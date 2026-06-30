"""FastAPI-app for MG Dubbing Studio. Tynt lag over pipeline.py."""
import json
import os

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, pipeline
from .pipeline import PipelineError

app = FastAPI(title="MG Dubbing Studio")

app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")
app.mount("/output", StaticFiles(directory=str(config.OUTPUT_DIR)), name="output")


def _ok(payload: dict):
    return {"status": "success", **payload}


def _err(message: str, code: int = 400):
    return JSONResponse(status_code=code, content={"status": "error", "message": message})


@app.get("/")
async def index():
    return FileResponse(str(config.STATIC_DIR / "index.html"))


@app.get("/api/health")
async def health():
    from . import __version__

    return _ok(
        {
            "version": __version__,
            "capabilities": pipeline.check_capabilities(),
            "edge_voices": config.EDGE_VOICES,
            "translate_model": config.DEFAULT_OPENROUTER_TRANSLATE_MODEL,
        }
    )


@app.post("/api/transcribe")
async def api_transcribe(video: UploadFile = File(...)):
    try:
        video_path = pipeline.save_upload(video.file, video.filename)
        result = pipeline.transcribe_video(video_path)
        stem = os.path.splitext(os.path.basename(video.filename))[0]
        transcript_file = f"{stem}_transcript.json"
        pipeline.save_json(result, transcript_file)
        return _ok(
            {
                "transcript": result,
                "transcript_file": transcript_file,
                "video_name": os.path.basename(video.filename),
            }
        )
    except PipelineError as e:
        return _err(str(e))
    except Exception as e:  # noqa: BLE001
        return _err(f"Uventet feil under transkribering: {e}", 500)


@app.post("/api/translate")
async def api_translate(
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

        sv_file = os.path.basename(transcript_file).replace(".json", "_sv.json")
        pipeline.save_json(data, sv_file)
        return _ok({"transcript": data, "transcript_file": sv_file})
    except PipelineError as e:
        return _err(str(e))
    except FileNotFoundError:
        return _err("Fant ikke transkripsjonsfila. Kjør transkribering først.", 404)
    except Exception as e:  # noqa: BLE001
        return _err(f"Uventet feil under oversettelse: {e}", 500)


@app.post("/api/upload-video")
async def api_upload_video(video: UploadFile = File(...)):
    """For ekspertmodus: last opp video uten å transkribere."""
    try:
        pipeline.save_upload(video.file, video.filename)
        return _ok({"video_name": os.path.basename(video.filename)})
    except Exception as e:  # noqa: BLE001
        return _err(f"Kunne ikke laste opp video: {e}", 500)


@app.post("/api/dub")
async def api_dub(
    video_name: str = Form(...),
    sv_json: str = Form(...),
    voice: str = Form("sv-SE-SofieNeural"),
    test_mode: bool = Form(True),
    api_key: str = Form(""),
    openrouter_model: str = Form("google/gemini-3.1-flash-tts-preview"),
    openrouter_voice: str = Form("Achird"),
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
        output_name = f"{stem}__{voice_tag}_{mode}.mp4"

        result_file = await pipeline.dub_video(
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
        return _err(f"Uventet feil under dubbing: {e}", 500)


@app.post("/api/dual-vo")
async def api_dual_vo(
    json_text: str = Form(...),
    voice: str = Form("Puck"),
    api_key: str = Form(""),
    model_id: str = Form("google/gemini-3.1-flash-tts-preview"),
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
        return _err(f"Uventet feil under voiceover: {e}", 500)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=False)
