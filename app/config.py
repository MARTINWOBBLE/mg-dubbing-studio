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

# Valgfri FFmpeg-sti (hvis ikke allerede på PATH)
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "").strip()
if FFMPEG_PATH and FFMPEG_PATH not in os.environ.get("PATH", ""):
    os.environ["PATH"] += os.pathsep + FFMPEG_PATH

# OpenRouter (valgfritt – kun for Gemini-oversettelse / premium-stemmer)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

# Modellvalg (kan overstyres via .env)
ASR_MODEL = os.getenv("ASR_MODEL", "NbAiLab/nb-whisper-medium-beta")
MT_MODEL = os.getenv("MT_MODEL", "Helsinki-NLP/opus-mt-no-sv")
DEFAULT_OPENROUTER_TRANSLATE_MODEL = os.getenv(
    "OPENROUTER_TRANSLATE_MODEL", "google/gemini-2.0-flash-001"
)

# Svenske standardstemmer (Edge-TTS – gratis, ingen nøkkel)
EDGE_VOICES = [
    {"id": "sv-SE-SofieNeural", "label": "Sofie (kvinne)"},
    {"id": "sv-SE-HilleviNeural", "label": "Hillevi (kvinne)"},
    {"id": "sv-SE-MattiasNeural", "label": "Mattias (mann)"},
]
