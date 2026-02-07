const root = document.querySelector(".container");
const sceneId = root.dataset.sceneId;

const sceneTitleEl = document.getElementById("scene-title");
const statusBadgeEl = document.getElementById("status-badge");
const scriptPanelEl = document.getElementById("script-panel");
const startBtn = document.getElementById("start-btn");
const endBtn = document.getElementById("end-btn");
const micToggleBtn = document.getElementById("mic-toggle-btn");
const micStatusEl = document.getElementById("mic-status");
const lockedOutputEl = document.getElementById("locked-output");
const lockedScriptTextEl = document.getElementById("locked-script-text");

let scene = null;
let state = null;
let pollHandle = null;

let micEnabled = false;
let mediaStream = null;
let audioContext = null;
let sourceNode = null;
let processorNode = null;
let sinkGainNode = null;

let agentSocket = null;
let agentSocketReady = false;
let agentStreamId = null;

let playbackNextTime = 0;
const playbackSources = new Set();

const TARGET_SAMPLE_RATE = 16000;

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

function setMicStatus(text) {
  micStatusEl.textContent = text;
}

function canCaptureNow() {
  return Boolean(state && (state.status === "RUNNING" || state.status === "READY_TO_LOCK"));
}

function activeBeatText(beat) {
  if (!beat) {
    return "";
  }
  const activeVariant = beat.active_variant_id
    ? beat.variants.find((variant) => variant.id === beat.active_variant_id)
    : null;
  if (beat.speaker === "AI") {
    return (activeVariant ? activeVariant.text : beat.canonical) || "";
  }
  return beat.canonical || "";
}

function lineLabel(beat) {
  if (!beat) {
    return "";
  }
  return beat.character || beat.speaker || "";
}

function resolveCurrentBeatIndex() {
  if (!state || !Number.isInteger(state.beat_index)) {
    return 0;
  }
  return Math.max(0, state.beat_index);
}

function resolveOpeningInstruction() {
  if (!scene || !Array.isArray(scene.beats) || scene.beats.length === 0) {
    return {
      introduction: "",
      instruction: "Do not introduce yourself. Wait for the user to speak.",
    };
  }

  const currentIndex = Math.min(resolveCurrentBeatIndex(), scene.beats.length - 1);
  const currentBeat = scene.beats[currentIndex];
  if (currentBeat && currentBeat.speaker === "AI") {
    const text = activeBeatText(currentBeat).trim();
    if (text) {
      return {
        introduction: text,
        instruction: `First utterance must be this exact line from the script: "${lineLabel(currentBeat)}: ${text}"`,
      };
    }
  }

  return {
    introduction: "",
    instruction: "The current script beat is not yours. Stay silent until user audio arrives.",
  };
}

function buildSceneScriptText() {
  if (!scene || !Array.isArray(scene.beats)) {
    return "";
  }
  return scene.beats
    .map((beat) => {
      const text = activeBeatText(beat);
      const label = lineLabel(beat);
      return `${label}: ${text || ""}`;
    })
    .join("\n");
}

function buildAgentSystemPrompt() {
  const aiName = (scene && scene.characters && scene.characters.AI) ? scene.characters.AI : "AI";
  const scriptText = buildSceneScriptText();
  const opening = resolveOpeningInstruction();
  return [
    "You are READER, a live voice rehearsal partner.",
    `Perform only the character: ${aiName}.`,
    "Never greet, introduce yourself, or explain rules.",
    "Follow the script beats in order.",
    opening.instruction,
    "If the user says commands starting with 'reader', treat them as direction.",
    "If user says 'lock this version', end the call promptly.",
    "Script:",
    scriptText,
  ].join("\n");
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
    const text = activeBeatText(beat);
    const label = lineLabel(beat);
    li.textContent = `${label}: ${text || ""}`;
    scriptPanelEl.appendChild(li);
  });
}

function hasScriptEdits() {
  if (!state || !Array.isArray(state.director_events)) {
    return false;
  }
  return state.director_events.some((event) => {
    const actions = event.meta && Array.isArray(event.meta.actions) ? event.meta.actions : [];
    return actions.some(
      (action) => typeof action === "string" && (action.startsWith("variant:") || action.startsWith("rewrite:")),
    );
  });
}

function renderLockedOutput() {
  if (!state || state.status !== "LOCKED" || !hasScriptEdits()) {
    lockedOutputEl.hidden = true;
    return;
  }
  lockedOutputEl.hidden = false;
  lockedScriptTextEl.textContent = state.locked_script_text || "";
}

function syncUi() {
  if (!state) {
    return;
  }
  updateStatusBadge(state.status);
  renderScript();
  renderLockedOutput();
  startBtn.disabled = state.status === "RUNNING" || state.status === "READY_TO_LOCK" || state.status === "LOCKED";
  endBtn.disabled = !(state.status === "RUNNING" || state.status === "READY_TO_LOCK");
  micToggleBtn.disabled = !canCaptureNow();
}

async function loadScene() {
  scene = await api(`/api/scenes/${sceneId}`);
  sceneTitleEl.textContent = scene.title;
  renderScript();
}

async function refreshState() {
  state = await api(`/api/scenes/${sceneId}/state`);
  if (state.status === "LOCKED" && micEnabled) {
    disableMic();
  }
  syncUi();
}

async function startScene() {
  await api(`/api/scenes/${sceneId}/start`, { method: "POST" });
  await loadScene();
  await refreshState();
}

async function endScene() {
  await api(`/api/scenes/${sceneId}/end`, { method: "POST" });
  await loadScene();
  await refreshState();
  if (micEnabled) {
    disableMic();
  }
}

function downsampleBuffer(inputFloat32, inputRate, outputRate) {
  if (inputRate === outputRate || inputRate < outputRate) {
    return inputFloat32;
  }

  const ratio = inputRate / outputRate;
  const outputLength = Math.max(1, Math.round(inputFloat32.length / ratio));
  const result = new Float32Array(outputLength);
  let offsetResult = 0;
  let offsetBuffer = 0;

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let accum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < inputFloat32.length; i += 1) {
      accum += inputFloat32[i];
      count += 1;
    }
    result[offsetResult] = count > 0 ? accum / count : 0;
    offsetResult += 1;
    offsetBuffer = nextOffsetBuffer;
  }

  return result;
}

function floatTo16BitPCM(float32Data) {
  const out = new Int16Array(float32Data.length);
  for (let i = 0; i < float32Data.length; i += 1) {
    const s = Math.max(-1, Math.min(1, float32Data[i]));
    out[i] = s < 0 ? Math.round(s * 32768) : Math.round(s * 32767);
  }
  return out;
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 8192;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode.apply(null, chunk);
  }
  return btoa(binary);
}

function base64ToBytes(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function pcm16leBytesToFloat32(bytes) {
  const sampleCount = Math.floor(bytes.length / 2);
  const out = new Float32Array(sampleCount);
  for (let i = 0; i < sampleCount; i += 1) {
    const lo = bytes[i * 2];
    const hi = bytes[i * 2 + 1];
    let sample = (hi << 8) | lo;
    if (sample & 0x8000) {
      sample -= 0x10000;
    }
    out[i] = sample / 32768;
  }
  return out;
}

function clearPlayback() {
  if (audioContext) {
    playbackNextTime = audioContext.currentTime;
  } else {
    playbackNextTime = 0;
  }
  for (const source of playbackSources) {
    try {
      source.stop();
    } catch (err) {
      // ignore
    }
  }
  playbackSources.clear();
}

function playAgentAudioPayload(payload) {
  if (!audioContext || !payload) {
    return;
  }
  const bytes = base64ToBytes(payload);
  const samples = pcm16leBytesToFloat32(bytes);
  if (!samples.length) {
    return;
  }
  const buffer = audioContext.createBuffer(1, samples.length, TARGET_SAMPLE_RATE);
  buffer.copyToChannel(samples, 0, 0);
  const source = audioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(audioContext.destination);

  const startAt = Math.max(audioContext.currentTime, playbackNextTime);
  source.start(startAt);
  playbackNextTime = startAt + buffer.duration;
  playbackSources.add(source);
  source.onended = () => {
    playbackSources.delete(source);
  };
}

function maybeParseAgentEvent(raw) {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  if (typeof raw.event === "string") {
    return raw;
  }
  if (typeof raw.type === "string") {
    return { event: raw.type, ...raw };
  }
  return null;
}

async function connectAgentSocket() {
  const session = await api(`/api/scenes/${sceneId}/agent-session`);

  return new Promise((resolve, reject) => {
    let settled = false;
    agentSocket = new WebSocket(session.ws_url);

    const setSettledResolve = () => {
      if (!settled) {
        settled = true;
        resolve();
      }
    };

    const setSettledReject = (err) => {
      if (!settled) {
        settled = true;
        reject(err);
      }
    };

    agentSocket.onopen = () => {
      const streamId = (window.crypto && typeof window.crypto.randomUUID === "function")
        ? window.crypto.randomUUID()
        : `stream-${Date.now()}`;
      agentStreamId = streamId;
      const systemPrompt = buildAgentSystemPrompt();
      const opening = resolveOpeningInstruction();
      const startEvent = {
        event: "start",
        stream_id: streamId,
        config: { input_format: session.input_format || "pcm_16000" },
        agent: {
          system_prompt: systemPrompt,
          introduction: opening.introduction,
        },
        metadata: {
          scene_id: sceneId,
          scene_title: scene && scene.title ? scene.title : "",
        },
      };
      const voiceId = scene && scene.voice && scene.voice.ai_voice_id;
      if (voiceId) {
        startEvent.config.voice_id = voiceId;
      }
      agentSocket.send(JSON.stringify(startEvent));
      setMicStatus("Connecting to Cartesia agent...");
    };

    agentSocket.onmessage = async (msgEvent) => {
      let payload = null;
      try {
        payload = JSON.parse(msgEvent.data);
      } catch (err) {
        return;
      }
      const evt = maybeParseAgentEvent(payload);
      if (!evt) {
        return;
      }

      if (evt.event === "ack") {
        agentSocketReady = true;
        setMicStatus("Listening (agent live)");
        setSettledResolve();
        return;
      }

      if (evt.event === "media_output") {
        if (evt.media && typeof evt.media.payload === "string") {
          playAgentAudioPayload(evt.media.payload);
        }
        return;
      }

      if (evt.event === "clear") {
        clearPlayback();
        return;
      }

      if (evt.event === "error") {
        setMicStatus(`Agent error: ${evt.message || "unknown error"}`);
      }
    };

    agentSocket.onerror = () => {
      if (!agentSocketReady) {
        setSettledReject(new Error("Failed to connect to Cartesia agent stream."));
      } else {
        setMicStatus("Agent socket error");
      }
    };

    agentSocket.onclose = () => {
      agentSocketReady = false;
      if (micEnabled) {
        setMicStatus("Agent stream closed");
      }
      if (!settled) {
        setSettledReject(new Error("Agent stream closed before ready."));
      }
    };
  });
}

function attachAudioProcessor() {
  processorNode = audioContext.createScriptProcessor(2048, 1, 1);
  sourceNode = audioContext.createMediaStreamSource(mediaStream);
  sinkGainNode = audioContext.createGain();
  sinkGainNode.gain.value = 0;

  sourceNode.connect(processorNode);
  processorNode.connect(sinkGainNode);
  sinkGainNode.connect(audioContext.destination);

  processorNode.onaudioprocess = (event) => {
    if (!micEnabled || !agentSocketReady || !canCaptureNow() || !agentStreamId || !agentSocket) {
      return;
    }
    if (agentSocket.readyState !== WebSocket.OPEN) {
      return;
    }
    const channelData = event.inputBuffer.getChannelData(0);
    const normalized = downsampleBuffer(channelData, audioContext.sampleRate, TARGET_SAMPLE_RATE);
    const pcm = floatTo16BitPCM(normalized);
    if (!pcm.length) {
      return;
    }
    const bytes = new Uint8Array(pcm.buffer);
    const payload = bytesToBase64(bytes);
    agentSocket.send(
      JSON.stringify({
        event: "media_input",
        stream_id: agentStreamId,
        media: { payload },
      }),
    );
  };
}

async function enableMic() {
  if (!canCaptureNow()) {
    throw new Error("Click Start Scene first.");
  }
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  audioContext = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
  await audioContext.resume();
  clearPlayback();
  await connectAgentSocket();
  attachAudioProcessor();

  micEnabled = true;
  micToggleBtn.textContent = "Disable Mic";
  setMicStatus("Listening (agent live)");
}

function cleanupAudioNodes() {
  if (processorNode) {
    try {
      processorNode.disconnect();
    } catch (err) {
      // ignore
    }
  }
  if (sourceNode) {
    try {
      sourceNode.disconnect();
    } catch (err) {
      // ignore
    }
  }
  if (sinkGainNode) {
    try {
      sinkGainNode.disconnect();
    } catch (err) {
      // ignore
    }
  }
  processorNode = null;
  sourceNode = null;
  sinkGainNode = null;
}

function closeAgentSocket() {
  if (!agentSocket) {
    return;
  }
  try {
    if (agentSocket.readyState === WebSocket.OPEN && agentStreamId) {
      agentSocket.send(JSON.stringify({ event: "stop", stream_id: agentStreamId }));
    }
    agentSocket.close();
  } catch (err) {
    // ignore
  }
  agentSocket = null;
  agentSocketReady = false;
  agentStreamId = null;
}

function disableMic() {
  micEnabled = false;
  micToggleBtn.textContent = "Enable Mic (Agent)";
  setMicStatus("Mic disabled");

  closeAgentSocket();
  clearPlayback();
  cleanupAudioNodes();

  if (mediaStream) {
    for (const track of mediaStream.getTracks()) {
      track.stop();
    }
  }
  mediaStream = null;

  if (audioContext) {
    audioContext.close();
  }
  audioContext = null;
}

startBtn.addEventListener("click", async () => {
  try {
    await startScene();
    if (!micEnabled) {
      await enableMic();
    }
  } catch (err) {
    console.error(err);
    setMicStatus(`Start error: ${err.message}`);
  }
});

endBtn.addEventListener("click", async () => {
  try {
    endBtn.disabled = true;
    setMicStatus("Ending scene...");
    await endScene();
  } catch (err) {
    console.error(err);
    setMicStatus(`End error: ${err.message}`);
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
    setMicStatus(`Mic error: ${err.message}`);
    disableMic();
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
