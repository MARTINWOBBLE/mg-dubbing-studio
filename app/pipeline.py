"""Kjernelogikk: transkribering, oversettelse, dubbing og tospråklig voiceover.

Alle tunge avhengigheter (torch, transformers, moviepy, pydub, edge_tts) importeres
*inne i* funksjonene. Det gjør at web-serveren og /api/health starter selv om de
maskinlæringsbibliotekene ikke er installert ennå.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import requests

from . import config


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
        print(f"[ASR] Laster {config.ASR_MODEL} på {dev} ...", flush=True)
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
        print(f"[MT] Laster {config.MT_MODEL} på {dev} ...", flush=True)
        _mt_tokenizer = AutoTokenizer.from_pretrained(config.MT_MODEL)
        _mt_model = AutoModelForSeq2SeqLM.from_pretrained(config.MT_MODEL).to(dev)
    return _mt_model, _mt_tokenizer


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

    tmp_audio = config.UPLOAD_DIR / "_temp_transcribe.wav"
    try:
        clip = VideoFileClip(str(video_path))
        if clip.audio is None:
            clip.close()
            raise PipelineError("Videoen har ingen lydspor å transkribere.")
        clip.audio.write_audiofile(
            str(tmp_audio), fps=16000, nbytes=2, codec="pcm_s16le", logger=None
        )
        clip.close()

        pipe = _get_asr()
        result = pipe(
            str(tmp_audio),
            return_timestamps=True,
            generate_kwargs={"language": "no", "task": "transcribe"},
        )
        return result
    finally:
        if tmp_audio.exists():
            tmp_audio.unlink()


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
        inputs = tokenizer(text, return_tensors="pt", truncation=True).to(dev)
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
    return resp.json()["choices"][0]["message"]["content"].strip()


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
async def _tts_segment_edge(text: str, voice: str, out_mp3: str) -> None:
    import edge_tts

    await edge_tts.Communicate(text, voice).save(out_mp3)


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


async def dub_video(
    data: dict,
    video_path: Path,
    voice: str,
    test_mode: bool = False,
    api_key: str = "",
    openrouter_model: str = "google/gemini-3.1-flash-tts-preview",
    openrouter_voice: str = "Achird",
    output_name: str = "dubbet.mp4",
) -> str:
    caps = check_capabilities()
    if not caps["media"]:
        raise PipelineError("moviepy/pydub mangler. Installer requirements.txt for å dubbe.")

    from moviepy import AudioFileClip, VideoFileClip
    from pydub import AudioSegment

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
    video = VideoFileClip(str(video_path))
    try:
        full_audio = AudioSegment.silent(duration=int(video.duration * 1000), frame_rate=24000)
        with tempfile.TemporaryDirectory() as tmp:
            for i, chunk in enumerate(chunks):
                text = (chunk.get("text") or "").strip()
                if not text:
                    continue
                start_ms = int(chunk["timestamp"][0] * 1000)
                if use_openrouter:
                    pcm = _tts_segment_openrouter(text, api_key, openrouter_model, openrouter_voice)
                    seg = AudioSegment(data=pcm, sample_width=2, frame_rate=24000, channels=1)
                else:
                    seg_path = os.path.join(tmp, f"seg_{i}.mp3")
                    await _tts_segment_edge(text, voice, seg_path)
                    seg = AudioSegment.from_mp3(seg_path)
                full_audio = full_audio.overlay(seg, position=start_ms)

            if test_mode and chunks:
                last_end_ms = int((chunks[-1]["timestamp"][1] + 2.0) * 1000)
                full_audio = full_audio[:last_end_ms]
                video = video.subclipped(0, min(last_end_ms / 1000.0, video.duration))

            mixed = os.path.join(tmp, "mixed.wav")
            full_audio.export(mixed, format="wav")
            final = video.with_audio(AudioFileClip(mixed))
            final.write_videofile(
                str(output_path),
                codec="libx264",
                audio_codec="aac",
                preset="ultrafast",
                threads=4,
                logger=None,
            )
            final.close()
    finally:
        video.close()
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
    model_id: str = "google/gemini-3.1-flash-tts-preview",
    voice: str = "Puck",
) -> dict:
    """Lager én norsk og én svensk lydfil av samme manus via OpenRouter TTS."""
    api_key = (api_key or config.OPENROUTER_API_KEY).strip()
    if not api_key:
        raise PipelineError("Mangler OpenRouter API-nøkkel for tospråklig voiceover.")
    if not check_capabilities()["media"]:
        raise PipelineError("pydub mangler. Installer requirements.txt.")

    from pydub import AudioSegment

    text_no = _extract_plain_text(data)
    if not text_no:
        raise PipelineError("Fant ingen tekst i JSON-fila.")

    text_sv = _openrouter_chat(text_no, api_key, config.DEFAULT_OPENROUTER_TRANSLATE_MODEL)

    def synth(text: str, name: str) -> str:
        pcm = _tts_segment_openrouter(text, api_key, model_id, voice)
        seg = AudioSegment(data=pcm, sample_width=2, frame_rate=24000, channels=1)
        out = config.OUTPUT_DIR / name
        seg.export(str(out), format="mp3")
        return name

    file_no = synth(text_no, f"vo_no_{voice}.mp3")
    file_sv = synth(text_sv, f"vo_sv_{voice}.mp3")
    return {
        "norwegian_text": text_no,
        "swedish_text": text_sv,
        "norwegian_audio": file_no,
        "swedish_audio": file_sv,
    }


# ---------------------------------------------------------------------------
# Hjelpere for lagring
# ---------------------------------------------------------------------------
def save_upload(file_obj, filename: str) -> Path:
    safe = os.path.basename(filename)
    dest = config.UPLOAD_DIR / safe
    with open(dest, "wb") as buf:
        shutil.copyfileobj(file_obj, buf)
    return dest


def save_json(data: dict, filename: str) -> Path:
    dest = config.UPLOAD_DIR / os.path.basename(filename)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return dest
