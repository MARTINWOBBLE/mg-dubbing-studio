# Brukerveiledning – MG Dubbing Studio

Dette verktøyet tar en **norsk videoveiledning** og lager en versjon med **svensk tale**.
Du trenger ikke kunne noe teknisk for å bruke det.

---

## Kom i gang (første gang)

1. Sørg for at **Python 3.11+** er installert ([python.org/downloads](https://www.python.org/downloads/) – huk av *«Add python.exe to PATH»*).
2. Sørg for at **FFmpeg** er installert (`winget install Gyan.FFmpeg` i en terminal, eller be IT).
3. Dobbeltklikk på **`start.cmd`** i prosjektmappen.
   - Første gang settes alt opp automatisk (tar et par minutter).
   - Nettleseren åpner seg på `http://localhost:8080`.

> 💡 Neste gang trenger du bare å dobbeltklikke `start.cmd` igjen.

### Vil du transkribere lokalt (uten API-nøkkel)?

Kjør denne én gang i en terminal i prosjektmappen (laster ned AI-modeller, flere GB):

```
.venv\Scripts\pip install -r requirements.txt
```

Alternativt: legg inn en **OpenRouter-nøkkel** under ⚙-knappen i appen, så brukes
skyen til oversettelse i stedet.

---

## Slik dubber du en video (vanlig bruk)

### Steg 1 – Kildevideo
Dra MP4-filen inn i opplastingsfeltet (eller klikk og velg fil).
Trykk **«Start transkribering»**. Vent – dette kan ta noen minutter.

### Steg 2 – Norsk transkripsjon
Les gjennom teksten som dukker opp. Velg oversetter:
- **Lokal modell** – gratis, kjører på din maskin (krever full installasjon)
- **OpenRouter/Gemini** – bedre kvalitet, krever API-nøkkel (⚙)

Trykk **«Oversett til svensk»**.

### Steg 3 – Svensk dubbing
Les gjennom og **rediger gjerne den svenske teksten** direkte i feltet (det er vanlig
JSON – endre bare tekstene mellom anførselstegn).

Velg stemme:
- **Sofie / Hillevi / Mattias** – gratis, høy kvalitet (Microsoft)
- **Premium** – Gemini-stemmer via OpenRouter (krever nøkkel)

La **«Testmodus»** stå på første gang – da dubbes bare de tre første setningene,
så du raskt hører om stemmen passer. Skru den av og trykk **«Generer dubbet video»**
igjen for full versjon.

### Ferdig!
Videoen spilles av nederst. Trykk **«Last ned svensk video»**.

---

## Ekspertmodus

Har du allerede en ferdig svensk transkripsjon (JSON-fil fra en tidligere kjøring)?

1. Last opp videoen i steg 1
2. Trykk **«Ekspertmodus: hopp til redigering»**
3. Lim inn JSON-en i steg 3 og generer

---

## Tospråklig voiceover (egen fane)

Lager **to lydfiler** (én norsk, én svensk) fra samme manus – nyttig når du skal
legge lyd på selv i et redigeringsprogram. Krever OpenRouter-nøkkel.

1. Lim inn eller last opp transkripsjons-JSON
2. Trykk **«Generer NO + SV lyd»**
3. Last ned begge MP3-filene

---

## Vanlige spørsmål

**Hvor lang tid tar det?**
Transkribering: ca. 20–30 % av videolengden. Full dubbing: noen minutter ekstra.
Klokken ved siden av spinneren viser medgått tid.

**«Begrenset miljø» øverst til høyre?**
Noe mangler på maskinen. Det gule banneret forteller hva – oftest at lokale
modeller ikke er installert (se «Kom i gang»).

**Feilmelding under dubbing?**
Sjekk at den svenske teksten fortsatt er gyldig JSON (alle anførselstegn og
komma på plass). Bruk «Last ned svensk JSON» som sikkerhetskopi før du redigerer mye.

**Hvor havner filene?**
Ferdige videoer/lyd: `output/`-mappen. Opplastinger: `uploads/`.
Filer eldre enn 7 dager ryddes automatisk ved oppstart (kan endres med
`RETENTION_DAYS` i `.env`).

**Starte på nytt?**
Trykk ↺-knappen øverst til høyre.

---

*Internt verktøy for Mestergruppen. Spørsmål? Kontakt Martin Zimmer Wold.*
