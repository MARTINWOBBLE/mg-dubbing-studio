/* ===== MG Dubbing Studio – frontend ===== */
const $ = (id) => document.getElementById(id);
const API_KEY_STORE = "mg_dubbing_openrouter_key";

const state = {
    videoName: null,
    videoFile: null,
    svFile: null,
    capabilities: {},
};

/* ---------- Logg & status ---------- */
function log(msg) {
    const el = $("log");
    const t = new Date().toLocaleTimeString("nb-NO");
    el.textContent += `\n› ${t}  ${msg}`;
    el.scrollTop = el.scrollHeight;
}
function setStatus(id, kind, msg) {
    const el = $(id);
    el.hidden = false;
    el.className = "status" + (kind === "error" ? " error" : kind === "ok" ? " ok" : "");
    el.innerHTML = kind === "loading"
        ? `<span class="spinner"></span><span>${msg}</span>`
        : `<span>${msg}</span>`;
}
function hide(id) { $(id).hidden = true; }
function setStep(id, st) { $(id).dataset.state = st; }
function setBadge(id, text) { $(id).textContent = text; }

/* ---------- API-nøkkel ---------- */
const getKey = () => localStorage.getItem(API_KEY_STORE) || "";

/* ---------- Helse / kapabiliteter ---------- */
async function loadHealth() {
    try {
        const res = await fetch("/api/health");
        const data = await res.json();
        state.capabilities = data.capabilities || {};
        renderHealth(data);
    } catch (e) {
        $("health-pill").textContent = "Server utilgjengelig";
        $("health-pill").className = "pill pill-warn";
    }
}
function renderHealth(data) {
    const c = data.capabilities || {};
    const pill = $("health-pill");
    const ready = c.ffmpeg && (c.local_asr || c.openrouter_key);
    pill.textContent = ready ? `Klar · v${data.version}` : "Begrenset miljø";
    pill.className = "pill " + (ready ? "pill-ok" : "pill-warn");

    // Bygg stemmeliste
    const sel = $("voice-select");
    sel.innerHTML = "";
    (data.edge_voices || []).forEach((v) => {
        const o = document.createElement("option");
        o.value = v.id; o.textContent = `${v.label} · Edge (gratis)`;
        sel.appendChild(o);
    });
    const orOpt = document.createElement("option");
    orOpt.value = "openrouter_api"; orOpt.textContent = "Premium (OpenRouter/Gemini)";
    sel.appendChild(orOpt);

    // Kapabilitets-banner
    const warnings = [];
    if (!c.ffmpeg) warnings.push("FFmpeg mangler – transkribering og dubbing vil ikke fungere.");
    if (!c.local_asr) warnings.push("Lokale modeller er ikke installert – transkribering krever «pip install -r requirements.txt».");
    if (!c.local_mt && !c.openrouter_key) warnings.push("Ingen oversetter tilgjengelig – installer modellene eller legg inn en OpenRouter-nøkkel under ⚙.");
    const banner = $("cap-banner");
    if (warnings.length) {
        banner.hidden = false;
        banner.className = "banner banner-warn";
        banner.innerHTML = "<strong>Merk:</strong> " + warnings.join(" ");
    } else {
        banner.hidden = true;
    }
}

/* ---------- Faner ---------- */
document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
        tab.classList.add("active");
        $("tab-" + tab.dataset.tab).classList.add("active");
    });
});

/* ---------- Innstillinger-modal ---------- */
$("settings-btn").addEventListener("click", () => {
    $("api-key").value = getKey();
    $("settings-modal").hidden = false;
});
$("settings-cancel").addEventListener("click", () => ($("settings-modal").hidden = true));
$("settings-save").addEventListener("click", () => {
    localStorage.setItem(API_KEY_STORE, $("api-key").value.trim());
    $("settings-modal").hidden = true;
    log("API-nøkkel lagret lokalt.");
    loadHealth();
});

/* ---------- Steg 1: video ---------- */
const dropzone = $("dropzone");
const videoInput = $("video-input");
dropzone.addEventListener("click", () => videoInput.click());
["dragover", "dragenter"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); }));
dropzone.addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) selectVideo(e.dataTransfer.files[0]); });
videoInput.addEventListener("change", (e) => { if (e.target.files[0]) selectVideo(e.target.files[0]); });

function selectVideo(file) {
    state.videoFile = file;
    state.videoName = file.name;
    const info = $("video-info");
    info.hidden = false;
    info.textContent = `🎞 ${file.name} (${(file.size / 1048576).toFixed(1)} MB)`;
    $("btn-transcribe").disabled = false;
    log(`Video valgt: ${file.name}`);
}

/* ---------- Steg 1 → 2: transkribering ---------- */
$("btn-transcribe").addEventListener("click", async () => {
    if (!state.videoFile) return;
    $("btn-transcribe").disabled = true;
    setStatus("status-1", "loading", "Transkriberer… dette kan ta noen minutter.");
    log("Starter transkribering…");
    const fd = new FormData();
    fd.append("video", state.videoFile);
    try {
        const data = await postJSON("/api/transcribe", fd);
        state.svFile = null;
        state.noFile = data.transcript_file;
        state.videoName = data.video_name;
        renderTranscript(data.transcript);
        setStatus("status-1", "ok", "Transkripsjon ferdig.");
        setStep("step-1", "done"); setBadge("badge-1", "Ferdig");
        setStep("step-2", "active"); setBadge("badge-2", "Klar");
        $("btn-translate").disabled = false;
        log("Transkribering fullført.");
    } catch (e) {
        setStatus("status-1", "error", e.message);
        $("btn-transcribe").disabled = false;
        log("FEIL: " + e.message);
    }
});

function renderTranscript(t) {
    const chunks = (t && t.chunks) || [];
    const el = $("no-preview");
    if (!chunks.length) { el.innerHTML = '<div class="placeholder">Ingen segmenter funnet.</div>'; return; }
    el.innerHTML = chunks.map((c) =>
        `<div class="chunk"><span class="chunk-time">${(c.timestamp?.[0] ?? 0).toFixed(1)}s</span><span>${escapeHtml(c.text || "")}</span></div>`
    ).join("");
}

/* ---------- Steg 2 → 3: oversettelse ---------- */
$("btn-translate").addEventListener("click", async () => {
    $("btn-translate").disabled = true;
    const engine = $("translate-engine").value;
    setStatus("status-2", "loading", "Oversetter til svensk…");
    log(`Oversetter (${engine})…`);
    const fd = new FormData();
    fd.append("transcript_file", state.noFile);
    fd.append("engine", engine);
    fd.append("api_key", getKey());
    try {
        const data = await postJSON("/api/translate", fd);
        state.svFile = data.transcript_file;
        $("sv-edit").value = JSON.stringify(data.transcript, null, 2);
        setStatus("status-2", "ok", "Oversettelse ferdig.");
        setStep("step-2", "done"); setBadge("badge-2", "Ferdig");
        unlockDub("Klar");
        log("Oversettelse fullført.");
    } catch (e) {
        setStatus("status-2", "error", e.message);
        $("btn-translate").disabled = false;
        log("FEIL: " + e.message);
    }
});

function unlockDub(badge) {
    setStep("step-3", "active");
    setBadge("badge-3", badge);
    $("btn-dub").disabled = false;
}

/* ---------- Ekspertmodus ---------- */
$("btn-expert").addEventListener("click", async () => {
    if (!state.videoFile) { alert("Velg en kildevideo først, så vi vet hva som skal dubbes."); return; }
    setStatus("status-1", "loading", "Laster opp video…");
    const fd = new FormData();
    fd.append("video", state.videoFile);
    try {
        const data = await postJSON("/api/upload-video", fd);
        state.videoName = data.video_name;
        setStatus("status-1", "ok", "Video lastet opp. Lim inn svensk JSON i steg 3.");
        setStep("step-1", "done"); setBadge("badge-1", "Ferdig");
        setStep("step-2", "locked"); setBadge("badge-2", "Hoppet over");
        unlockDub("Manuell");
        $("sv-edit").focus();
        log("Ekspertmodus: video lastet opp, klar for manuell svensk JSON.");
    } catch (e) {
        setStatus("status-1", "error", e.message);
    }
});

/* ---------- Stemmevalg: vis OpenRouter-felt ---------- */
$("voice-select").addEventListener("change", (e) => {
    $("openrouter-tts").hidden = e.target.value !== "openrouter_api";
});

/* ---------- Steg 3: dubbing ---------- */
$("btn-dub").addEventListener("click", async () => {
    const svText = $("sv-edit").value.trim();
    if (!svText) { alert("Mangler svensk transkripsjon."); return; }
    try { JSON.parse(svText); } catch { alert("Den svenske transkripsjonen er ikke gyldig JSON."); return; }

    $("btn-dub").disabled = true;
    setStatus("status-3", "loading", "Genererer svensk lyd og setter sammen video…");
    log("Starter dubbing…");
    const fd = new FormData();
    fd.append("video_name", state.videoName);
    fd.append("sv_json", svText);
    fd.append("voice", $("voice-select").value);
    fd.append("test_mode", $("test-mode").checked);
    fd.append("api_key", getKey());
    fd.append("openrouter_model", $("or-model").value);
    fd.append("openrouter_voice", $("or-voice").value);
    try {
        const data = await postJSON("/api/dub", fd);
        hide("status-3");
        setStep("step-3", "done"); setBadge("badge-3", "Ferdig");
        const url = "/output/" + encodeURIComponent(data.file) + "?t=" + Date.now();
        $("result-video").src = url;
        $("btn-download").href = url;
        $("btn-download").setAttribute("download", data.file);
        $("result-card").hidden = false;
        $("result-card").scrollIntoView({ behavior: "smooth" });
        log("Dubbing fullført: " + data.file);
    } catch (e) {
        setStatus("status-3", "error", e.message);
        $("btn-dub").disabled = false;
        log("FEIL: " + e.message);
    }
});

/* ---------- Tospråklig voiceover ---------- */
$("btn-load-json").addEventListener("click", () => $("dual-json-input").click());
$("dual-json-input").addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = (ev) => { $("dual-json").value = ev.target.result; log("JSON-fil lastet inn."); };
    reader.readAsText(f);
});

$("btn-dual").addEventListener("click", async () => {
    const txt = $("dual-json").value.trim();
    if (!txt) { alert("Lim inn eller last opp en JSON-transkripsjon."); return; }
    try { JSON.parse(txt); } catch { alert("Innholdet er ikke gyldig JSON."); return; }
    if (!getKey()) { alert("Tospråklig voiceover krever en OpenRouter-nøkkel. Legg den inn under ⚙."); return; }

    $("btn-dual").disabled = true;
    setStatus("status-dual", "loading", "Oversetter og genererer norsk + svensk lyd…");
    const fd = new FormData();
    fd.append("json_text", txt);
    fd.append("voice", $("dual-voice").value);
    fd.append("model_id", $("dual-model").value);
    fd.append("api_key", getKey());
    try {
        const data = await postJSON("/api/dual-vo", fd);
        hide("status-dual");
        $("dual-result").hidden = false;
        const noUrl = "/output/" + encodeURIComponent(data.norwegian_audio) + "?t=" + Date.now();
        const svUrl = "/output/" + encodeURIComponent(data.swedish_audio) + "?t=" + Date.now();
        $("audio-no").src = noUrl; $("dl-no").href = noUrl; $("dl-no").setAttribute("download", data.norwegian_audio);
        $("audio-sv").src = svUrl; $("dl-sv").href = svUrl; $("dl-sv").setAttribute("download", data.swedish_audio);
        $("text-no").textContent = data.norwegian_text;
        $("text-sv").textContent = data.swedish_text;
        log("Tospråklig voiceover ferdig.");
    } catch (e) {
        setStatus("status-dual", "error", e.message);
        log("FEIL: " + e.message);
    } finally {
        $("btn-dual").disabled = false;
    }
});

/* ---------- Hjelpere ---------- */
async function postJSON(url, formData) {
    const res = await fetch(url, { method: "POST", body: formData });
    let data;
    try { data = await res.json(); } catch { throw new Error(`Serverfeil (${res.status}).`); }
    if (data.status !== "success") throw new Error(data.message || `Feil (${res.status}).`);
    return data;
}
function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- Init ---------- */
loadHealth();
