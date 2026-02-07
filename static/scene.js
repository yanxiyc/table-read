const root = document.querySelector(".container");
const sceneId = root.dataset.sceneId;

const sceneTitleEl = document.getElementById("scene-title");
const statusBadgeEl = document.getElementById("status-badge");
const scriptPanelEl = document.getElementById("script-panel");
const transcriptPanelEl = document.getElementById("transcript-panel");
const startBtn = document.getElementById("start-btn");
const micToggleBtn = document.getElementById("mic-toggle-btn");
const micStatusEl = document.getElementById("mic-status");
const lockedOutputEl = document.getElementById("locked-output");
const lockedScriptTextEl = document.getElementById("locked-script-text");
const lockedNotesEl = document.getElementById("locked-notes");
const audioPlayer = document.getElementById("ai-audio-player");

let scene = null;
let state = null;
let pollHandle = null;
let playedAudioEventIds = new Set();
let audioQueue = [];
let isAudioPlaying = false;

let micEnabled = false;
let mediaRecorder = null;
let audioChunks = [];
let mediaStream = null;
let analyser = null;
let audioContext = null;
let levelFrame = null;
let isRecording = false;
let lastSpeechAt = 0;
let recordingStartAt = 0;
let uploadBusy = false;
let uploadQueue = [];

const VOICE_THRESHOLD = 0.015;
const SILENCE_MS = 900;
const MIN_RECORD_MS = 250;

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

function updateStatusBadge(status) {
  statusBadgeEl.textContent = status;
  statusBadgeEl.className = `badge ${status.toLowerCase()}`;
}

function renderScript() {
  if (!scene) {
    return;
  }
  scriptPanelEl.innerHTML = "";
  scene.beats.forEach((beat, idx) => {
    const li = document.createElement("li");
    li.className = "script-item";
    if (state && idx === state.beat_index) {
      li.classList.add("current");
    }
    const activeVariant = beat.active_variant_id
      ? beat.variants.find((variant) => variant.id === beat.active_variant_id)
      : null;
    const text = beat.speaker === "AI"
      ? (activeVariant ? activeVariant.text : beat.canonical)
      : (beat.canonical || "");
    const label = beat.character || beat.speaker;
    li.textContent = `${label}: ${text || ""}`;
    scriptPanelEl.appendChild(li);
  });
}

function renderTranscript() {
  if (!state) {
    return;
  }
  transcriptPanelEl.innerHTML = "";
  for (const event of state.transcript) {
    const line = document.createElement("div");
    line.className = "transcript-line";
    const speaker = document.createElement("span");
    speaker.className = "speaker";
    speaker.textContent = (event.meta && event.meta.character) || event.speaker;
    const text = document.createElement("span");
    text.textContent = event.text;
    line.appendChild(speaker);
    line.appendChild(text);
    transcriptPanelEl.appendChild(line);
  }
  transcriptPanelEl.scrollTop = transcriptPanelEl.scrollHeight;
}

function renderLockedOutput() {
  if (!state || state.status !== "LOCKED") {
    lockedOutputEl.hidden = true;
    return;
  }
  lockedOutputEl.hidden = false;
  lockedScriptTextEl.textContent = state.locked_script_text || "";
  lockedNotesEl.innerHTML = "";
  for (const note of state.locked_notes || []) {
    const li = document.createElement("li");
    li.textContent = note;
    lockedNotesEl.appendChild(li);
  }
}

function enqueueNewAudio() {
  if (!state) {
    return;
  }
  for (const event of state.transcript) {
    const audioUrl = event.meta && event.meta.audio_url;
    if (event.speaker !== "AI" || !audioUrl || playedAudioEventIds.has(event.event_id)) {
      continue;
    }
    playedAudioEventIds.add(event.event_id);
    audioQueue.push(audioUrl);
  }
  playNextAudio();
}

async function playNextAudio() {
  if (isAudioPlaying || audioQueue.length === 0) {
    return;
  }
  isAudioPlaying = true;
  const src = audioQueue.shift();
  audioPlayer.src = `${src}?_ts=${Date.now()}`;
  try {
    await audioPlayer.play();
  } catch (err) {
    // Browser autoplay constraints can block play before first user interaction.
  }
}

audioPlayer.addEventListener("ended", () => {
  isAudioPlaying = false;
  playNextAudio();
});

audioPlayer.addEventListener("error", () => {
  isAudioPlaying = false;
  playNextAudio();
});

function syncUi() {
  if (!state) {
    return;
  }
  updateStatusBadge(state.status);
  renderScript();
  renderTranscript();
  renderLockedOutput();
  enqueueNewAudio();
}

async function loadScene() {
  scene = await api(`/api/scenes/${sceneId}`);
  sceneTitleEl.textContent = scene.title;
  renderScript();
}

async function refreshState() {
  state = await api(`/api/scenes/${sceneId}/state`);
  if (state.status === "LOCKED") {
    stopRecording();
  }
  syncUi();
}

async function startScene() {
  await api(`/api/scenes/${sceneId}/start`, { method: "POST" });
  await loadScene();
  await refreshState();
}

function audioLevelRms() {
  if (!analyser) {
    return 0;
  }
  const data = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(data);
  let sum = 0;
  for (let i = 0; i < data.length; i += 1) {
    sum += data[i] * data[i];
  }
  return Math.sqrt(sum / data.length);
}

function startRecording(now) {
  if (!mediaRecorder || mediaRecorder.state !== "inactive") {
    return;
  }
  audioChunks = [];
  recordingStartAt = now;
  mediaRecorder.start();
  isRecording = true;
  micStatusEl.textContent = "Listening (speech detected)";
}

function stopRecording() {
  if (!mediaRecorder || mediaRecorder.state === "inactive") {
    isRecording = false;
    return;
  }
  mediaRecorder.stop();
  isRecording = false;
  micStatusEl.textContent = "Listening";
}

async function processUploadQueue() {
  if (uploadBusy || uploadQueue.length === 0) {
    return;
  }
  uploadBusy = true;
  const blob = uploadQueue.shift();
  const formData = new FormData();
  formData.append("audio", blob, "utterance.webm");
  formData.append("client_ts", new Date().toISOString());
  try {
    const response = await api(`/api/scenes/${sceneId}/utterance`, {
      method: "POST",
      body: formData,
    });
    state = response.state;
    scene = await api(`/api/scenes/${sceneId}`);
    syncUi();
  } catch (err) {
    console.error(err);
  } finally {
    uploadBusy = false;
    processUploadQueue();
  }
}

function maybeCaptureSpeechLoop() {
  if (!micEnabled) {
    return;
  }
  const now = Date.now();
  const statusRunning = state && (state.status === "RUNNING" || state.status === "READY_TO_LOCK");
  if (statusRunning) {
    const level = audioLevelRms();
    if (level > VOICE_THRESHOLD) {
      lastSpeechAt = now;
      if (!isRecording) {
        startRecording(now);
      }
    }
    if (isRecording && now - lastSpeechAt > SILENCE_MS && now - recordingStartAt > MIN_RECORD_MS) {
      stopRecording();
    }
  } else if (isRecording) {
    stopRecording();
  }
  levelFrame = requestAnimationFrame(maybeCaptureSpeechLoop);
}

async function enableMic() {
  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioContext = new AudioContext();
  const sourceNode = audioContext.createMediaStreamSource(mediaStream);
  analyser = audioContext.createAnalyser();
  analyser.fftSize = 2048;
  sourceNode.connect(analyser);

  const preferredType = "audio/webm;codecs=opus";
  const mimeType = MediaRecorder.isTypeSupported(preferredType) ? preferredType : "";
  mediaRecorder = mimeType ? new MediaRecorder(mediaStream, { mimeType }) : new MediaRecorder(mediaStream);

  mediaRecorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size > 0) {
      audioChunks.push(event.data);
    }
  });

  mediaRecorder.addEventListener("stop", () => {
    const durationMs = Date.now() - recordingStartAt;
    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
    audioChunks = [];
    if (durationMs < MIN_RECORD_MS || blob.size < 1500) {
      return;
    }
    uploadQueue.push(blob);
    processUploadQueue();
  });

  micEnabled = true;
  micToggleBtn.textContent = "Disable Mic";
  micStatusEl.textContent = "Listening";
  maybeCaptureSpeechLoop();
}

function disableMic() {
  micEnabled = false;
  micToggleBtn.textContent = "Enable Mic";
  micStatusEl.textContent = "Mic disabled";
  if (levelFrame) {
    cancelAnimationFrame(levelFrame);
    levelFrame = null;
  }
  if (isRecording) {
    stopRecording();
  }
  if (mediaStream) {
    for (const track of mediaStream.getTracks()) {
      track.stop();
    }
  }
  if (audioContext) {
    audioContext.close();
  }
  mediaStream = null;
  analyser = null;
  mediaRecorder = null;
  audioContext = null;
}

startBtn.addEventListener("click", async () => {
  try {
    await startScene();
  } catch (err) {
    console.error(err);
  }
});

micToggleBtn.addEventListener("click", async () => {
  try {
    if (micEnabled) {
      disableMic();
    } else {
      await enableMic();
    }
  } catch (err) {
    micStatusEl.textContent = `Mic error: ${err.message}`;
  }
});

async function init() {
  await loadScene();
  await refreshState();
  pollHandle = setInterval(async () => {
    try {
      await refreshState();
      scene = await api(`/api/scenes/${sceneId}`);
      renderScript();
    } catch (err) {
      console.error(err);
      clearInterval(pollHandle);
    }
  }, 1000);
}

init();
