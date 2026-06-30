# MG Dubbing Studio

Ett samlet, brukervennlig verktøy for å **transkribere, oversette og dubbe
videoveiledninger fra norsk til svensk** – med Mestergruppen-profil og norsk grensesnitt.

Dette er konsolideringen av tre tidligere prototyper
([`nb-whisper-transcription`](https://github.com/MARTINWOBBLE/nb-whisper-transcription),
[`mg-dual-vo-studio`](https://github.com/MARTINWOBBLE/mg-dual-vo-studio) og
[`swedish-voiceover-tool`](https://github.com/MARTINWOBBLE/swedish-voiceover-tool))
til én FastAPI-app.

## Funksjoner

- **Dubb video** – komplett løype i tre steg:
  1. Last opp norsk video → transkriber (NbAiLab nb-whisper)
  2. Oversett til svensk (lokal Helsinki-NLP **eller** Gemini via OpenRouter)
  3. Rediger teksten → generer svensk voiceover (Edge-TTS gratis, eller premium via OpenRouter) lagt på originalvideoen
- **Tospråklig voiceover** – ta en transkripsjon og få én norsk + én svensk lydfil
- **Ekspertmodus** – hopp rett til dubbing med en ferdig svensk JSON
- **Miljøsjekk** – `/api/health` rapporterer hva som er tilgjengelig (FFmpeg, lokale modeller, nøkkel), og UI-et tilpasser seg automatisk

## Rask start

### Med Docker (anbefalt)

```bash
cp .env.example .env      # legg evt. inn OPENROUTER_API_KEY
docker-compose up --build
```

Åpne deretter http://localhost:8080

### Lokalt (Python 3.11)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt # full installasjon med lokale modeller
uvicorn app.main:app --port 8080
```

> **Lett variant:** `pip install -r requirements-web.txt` starter serveren og UI-et
> uten de tunge ML-modellene (nyttig for testing, eller hvis du kun bruker
> OpenRouter + Edge-TTS).

Krever **FFmpeg** på `PATH` (eller sett `FFMPEG_PATH` i `.env`).

## Konfigurasjon

Alt settes i `.env` (se `.env.example`):

| Variabel | Beskrivelse |
|----------|-------------|
| `OPENROUTER_API_KEY` | Valgfri. For Gemini-oversettelse og premium-stemmer. |
| `FFMPEG_PATH` | Valgfri. Sti til FFmpeg sin `bin`-katalog hvis ikke på PATH. |
| `ASR_MODEL` / `MT_MODEL` | Overstyr standardmodellene. |

API-nøkkelen kan også legges inn direkte i grensesnittet (⚙) – da lagres den kun
lokalt i nettleseren (`localStorage`).

## Arkitektur

```
app/
  main.py       FastAPI-ruter (tynt lag)
  pipeline.py   Kjernelogikk – tunge ML-importer lastes lazy
  config.py     Miljø, kataloger, modellvalg
static/         Frontend (norsk, lys MG-profil)
uploads/        Opplastede videoer + transkripsjoner (utenfor git)
output/         Ferdige videoer/lydfiler (utenfor git)
```

ML-bibliotekene importeres først når de faktisk trengs, slik at serveren og
miljøsjekken starter selv før modellene er installert.

## API

| Endepunkt | Hva |
|-----------|-----|
| `GET /api/health` | Versjon + kapabiliteter + stemmer |
| `POST /api/transcribe` | Video → norsk transkripsjon |
| `POST /api/translate` | Transkripsjon → svensk (lokal/OpenRouter) |
| `POST /api/upload-video` | Last opp video (ekspertmodus) |
| `POST /api/dub` | Svensk JSON + video → dubbet video |
| `POST /api/dual-vo` | JSON → norsk + svensk lydfil |

## Lisens

Proprietær – intern bruk i Mestergruppen. Se [LICENSE](LICENSE).
