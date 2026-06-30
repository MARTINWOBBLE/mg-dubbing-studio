"""Kjernelogikk: transkribering, oversettelse, dubbing og tospråklig voiceover.

Alle tunge avhengigheter (torch, transformers, moviepy, pydub, edge_tts) importeres
*inne i* funksjonene. Det gjør at web-serveren og /api/health starter selv om de
maskinlæringsbibliotekene ikke er installert ennå.

Funksjonene her er synkrone og tunge. Endepunktene i main.py er derfor vanlige `def`
slik at FastAPI kjører dem i en threadpool og ikke blokkerer event-loopen.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

import requests

from . import config

logger = logging.getLogger("mg_dubbing")


# ---------------------------------------------------------------------------
# Kapabilitets-deteksjon – brukes av /api/health og frontend
# ---------------------------------------------------------------------------
def _module_available(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def check_capabilities() -> dict:
    """Hva kan denne installasjonen faktisk gjøre akkurat nå?"""
    ffmpeg = shutil.which("ffmpeg") is not None
    return {
        "ffmpeg": ffmpeg,
        "local_asr": _module_available("torch") and _module_available("transformers"),
        "local_mt": _module_available("torch") and _module_available("transformers"),
        "edge_tts": _module_available("edge_tts"),
        "media": _module_available("moviepy") and _module_available("pydub"),
        "openrouter_key": bool(config.OPENROUTER_API_KEY),
    }


class PipelineError(Exception):
    """Brukervennlig feil som kan vises direkte i grensesnittet."""


# ---------------------------------------------------------------------------
# Lazy-lastede modeller (caches mellom kall)
# ---------------------------------------------------------------------------
_asr_pipe = None
_mt_model = None
_mt_tokenizer = None


def _device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def _get_asr():
    global _asr_pipe
    if _asr_pipe is None:
        from transformers import pipeline

        dev = _device()
        logger.info("Laster ASR-modell %s på %s", config.ASR_MODEL, dev)
        _asr_pipe = pipeline(
            "automatic-speech-recognition",
            model=config.ASR_MODEL,
            chunk_length_s=30,
            device=dev,
        )
    return _asr_pipe


def _get_mt():
    global _mt_model, _mt_tokenizer
    if _mt_model is None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        dev = _device()
        logger.info("Laster oversettelsesmodell %s på %s", config.MT_MODEL, dev)
        _mt_tokenizer = AutoTokenizer.from_pretrained(config.MT_MODEL)
        _mt_model = AutoModelForSeq2SeqLM.from_pretrained(config.MT_MODEL).to(dev)
    return _mt_model, _mt_tokenizer


# ---------------------------------------------------------------------------
# Tidsstempel-hjelpere (robuste mot None / manglende felt fra Whisper)
# ---------------------------------------------------------------------------
def _seg_start_ms(chunk: dict) -> Optional[int]:
    """Starttid i ms, eller None hvis segmentet mangler gyldig tidsstempel."""
    ts = chunk.get("timestamp")
    if not isinstance(ts, (list, tuple)) or len(ts) < 1 or ts[0] is None:
        return None
    return int(float(ts[0]) * 1000)


def _last_end_seconds(chunks: list, video_duration: float) -> float:
    """Sluttid for siste segment. Whisper lar ofte siste end-stempel være None."""
    end = None
    if chunks:
        ts = chunks[-1].get("timestamp")
        if isinstance(ts, (list, tuple)) and len(ts) >= 2 and ts[1] is not None:
            end = float(ts[1])
    if end is None or end <= 0:
        end = video_duration
    # Aldri lengre enn selve videoen (kan ikke subklippe forbi kilden).
    return min(end + 2.0, video_duration)


# ---------------------------------------------------------------------------
# 1) Transkribering: video -> norsk transkripsjon med tidsstempler
# ---------------------------------------------------------------------------
def transcribe_video(video_path: Path) -> dict:
    if not check_capabilities()["local_asr"]:
        raise PipelineError(
            "Lokale modeller er ikke installert. Kjør «pip install -r requirements.txt» "
            "for å aktivere transkribering."
        )
    try:
        from moviepy import VideoFileClip
    except Exception as exc:  # noqa: BLE001
        raise PipelineError(f"moviepy mangler eller FFmpeg er ikke tilgjengelig: {exc}")

    tmp_audio = config.UPLOAD_DIR / f"_temp_transcribe_{uuid.uuid4().hex[:8]}.wav"
    try:
        with VideoFileClip(str(video_path)) as clip:
            if clip.audio is None:
                raise PipelineError("Videoen har ingen lydspor å transkribere.")
            clip.audio.write_audiofile(
                str(tmp_audio), fps=16000, nbytes=2, codec="pcm_s16le", logger=None
            )

        pipe = _get_asr()
        result = pipe(
            str(tmp_audio),
            return_timestamps=True,
            generate_kwargs={"language": "no", "task": "transcribe"},
        )
        return result
    finally:
        if tmp_audio.exists():
            try:
                tmp_audio.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 2) Oversettelse NO -> SV (lokal modell ELLER OpenRouter/Gemini)
# ---------------------------------------------------------------------------
def translate_local(data: dict) -> dict:
    if not check_capabilities()["local_mt"]:
        raise PipelineError(
            "Lokale modeller er ikke installert. Velg «OpenRouter» som oversetter, "
            "eller installer requirements.txt."
        )
    import torch

    model, tokenizer = _get_mt()
    dev = _device()
    chunks = data.get("chunks", [])
    for chunk in chunks:
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512).to(dev)
        with torch.no_grad():
            generated = model.generate(**inputs, max_length=512)
        chunk["text"] = tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
    data["text"] = " ".join(c.get("text", "") for c in chunks)
    return data


_TRANSLATE_SYSTEM = (
    "Du er en profesjonell oversetter for Mestergruppen. Oversett følgende norske tekst "
    "til naturlig, profesjonell og presis svensk. Teksten er en veiledning for IT-systemer. "
    "Behold tekniske begreper og produktnavn (f.eks. «Diver») uendret når det er naturlig i "
    "svensk IT-sjargong. Svar KUN med den svenske oversettelsen, uten forklaring."
)


def _openrouter_chat(text: str, api_key: str, model: str) -> str:
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "MG Dubbing Studio",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": _TRANSLATE_SYSTEM},
                {"role": "user", "content": text},
            ],
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise PipelineError(f"OpenRouter-oversettelse feilet ({resp.status_code}): {resp.text[:300]}")
    try:
        body = resp.json()
    except ValueError:
        raise PipelineError("OpenRouter ga et ugyldig (ikke-JSON) svar.")
    choices = body.get("choices")
    if not choices:
        detail = body.get("error") or body
        raise PipelineError(f"OpenRouter ga uventet svar: {str(detail)[:300]}")
    content = (choices[0].get("message") or {}).get("content")
    if not content:
        raise PipelineError("OpenRouter returnerte et tomt svar.")
    return content.strip()


def translate_openrouter(data: dict, api_key: str, model: Optional[str] = None) -> dict:
    api_key = (api_key or config.OPENROUTER_API_KEY).strip()
    if not api_key:
        raise PipelineError("Mangler OpenRouter API-nøkkel for oversettelse.")
    model = model or config.DEFAULT_OPENROUTER_TRANSLATE_MODEL
    for chunk in data.get("chunks", []):
        text = (chunk.get("text") or "").strip()
        if text:
            chunk["text"] = _openrouter_chat(text, api_key, model)
    data["text"] = " ".join(c.get("text", "") for c in data.get("chunks", []))
    return data


# ---------------------------------------------------------------------------
# 3) Dubbing: svensk transkripsjon + originalvideo -> dubbet video
# ---------------------------------------------------------------------------
def _edge_save_sync(text: str, voice: str, out_mp3: str) -> None:
    import asyncio

    import edge_tts

    async def _run():
        await asyncio.wait_for(
            edge_tts.Communicate(text, voice).save(out_mp3), timeout=config.EDGE_TTS_TIMEOUT
        )

    try:
        asyncio.run(_run())
    except asyncio.TimeoutError as exc:
        raise PipelineError(
            "Edge-TTS (Microsoft) svarte ikke i tide. Prøv igjen eller bytt til OpenRouter-stemme."
        ) from exc


def _tts_segment_openrouter(text: str, api_key: str, model: str, voice: str) -> bytes:
    resp = requests.post(
        "https://openrouter.ai/api/v1/audio/speech",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "MG Dubbing Studio",
        },
        json={"model": model, "input": text, "voice": voice, "response_format": "pcm"},
        timeout=180,
    )
    if resp.status_code != 200:
        raise PipelineError(f"OpenRouter TTS feilet ({resp.status_code}): {resp.text[:300]}")
    return resp.content


def dub_video(
    data: dict,
    video_path: Path,
    voice: str,
    test_mode: bool = False,
    api_key: str = "",
    openrouter_model: str = "",
    openrouter_voice: str = "",
    output_name: str = "dubbet.mp4",
) -> str:
    caps = check_capabilities()
    if not caps["media"]:
        raise PipelineError("moviepy/pydub mangler. Installer requirements.txt for å dubbe.")

    from moviepy import AudioFileClip, VideoFileClip
    from pydub import AudioSegment

    openrouter_model = openrouter_model or config.OPENROUTER_TTS_MODEL
    openrouter_voice = openrouter_voice or config.OPENROUTER_TTS_VOICE

    chunks = list(data.get("chunks", []))
    if not chunks:
        raise PipelineError("Transkripsjonen inneholder ingen segmenter («chunks»).")
    if test_mode:
        chunks = chunks[:3]

    use_openrouter = voice == "openrouter_api"
    if use_openrouter:
        api_key = (api_key or config.OPENROUTER_API_KEY).strip()
        if not api_key:
            raise PipelineError("Mangler OpenRouter API-nøkkel for premium-stemme.")
    elif not caps["edge_tts"]:
        raise PipelineError("edge-tts mangler. Installer requirements.txt.")

    output_path = config.OUTPUT_DIR / output_name
    base_video = None
    render_clip = None
    try:
        base_video = VideoFileClip(str(video_path))
        full_audio = AudioSegment.silent(duration=int(base_video.duration * 1000), frame_rate=24000)

        with tempfile.TemporaryDirectory() as tmp:
            placed = 0
            last_end_ms = 0
            for i, chunk in enumerate(chunks):
                text = (chunk.get("text") or "").strip()
                if not text:
                    continue
                start_ms = _seg_start_ms(chunk)
                if start_ms is None:
                    logger.warning("Segment %d mangler starttidspunkt; bruker forrige sluttid.", i + 1)
                    start_ms = last_end_ms
                if use_openrouter:
                    pcm = _tts_segment_openrouter(text, api_key, openrouter_model, openrouter_voice)
                    seg = AudioSegment(data=pcm, sample_width=2, frame_rate=24000, channels=1)
                else:
                    seg_path = os.path.join(tmp, f"seg_{i}.mp3")
                    _edge_save_sync(text, voice, seg_path)
                    seg = AudioSegment.from_mp3(seg_path)
                full_audio = full_audio.overlay(seg, position=start_ms)
                last_end_ms = start_ms + len(seg)
                placed += 1

            if placed == 0:
                raise PipelineError(
                    "Ingen segmenter hadde tekst og gyldige tidsstempler å dubbe."
                )

            render_clip = base_video
            if test_mode:
                last_end_s = _last_end_seconds(chunks, base_video.duration)
                full_audio = full_audio[: int(last_end_s * 1000)]
                render_clip = base_video.subclipped(0, last_end_s)

            mixed = os.path.join(tmp, "mixed.wav")
            full_audio.export(mixed, format="wav")

            # Lukk lyd-/sluttklipp FØR temp-katalogen ryddes (unngår Windows-PermissionError
            # som ellers maskerer den egentlige feilen).
            audio_clip = None
            final = None
            try:
                audio_clip = AudioFileClip(mixed)
                final = render_clip.with_audio(audio_clip)
                final.write_videofile(
                    str(output_path),
                    codec="libx264",
                    audio_codec="aac",
                    preset="ultrafast",
                    threads=4,
                    logger=None,
                )
            finally:
                for clip in (final, audio_clip):
                    if clip is not None:
                        try:
                            clip.close()
                        except Exception:  # noqa: BLE001
                            pass
    finally:
        # Lukk både evt. subklipp (render_clip) og originalen (base_video).
        for clip in {id(render_clip): render_clip, id(base_video): base_video}.values():
            if clip is not None:
                try:
                    clip.close()
                except Exception:  # noqa: BLE001
                    pass
    return output_name


# ---------------------------------------------------------------------------
# 4) Tospråklig voiceover (fra mg-dual-vo-studio): JSON -> NO + SV lydfiler
# ---------------------------------------------------------------------------
def _extract_plain_text(data: dict) -> str:
    if data.get("chunks"):
        return " ".join(c.get("text", "") for c in data["chunks"]).strip()
    if data.get("segments"):
        return " ".join(s.get("text", "") for s in data["segments"]).strip()
    return (data.get("text") or "").strip()


def dual_voiceover(
    data: dict,
    api_key: str,
    model_id: str = "",
    voice: str = "",
) -> dict:
    """Lager én norsk og én svensk lydfil av samme manus via OpenRouter TTS."""
    api_key = (api_key or config.OPENROUTER_API_KEY).strip()
    if not api_key:
        raise PipelineError("Mangler OpenRouter API-nøkkel for tospråklig voiceover.")
    if not check_capabilities()["media"]:
        raise PipelineError("pydub mangler. Installer requirements.txt.")

    from pydub import AudioSegment

    model_id = model_id or config.OPENROUTER_TTS_MODEL
    voice = voice or config.DUAL_VO_VOICE

    text_no = _extract_plain_text(data)
    if not text_no:
        raise PipelineError("Fant ingen tekst i JSON-fila.")

    text_sv = _openrouter_chat(text_no, api_key, config.DEFAULT_OPENROUTER_TRANSLATE_MODEL)
    uid = uuid.uuid4().hex[:8]

    def synth(text: str, name: str) -> str:
        pcm = _tts_segment_openrouter(text, api_key, model_id, voice)
        seg = AudioSegment(data=pcm, sample_width=2, frame_rate=24000, channels=1)
        seg.export(str(config.OUTPUT_DIR / name), format="mp3")
        return name

    file_no = synth(text_no, f"vo_no_{voice}_{uid}.mp3")
    file_sv = synth(text_sv, f"vo_sv_{voice}_{uid}.mp3")
    return {
        "norwegian_text": text_no,
        "swedish_text": text_sv,
        "norwegian_audio": file_no,
        "swedish_audio": file_sv,
    }


# ---------------------------------------------------------------------------
# Hjelpere for lagring og opprydding
# ---------------------------------------------------------------------------
def save_upload(file_obj, filename: str) -> Path:
    # Unikt lagringsnavn så samtidige/gjentatte opplastinger ikke overskriver hverandre.
    safe = os.path.basename(filename) or "upload"
    dest = config.UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{safe}"
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    with open(dest, "wb") as buf:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if limit and written > limit:
                buf.close()
                try:
                    dest.unlink()
                except OSError:
                    pass
                raise PipelineError(
                    f"Filen er for stor (over grensen på {config.MAX_UPLOAD_MB} MB)."
                )
            buf.write(chunk)
    return dest


def save_json(data: dict, filename: str) -> Path:
    dest = config.UPLOAD_DIR / os.path.basename(filename)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return dest


def cleanup_old_files(days: Optional[int] = None) -> int:
    """Slett opplastinger/utdata eldre enn `days` dager. 0/None = ingen opprydding."""
    days = config.RETENTION_DAYS if days is None else days
    if not days or days <= 0:
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    for directory in (config.UPLOAD_DIR, config.OUTPUT_DIR):
        for path in directory.iterdir():
            if path.name == ".gitkeep" or not path.is_file():
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
    if removed:
        logger.info("Opprydding: slettet %d gamle filer (eldre enn %d dager)", removed, days)
    return removed
