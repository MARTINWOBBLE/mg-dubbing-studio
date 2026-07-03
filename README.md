# MG Dubbing Studio

Ett samlet, brukervennlig verktøy for å **transkribere, oversette og dubbe
videoveiledninger fra norsk til svensk** – med Mestergruppen-profil og norsk grensesnitt.

> ⚠️ **Lisens: Kildekoden er synlig (source-available), men dette er IKKE open source.**
> Alle rettigheter forbeholdt. Kopiering, distribusjon eller bruk krever skriftlig
> tillatelse. Se [LICENSE](LICENSE).

| | |
|---|---|
| 📖 **Skal du bare bruke verktøyet?** | Les [BRUKERVEILEDNING.md](BRUKERVEILEDNING.md) |
| 🚀 **Rask start (Windows)** | Dobbeltklikk `start.cmd` |
| 🐳 **Server/Docker** | `docker-compose up --build` |

## Funksjoner

- **Dubb video** – komplett løype i tre steg:
  1. Last opp norsk video → transkriber ([NbAiLab nb-whisper](https://huggingface.co/NbAiLab))
  2. Oversett til svensk (lokal Helsinki-NLP **eller** Gemini via OpenRouter)
  3. Rediger teksten → generer svensk voiceover (Edge-TTS gratis, eller premium via
     OpenRouter) lagt på originalvideoen
- **Tospråklig voiceover** – ta en transkripsjon og få én norsk + én svensk lydfil
- **Ekspertmodus** – hopp rett til dubbing med en ferdig svensk JSON
- **Testmodus** – dub bare de 3 første setningene for rask kvalitetssjekk
- **Miljøsjekk** – `/api/health` rapporterer hva som er tilgjengelig (FFmpeg, lokale
  modeller, nøkkel), og UI-et tilpasser seg automatisk
- **Automatisk opprydding** – gamle opplastinger/utdata slettes etter `RETENTION_DAYS`

## Installasjon

### Windows (anbefalt for vanlig bruk)

**Forutsetninger:** [Python 3.11+](https://www.python.org/downloads/) (huk av
*Add to PATH*) og FFmpeg (`winget install Gyan.FFmpeg`).

Dobbeltklikk **`start.cmd`** – første gang settes alt opp automatisk, deretter
starter serveren og nettleseren åpnes på http://localhost:8080.

For **lokal transkribering/oversettelse** (gratis, ingen API-nøkkel, men laster ned
flere GB modeller):

```bash
.venv\Scripts\pip install -r requirements.txt
```

### Docker (server / deling med team)

```bash
docker-compose up --build
```

`.env` er valgfri – alle verdier har fornuftige standarder. Imaget bruker CPU-only
torch og cacher HuggingFace-modeller i et volum.

### Manuelt (alle plattformer)

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # eller requirements-web.txt for lett variant
uvicorn app.main:app --port 8080
```

## Konfigurasjon

Alt settes i `.env` (se `.env.example`):

| Variabel | Beskrivelse |
|----------|-------------|
| `OPENROUTER_API_KEY` | Valgfri. For Gemini-oversettelse og premium-stemmer. |
| `FFMPEG_PATH` | Valgfri. Sti til FFmpeg sin `bin`-katalog hvis ikke på PATH. |
| `HOST` / `PORT` | Bind-adresse og port (kun `python -m app.main`). Standard `127.0.0.1:8080`. |
| `MAX_UPLOAD_MB` | Maks opplastingsstørrelse. Standard `1024`. |
| `RETENTION_DAYS` | Slett opplastinger/utdata eldre enn dette ved oppstart. Standard `7`, `0` = aldri. |
| `EDGE_TTS_TIMEOUT` | Timeout (sek) per Edge-TTS-segment. Standard `120`. |
| `ASR_MODEL` / `MT_MODEL` | Overstyr standardmodellene. |
| `OPENROUTER_TRANSLATE_MODEL` | Modell for Gemini-oversettelse. |
| `OPENROUTER_TTS_MODEL` / `OPENROUTER_TTS_VOICE` | Standard premium-stemme (vises i UI). |
| `DUAL_VO_VOICE` | Standardstemme for tospråklig voiceover. |

API-nøkkelen kan også legges inn direkte i grensesnittet (⚙) – da lagres den kun
lokalt i nettleseren (`localStorage`), aldri på serveren.

## Sikkerhet / nettverk

Verktøyet har **ingen innebygd autentisering**. Lokalt binder det kun til
`127.0.0.1`. Docker-imaget binder `0.0.0.0` for å være tilgjengelig i containeren –
hvis du eksponerer porten på et delt nettverk, sett det bak en autentisert
reverse-proxy eller begrens tilgangen.

## Arkitektur

```
app/
  main.py       FastAPI-ruter (synkrone def → threadpool, blokkerer ikke serveren)
  pipeline.py   Kjernelogikk – tunge ML-importer lastes lazy
  config.py     Miljø, kataloger, modellvalg
static/         Frontend (norsk, lys Mestergruppen-profil, WCAG-vennlig)
uploads/        Opplastede videoer + transkripsjoner (utenfor git, auto-ryddes)
output/         Ferdige videoer/lydfiler (utenfor git, auto-ryddes)
```

ML-bibliotekene importeres først når de faktisk trengs, slik at serveren og
miljøsjekken starter selv før modellene er installert. Whisper-tidsstempler med
manglende/`None`-verdier håndteres tolerant (sekvensiell fallback).

## API

| Endepunkt | Hva |
|-----------|-----|
| `GET /api/health` | Versjon, kapabiliteter, stemmer og standardmodeller |
| `POST /api/transcribe` | Video → norsk transkripsjon (med tidsstempler) |
| `POST /api/translate` | Transkripsjon → svensk (lokal/OpenRouter) |
| `POST /api/upload-video` | Last opp video (ekspertmodus) |
| `POST /api/dub` | Svensk JSON + video → dubbet video |
| `POST /api/dual-vo` | JSON → norsk + svensk lydfil |

Alle feil returneres som `{"status": "error", "message": "<norsk forklaring>"}`.

## Historikk

Dette verktøyet konsoliderer tre tidligere prototyper:
[`nb-whisper-transcription`](https://github.com/MARTINWOBBLE/nb-whisper-transcription),
[`mg-dual-vo-studio`](https://github.com/MARTINWOBBLE/mg-dual-vo-studio) og
[`swedish-voiceover-tool`](https://github.com/MARTINWOBBLE/swedish-voiceover-tool)
(alle arkivert).

## Lisens

**Proprietær – alle rettigheter forbeholdt.** Kildekoden er publisert for innsyn
og intern bruk i Mestergruppen, ikke for gjenbruk. Se [LICENSE](LICENSE).
