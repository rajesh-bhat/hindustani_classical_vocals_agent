/**
 * script.js — Raaga Guru Session (voice + text modes)
 *
 * Voice mode audio pipeline:
 *   Mic (getUserMedia) → AudioContext @ 16kHz → ScriptProcessorNode
 *   → Int16 PCM → binary WebSocket → FastAPI → Gemini Live API
 *
 *   Gemini Live API → FastAPI → WebSocket JSON { audio: base64 24kHz PCM }
 *   → AudioContext @ 24kHz → BufferSource → speakers
 *
 * Text mode: no mic/speaker — connects with ?mode=text, exchanges
 * { text } / { output_text } JSON frames only.
 */

// ── Constants ─────────────────────────────────────────────────────────────────
const AUDIO_INPUT_RATE      = 16_000;
const AUDIO_OUTPUT_RATE     = 24_000;
const SCRIPT_PROCESSOR_SIZE = 4_096;

// ── DOM references ────────────────────────────────────────────────────────────
const startBtn           = document.getElementById('start-btn');
const startBtnLabel      = document.getElementById('start-btn-label');
const stopBtn            = document.getElementById('stop-btn');
const liveTranscript     = document.getElementById('live-transcript');
const liveIndicator      = document.getElementById('live-indicator');
const liveStatusLabel    = document.getElementById('live-status-label');
const clearTranscriptBtn = document.getElementById('clear-transcript-btn');
const visualizerContainer = document.getElementById('visualizer-container');
const visualizerCanvas   = document.getElementById('audio-visualizer');
const listeningLabel     = document.getElementById('listening-label');
const sessionHint        = document.getElementById('session-hint');
const modeVoiceBtn       = document.getElementById('mode-voice-btn');
const modeTextBtn        = document.getElementById('mode-text-btn');
const textInputRow       = document.getElementById('text-input-row');
const textInput          = document.getElementById('text-input');
const textSendBtn        = document.getElementById('text-send-btn');

// ── Session state ─────────────────────────────────────────────────────────────
let isLiveActive    = false;
let sessionMode     = 'voice'; // 'voice' | 'text'
let liveStream      = null;
let liveSocket      = null;

// Input audio
let inAudioCtx      = null;
let scriptProcessor = null;
let analyser        = null;

// Output audio
let outAudioCtx     = null;
let audioQueue      = [];
let isPlaying       = false;

// Transcript
let lastTranscriptRole = null;

// Visualizer
let animFrameId     = null;

// ── Event listeners ───────────────────────────────────────────────────────────
startBtn.addEventListener('click', startLiveSession);
stopBtn.addEventListener('click', stopLiveSession);
clearTranscriptBtn.addEventListener('click', clearTranscript);

// Mode toggle — only switchable before a session starts
modeVoiceBtn.addEventListener('click', () => setMode('voice'));
modeTextBtn.addEventListener('click', () => setMode('text'));

// Text input — send typed queries in text mode
textSendBtn.addEventListener('click', sendTypedText);
textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendTypedText();
});

// ── Public actions ────────────────────────────────────────────────────────────

function setMode(mode) {
    if (isLiveActive || mode === sessionMode) return;
    sessionMode = mode;
    modeVoiceBtn.classList.toggle('active', mode === 'voice');
    modeTextBtn.classList.toggle('active', mode === 'text');
    startBtnLabel.textContent = mode === 'voice' ? 'Talk to Guru' : 'Chat with Guru';
    startBtn.querySelector('.btn-icon').textContent = mode === 'voice' ? '🎙️' : '💬';
    sessionHint.textContent = mode === 'voice'
        ? 'Ask about any raaga — its structure, swara rules, aaroh-avaroh, pakad, time of day, and how it differs from similar raagas.'
        : 'Type your question below — ask about any raaga\'s structure, swara rules, aaroh-avaroh, pakad, and more.';
}

function sendTypedText() {
    const query = textInput.value.trim();
    if (!query) return;
    textInput.value = '';

    if (isLiveActive && liveSocket?.readyState === WebSocket.OPEN) {
        liveSocket.send(JSON.stringify({ text: query }));
        appendTranscript('user', query);
    } else if (!isLiveActive) {
        startLiveSession().then(() => {
            setTimeout(() => {
                if (liveSocket?.readyState === WebSocket.OPEN) {
                    liveSocket.send(JSON.stringify({ text: query }));
                    appendTranscript('user', query);
                }
            }, 1500);
        });
    }
}

function clearTranscript() {
    liveTranscript.innerHTML =
        '<p class="transcript-placeholder">Start a session and ask your question — for example:<br>' +
        '<em>"Tell me about Raag Yaman"</em> or <em>"What is the difference between Bhupali and Deshkar?"</em></p>';
    lastTranscriptRole = null;
}

async function startLiveSession() {
    if (isLiveActive) return;

    // 1. Acquire microphone (voice mode only — text mode needs no audio)
    if (sessionMode === 'voice') {
        try {
            liveStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (err) {
            console.error('[Live] getUserMedia failed:', err);
            showError('Microphone access is required. Please allow access and try again.');
            return;
        }
    }

    // 2. Update UI state
    isLiveActive = true;
    startBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');
    modeVoiceBtn.disabled = true;
    modeTextBtn.disabled = true;
    if (sessionMode === 'voice') {
        visualizerContainer.classList.remove('hidden');
    } else {
        textInputRow.classList.remove('hidden');
    }
    sessionHint.classList.add('hidden');
    setLiveStatus(true);
    liveTranscript.innerHTML = '';
    lastTranscriptRole = null;
    document.getElementById('conn-error-banner')?.remove();

    // 3. Initialise output audio context (voice mode only)
    if (sessionMode === 'voice') {
        outAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: AUDIO_OUTPUT_RATE });
        audioQueue  = [];
        isPlaying   = false;
    }

    // 4. Open WebSocket
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const modeParam = sessionMode === 'text' ? '?mode=text' : '';
    liveSocket = new WebSocket(`${protocol}//${location.host}/ws/live${modeParam}`);
    liveSocket.binaryType = 'arraybuffer';

    liveSocket.onopen    = handleSocketOpen;
    liveSocket.onmessage = handleSocketMessage;
    liveSocket.onerror   = handleSocketError;
    liveSocket.onclose   = handleSocketClose;

    if (sessionMode === 'text') {
        textInput.focus();
    }
}

function stopLiveSession() {
    if (!isLiveActive) return;
    isLiveActive = false;

    if (liveSocket?.readyState === WebSocket.OPEN) {
        try { liveSocket.send(JSON.stringify({ audioStreamEnd: true })); } catch (_) {}
        liveSocket.close(1000, 'User stopped session');
    }

    teardown();
}

// ── WebSocket handlers ────────────────────────────────────────────────────────

function handleSocketOpen() {
    console.log('[Live] WebSocket connected');
    if (sessionMode === 'voice') {
        startAudioCapture();
        startVisualizer();
    }
}

function handleSocketMessage(event) {
    if (event.data instanceof ArrayBuffer) return;

    let data;
    try {
        data = JSON.parse(event.data);
    } catch (err) {
        console.warn('[Live] Non-JSON message; ignoring');
        return;
    }

    if (data.interrupted) {
        audioQueue.length = 0;
        isPlaying = false;
    }

    if (data.audio) {
        const f32 = decodeBase64Pcm(data.audio);
        if (f32) {
            audioQueue.push(f32);
            schedulePlayback();
        }
    }

    if (data.debug_tool) appendToolLoaded(data.debug_tool, data.debug_args);

    if (data.input_text)  appendTranscript('user',  data.input_text);
    if (data.output_text) appendTranscript('agent', data.output_text);
}

function handleSocketError(event) {
    console.error('[Live] WebSocket error:', event);
}

function handleSocketClose(event) {
    console.log(`[Live] WebSocket closed (code=${event.code}, clean=${event.wasClean})`);
    if (isLiveActive) {
        isLiveActive = false;
        teardown();
        showConnectionError(`Session ended unexpectedly. Click "${startBtnLabel.textContent}" to reconnect.`);
    }
}

// ── Audio capture (input) ─────────────────────────────────────────────────────

function startAudioCapture() {
    inAudioCtx    = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: AUDIO_INPUT_RATE });
    const source  = inAudioCtx.createMediaStreamSource(liveStream);
    scriptProcessor = inAudioCtx.createScriptProcessor(SCRIPT_PROCESSOR_SIZE, 1, 1);

    // Analyser for visualizer
    analyser = inAudioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    source.connect(scriptProcessor);
    scriptProcessor.connect(inAudioCtx.destination);

    scriptProcessor.onaudioprocess = (e) => {
        if (!isLiveActive || liveSocket?.readyState !== WebSocket.OPEN) return;
        const f32 = e.inputBuffer.getChannelData(0);
        const i16 = float32ToInt16(f32);
        liveSocket.send(i16.buffer);
    };
}

// ── Audio playback (output) ───────────────────────────────────────────────────

function schedulePlayback() {
    if (isPlaying || !audioQueue.length) return;
    isPlaying = true;

    const f32 = audioQueue.shift();
    const buf = outAudioCtx.createBuffer(1, f32.length, AUDIO_OUTPUT_RATE);
    buf.getChannelData(0).set(f32);

    const src = outAudioCtx.createBufferSource();
    src.buffer = buf;
    src.connect(outAudioCtx.destination);
    src.onended = () => {
        isPlaying = false;
        schedulePlayback();
    };
    src.start();
}

// ── Audio Visualizer ──────────────────────────────────────────────────────────

function startVisualizer() {
    const canvas = visualizerCanvas;
    const ctx = canvas.getContext('2d');

    function resizeCanvas() {
        canvas.width = canvas.offsetWidth * window.devicePixelRatio;
        canvas.height = canvas.offsetHeight * window.devicePixelRatio;
        ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    }
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    const w = canvas.offsetWidth;
    const h = canvas.offsetHeight;
    const barCount = 64;
    const barW = (w / barCount) * 0.6;
    const gap  = (w / barCount) * 0.4;

    function draw() {
        if (!isLiveActive || !analyser) return;
        animFrameId = requestAnimationFrame(draw);

        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(dataArray);

        ctx.clearRect(0, 0, w, h);

        for (let i = 0; i < barCount; i++) {
            const val = dataArray[i] / 255;
            const barH = Math.max(2, val * h * 0.9);
            const x = i * (barW + gap);
            const y = (h - barH) / 2;

            // Gradient from saffron to gold
            const hue = 30 + (i / barCount) * 15;
            const alpha = 0.3 + val * 0.7;
            ctx.fillStyle = `hsla(${hue}, 90%, 60%, ${alpha})`;
            ctx.beginPath();
            ctx.roundRect(x, y, barW, barH, 2);
            ctx.fill();
        }
    }

    draw();
}

function stopVisualizer() {
    if (animFrameId) {
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
    }
}

// ── Teardown ──────────────────────────────────────────────────────────────────

function teardown() {
    stopVisualizer();

    if (scriptProcessor) { scriptProcessor.disconnect(); scriptProcessor = null; }
    if (inAudioCtx)      { inAudioCtx.close().catch(() => {}); inAudioCtx = null; }
    analyser = null;

    audioQueue.length = 0;
    isPlaying = false;
    if (outAudioCtx) { outAudioCtx.close().catch(() => {}); outAudioCtx = null; }

    if (liveStream) {
        liveStream.getTracks().forEach(t => t.stop());
        liveStream = null;
    }

    startBtn.classList.remove('hidden');
    stopBtn.classList.add('hidden');
    visualizerContainer.classList.add('hidden');
    textInputRow.classList.add('hidden');
    modeVoiceBtn.disabled = false;
    modeTextBtn.disabled = false;
    sessionHint.classList.remove('hidden');
    setLiveStatus(false);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function decodeBase64Pcm(b64) {
    try {
        const bin = atob(b64);
        const u8  = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
        const i16 = new Int16Array(u8.buffer);
        const f32 = new Float32Array(i16.length);
        for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32_768;
        return f32;
    } catch (err) {
        console.warn('[Live] Failed to decode PCM audio:', err.message);
        return null;
    }
}

function float32ToInt16(f32) {
    const i16 = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) {
        const s = Math.max(-1, Math.min(1, f32[i]));
        i16[i]  = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return i16;
}

function appendTranscript(role, text) {
    const placeholder = liveTranscript.querySelector('.transcript-placeholder');
    if (placeholder) placeholder.remove();

    const cssClass = role === 'user' ? 'transcript-user' : 'transcript-agent';
    const label    = role === 'user' ? '🎤 You' : '🎵 Guru';

    if (role === lastTranscriptRole) {
        const existing = liveTranscript.lastElementChild;
        if (existing && existing.classList.contains(cssClass)) {
            existing.textContent += ' ' + text.trim();
            liveTranscript.scrollTop = liveTranscript.scrollHeight;
            return;
        }
    }

    lastTranscriptRole = role;
    const el = document.createElement('div');
    el.className = `transcript-entry ${cssClass}`;
    el.textContent = `${label}: ${text.trim()}`;
    liveTranscript.appendChild(el);
    liveTranscript.scrollTop = liveTranscript.scrollHeight;
}

// Human-readable labels for each backend knowledge tool.
const TOOL_LABELS = {
    lookup_raaga:        'Raaga details',
    list_raagas:         'Raaga index',
    lookup_fundamentals: 'Music theory',
};

function appendToolLoaded(tool, args) {
    const placeholder = liveTranscript.querySelector('.transcript-placeholder');
    if (placeholder) placeholder.remove();

    const label = TOOL_LABELS[tool] || tool;
    const detail = args && args.raaga_name ? ` · ${args.raaga_name}` : '';

    const el = document.createElement('div');
    el.className = 'transcript-tool';
    el.textContent = `📚 Loaded knowledge: ${label}${detail}`;
    liveTranscript.appendChild(el);
    liveTranscript.scrollTop = liveTranscript.scrollHeight;

    // A tool event breaks the user/agent grouping run.
    lastTranscriptRole = null;
}

function setLiveStatus(active) {
    liveIndicator.classList.toggle('active', active);
    liveIndicator.classList.toggle('idle', !active);
    liveStatusLabel.textContent = active ? 'Live' : 'Ready';
    if (!active) lastTranscriptRole = null;
}

function showConnectionError(message) {
    document.getElementById('conn-error-banner')?.remove();
    const banner = document.createElement('div');
    banner.id = 'conn-error-banner';
    banner.className = 'error-banner';
    banner.textContent = '⚠️ ' + message;
    const card = document.getElementById('session-card');
    if (card?.parentNode) {
        card.parentNode.insertBefore(banner, card.nextSibling);
    }
    setTimeout(() => banner.remove(), 8_000);
}

function showError(message) {
    alert(message);
}
