"""Sentral konfigurasjon. Leser miljøvariabler én gang og eksponerer kataloger."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Rotkatalog for prosjektet (mappen over app/)
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


# Server (CLI / __main__). Standard er localhost; Docker setter HOST=0.0.0.0.
HOST = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
PORT = _int_env("PORT", 8080)

# Valgfri FFmpeg-sti (hvis ikke allerede på PATH)
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "").strip()
if FFMPEG_PATH and FFMPEG_PATH not in os.environ.get("PATH", ""):
    os.environ["PATH"] += os.pathsep + FFMPEG_PATH

# OpenRouter (valgfritt – kun for Gemini-oversettelse / premium-stemmer)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

# Grenser og opprydding
MAX_UPLOAD_MB = _int_env("MAX_UPLOAD_MB", 1024)  # avvis opplastinger over denne grensen
RETENTION_DAYS = _int_env("RETENTION_DAYS", 7)   # rydd opplastinger/utdata eldre enn dette (0 = aldri)
EDGE_TTS_TIMEOUT = _int_env("EDGE_TTS_TIMEOUT", 120)

# Modellvalg (kan overstyres via .env)
ASR_MODEL = os.getenv("ASR_MODEL", "NbAiLab/nb-whisper-medium-beta")
MT_MODEL = os.getenv("MT_MODEL", "Helsinki-NLP/opus-mt-no-sv")
DEFAULT_OPENROUTER_TRANSLATE_MODEL = os.getenv(
    "OPENROUTER_TRANSLATE_MODEL", "google/gemini-2.0-flash-001"
)
# Premium TTS via OpenRouter (standardverdier som frontend henter fra /api/health)
OPENROUTER_TTS_MODEL = os.getenv("OPENROUTER_TTS_MODEL", "google/gemini-3.1-flash-tts-preview")
OPENROUTER_TTS_VOICE = os.getenv("OPENROUTER_TTS_VOICE", "Achird")
DUAL_VO_VOICE = os.getenv("DUAL_VO_VOICE", "Puck")

# Svenske standardstemmer (Edge-TTS – gratis, ingen nøkkel)
EDGE_VOICES = [
    {"id": "sv-SE-SofieNeural", "label": "Sofie (kvinne)"},
    {"id": "sv-SE-HilleviNeural", "label": "Hillevi (kvinne)"},
    {"id": "sv-SE-MattiasNeural", "label": "Mattias (mann)"},
]
