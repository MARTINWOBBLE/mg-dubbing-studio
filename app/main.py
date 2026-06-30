"""FastAPI-app for MG Dubbing Studio. Tynt lag over pipeline.py.

Endepunktene er bevisst synkrone (`def`), slik at FastAPI kjører dem i en threadpool
og det tunge arbeidet (ffmpeg, modeller, nettverk) ikke blokkerer event-loopen.
"""
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, pipeline
from .pipeline import PipelineError

logger = logging.getLogger("mg_dubbing")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        pipeline.cleanup_old_files()
    except Exception:  # noqa: BLE001
        logger.exception("Opprydding ved oppstart feilet")
    yield


app = FastAPI(title="MG Dubbing Studio", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
app.mount("/output", StaticFiles(directory=str(config.OUTPUT_DIR)), name="output")


def _ok(payload: dict):
    return {"status": "success", **payload}


def _err(message: str, code: int = 400):
    return JSONResponse(status_code=code, content={"status": "error", "message": message})


@app.get("/")
async def index():
    return FileResponse(str(config.STATIC_DIR / "index.html"))


@app.head("/")
async def index_head():
    return Response(status_code=200)


@app.get("/api/health")
async def health():
    from . import __version__

    return _ok(
        {
            "version": __version__,
            "capabilities": pipeline.check_capabilities(),
            "edge_voices": config.EDGE_VOICES,
            "translate_model": config.DEFAULT_OPENROUTER_TRANSLATE_MODEL,
            "tts_model": config.OPENROUTER_TTS_MODEL,
            "tts_voice": config.OPENROUTER_TTS_VOICE,
            "dual_voice": config.DUAL_VO_VOICE,
            "max_upload_mb": config.MAX_UPLOAD_MB,
        }
    )


@app.post("/api/transcribe")
def api_transcribe(video: UploadFile = File(...)):
    try:
        video_path = pipeline.save_upload(video.file, video.filename)
        result = pipeline.transcribe_video(video_path)
        stem = os.path.splitext(video_path.name)[0]
        transcript_file = f"{stem}_transcript.json"
        pipeline.save_json(result, transcript_file)
        return _ok(
            {
                "transcript": result,
                "transcript_file": transcript_file,
                "video_name": video_path.name,
            }
        )
    except PipelineError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Uventet feil i /api/transcribe")
        return _err(f"Uventet feil under transkribering: {e}", 500)


@app.post("/api/translate")
def api_translate(
    transcript_file: str = Form(...),
    engine: str = Form("local"),
    api_key: str = Form(""),
    model: str = Form(""),
):
    try:
        path = config.UPLOAD_DIR / os.path.basename(transcript_file)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if engine == "openrouter":
            data = pipeline.translate_openrouter(data, api_key, model or None)
        else:
            data = pipeline.translate_local(data)

        base = os.path.splitext(os.path.basename(transcript_file))[0]
        sv_file = f"{base}_sv.json"
        pipeline.save_json(data, sv_file)
        return _ok({"transcript": data, "transcript_file": sv_file})
    except PipelineError as e:
        return _err(str(e))
    except FileNotFoundError:
        return _err("Fant ikke transkripsjonsfila. Kjør transkribering først.", 404)
    except Exception as e:  # noqa: BLE001
        logger.exception("Uventet feil i /api/translate")
        return _err(f"Uventet feil under oversettelse: {e}", 500)


@app.post("/api/upload-video")
def api_upload_video(video: UploadFile = File(...)):
    """For ekspertmodus: last opp video uten å transkribere."""
    try:
        video_path = pipeline.save_upload(video.file, video.filename)
        return _ok({"video_name": video_path.name})
    except PipelineError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Uventet feil i /api/upload-video")
        return _err(f"Kunne ikke laste opp video: {e}", 500)


@app.post("/api/dub")
def api_dub(
    video_name: str = Form(...),
    sv_json: str = Form(...),
    voice: str = Form("sv-SE-SofieNeural"),
    test_mode: bool = Form(True),
    api_key: str = Form(""),
    openrouter_model: str = Form(""),
    openrouter_voice: str = Form(""),
):
    try:
        try:
            data = json.loads(sv_json)
        except json.JSONDecodeError:
            return _err("Den svenske transkripsjonen er ikke gyldig JSON.")

        video_path = config.UPLOAD_DIR / os.path.basename(video_name)
        if not video_path.exists():
            return _err("Fant ikke originalvideoen på serveren. Last den opp på nytt.", 404)

        stem = os.path.splitext(os.path.basename(video_name))[0]
        mode = "test" if test_mode else "full"
        voice_tag = "openrouter" if voice == "openrouter_api" else voice
        output_name = f"{stem}__{voice_tag}_{mode}_{uuid.uuid4().hex[:8]}.mp4"

        result_file = pipeline.dub_video(
            data=data,
            video_path=video_path,
            voice=voice,
            test_mode=test_mode,
            api_key=api_key,
            openrouter_model=openrouter_model,
            openrouter_voice=openrouter_voice,
            output_name=output_name,
        )
        return _ok({"file": result_file})
    except PipelineError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Uventet feil i /api/dub")
        return _err(f"Uventet feil under dubbing: {e}", 500)


@app.post("/api/dual-vo")
def api_dual_vo(
    json_text: str = Form(...),
    voice: str = Form(""),
    api_key: str = Form(""),
    model_id: str = Form(""),
):
    try:
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            return _err("Innholdet er ikke gyldig JSON.")
        result = pipeline.dual_voiceover(data, api_key=api_key, model_id=model_id, voice=voice)
        return _ok(result)
    except PipelineError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Uventet feil i /api/dual-vo")
        return _err(f"Uventet feil under voiceover: {e}", 500)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=False)
