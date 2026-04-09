/**
 * STRBOSS Voice Widget
 * Floating mic button for the STR dashboard
 * Connects via WebSocket to the Pipecat voice agent
 */
(function() {
  'use strict';

  var WS_URL = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/voice/';
  var ws = null;
  var mediaRecorder = null;
  var audioChunks = [];
  var isRecording = false;
  var isConnected = false;
  var audioContext = null;

  // ── Inject CSS ──
  var style = document.createElement('style');
  style.textContent = [
    '#strboss-voice-widget {',
    '  position: fixed; bottom: 28px; right: 28px; z-index: 99999;',
    '  font-family: "DM Sans", system-ui, sans-serif;',
    '}',
    '#strboss-mic-btn {',
    '  width: 56px; height: 56px; border-radius: 50%;',
    '  background: linear-gradient(135deg, #1e1c18 0%, #2a2520 100%);',
    '  border: 1.5px solid rgba(201,185,154,0.3);',
    '  color: #c9b99a; cursor: pointer;',
    '  display: flex; align-items: center; justify-content: center;',
    '  box-shadow: 0 4px 20px rgba(0,0,0,0.4);',
    '  transition: all 0.3s ease;',
    '}',
    '#strboss-mic-btn:hover {',
    '  border-color: rgba(201,185,154,0.6);',
    '  box-shadow: 0 4px 30px rgba(201,185,154,0.15);',
    '  transform: scale(1.05);',
    '}',
    '#strboss-mic-btn.recording {',
    '  background: linear-gradient(135deg, #3a1515 0%, #4a2020 100%);',
    '  border-color: #c0504d;',
    '  animation: strboss-pulse 1.5s ease-in-out infinite;',
    '}',
    '#strboss-mic-btn.processing {',
    '  border-color: #d4a843;',
    '  animation: strboss-pulse 0.8s ease-in-out infinite;',
    '}',
    '#strboss-mic-btn.speaking {',
    '  border-color: #4a9e6e;',
    '  box-shadow: 0 4px 30px rgba(74,158,110,0.2);',
    '}',
    '#strboss-mic-btn svg { width: 24px; height: 24px; }',
    '@keyframes strboss-pulse {',
    '  0%, 100% { box-shadow: 0 4px 20px rgba(192,80,77,0.2); }',
    '  50% { box-shadow: 0 4px 30px rgba(192,80,77,0.5); }',
    '}',
    '#strboss-transcript {',
    '  position: absolute; bottom: 68px; right: 0;',
    '  width: 320px; max-height: 400px; overflow-y: auto;',
    '  background: rgba(20,20,20,0.95); border: 1px solid rgba(201,185,154,0.15);',
    '  border-radius: 12px; padding: 0;',
    '  display: none; flex-direction: column;',
    '  box-shadow: 0 8px 40px rgba(0,0,0,0.5);',
    '  backdrop-filter: blur(20px);',
    '}',
    '#strboss-transcript.open { display: flex; }',
    '#strboss-transcript-header {',
    '  padding: 12px 16px; border-bottom: 1px solid rgba(201,185,154,0.1);',
    '  display: flex; align-items: center; justify-content: space-between;',
    '  font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em;',
    '  color: rgba(255,255,255,0.5);',
    '}',
    '#strboss-transcript-header .status-dot {',
    '  width: 6px; height: 6px; border-radius: 50%;',
    '  background: #c0504d; display: inline-block; margin-right: 6px;',
    '}',
    '#strboss-transcript-header .status-dot.connected { background: #4a9e6e; }',
    '#strboss-transcript-body {',
    '  padding: 12px 16px; overflow-y: auto; max-height: 320px;',
    '  display: flex; flex-direction: column; gap: 10px;',
    '}',
    '.strboss-msg {',
    '  font-size: 13px; line-height: 1.5; padding: 8px 12px;',
    '  border-radius: 8px; max-width: 90%;',
    '}',
    '.strboss-msg.user {',
    '  background: rgba(201,185,154,0.1); color: #c9b99a;',
    '  align-self: flex-end; text-align: right;',
    '}',
    '.strboss-msg.assistant {',
    '  background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.85);',
    '  align-self: flex-start;',
    '}',
    '.strboss-msg.system {',
    '  background: transparent; color: rgba(255,255,255,0.35);',
    '  font-size: 11px; align-self: center; text-align: center;',
    '}',
    '#strboss-text-input {',
    '  display: flex; border-top: 1px solid rgba(201,185,154,0.1);',
    '  padding: 8px 12px;',
    '}',
    '#strboss-text-input input {',
    '  flex: 1; background: rgba(255,255,255,0.05);',
    '  border: 1px solid rgba(201,185,154,0.15); border-radius: 6px;',
    '  padding: 8px 12px; color: #fff; font-size: 13px;',
    '  font-family: "DM Sans", system-ui, sans-serif; outline: none;',
    '}',
    '#strboss-text-input input::placeholder { color: rgba(255,255,255,0.25); }',
    '#strboss-text-input input:focus { border-color: rgba(201,185,154,0.4); }',
  ].join('\n');
  document.head.appendChild(style);

  // ── Build DOM ──
  var widget = document.createElement('div');
  widget.id = 'strboss-voice-widget';
  widget.innerHTML = [
    '<div id="strboss-transcript">',
    '  <div id="strboss-transcript-header">',
    '    <span><span class="status-dot"></span>STRBOSS Voice</span>',
    '    <span id="strboss-close-btn" style="cursor:pointer;font-size:16px;color:rgba(255,255,255,0.4);">&#10005;</span>',
    '  </div>',
    '  <div id="strboss-transcript-body"></div>',
    '  <div id="strboss-text-input">',
    '    <input type="text" placeholder="Type a command..." id="strboss-text-field" />',
    '  </div>',
    '</div>',
    '<button id="strboss-mic-btn" title="STRBOSS Voice">',
    '  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">',
    '    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>',
    '    <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>',
    '    <line x1="12" y1="19" x2="12" y2="23"/>',
    '    <line x1="8" y1="23" x2="16" y2="23"/>',
    '  </svg>',
    '</button>',
  ].join('\n');
  document.body.appendChild(widget);

  var micBtn = document.getElementById('strboss-mic-btn');
  var transcriptPanel = document.getElementById('strboss-transcript');
  var transcriptBody = document.getElementById('strboss-transcript-body');
  var closeBtn = document.getElementById('strboss-close-btn');
  var textField = document.getElementById('strboss-text-field');
  var statusDot = widget.querySelector('.status-dot');

  // ── Helpers ──
  function addMessage(text, role) {
    var div = document.createElement('div');
    div.className = 'strboss-msg ' + role;
    div.textContent = text;
    transcriptBody.appendChild(div);
    transcriptBody.scrollTop = transcriptBody.scrollHeight;
  }

  function setStatus(state) {
    micBtn.className = '';
    if (state === 'recording') micBtn.classList.add('recording');
    else if (state === 'processing') micBtn.classList.add('processing');
    else if (state === 'speaking') micBtn.classList.add('speaking');
  }

  function updateConnectionDot(connected) {
    if (connected) statusDot.classList.add('connected');
    else statusDot.classList.remove('connected');
  }

  // ── Audio playback ──
  function playAudio(audioData) {
    // audioData is Uint8Array of MP3
    var blob = new Blob([audioData], { type: 'audio/mpeg' });
    var url = URL.createObjectURL(blob);
    var audio = new Audio(url);
    setStatus('speaking');
    audio.onended = function() {
      setStatus('');
      URL.revokeObjectURL(url);
    };
    audio.onerror = function() {
      setStatus('');
      URL.revokeObjectURL(url);
    };
    audio.play().catch(function(e) {
      console.warn('Audio playback failed:', e);
      setStatus('');
    });
  }

  // ── WebSocket ──
  function connectWS() {
    if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) return;

    ws = new WebSocket(WS_URL);
    ws.binaryType = 'arraybuffer';

    ws.onopen = function() {
      isConnected = true;
      updateConnectionDot(true);
      console.log('[STRBOSS] Voice WebSocket connected');
    };

    ws.onclose = function() {
      isConnected = false;
      updateConnectionDot(false);
      console.log('[STRBOSS] Voice WebSocket disconnected, reconnecting in 5s...');
      setTimeout(connectWS, 5000);
    };

    ws.onerror = function(e) {
      console.error('[STRBOSS] WebSocket error:', e);
    };

    ws.onmessage = function(event) {
      if (event.data instanceof ArrayBuffer) {
        // Binary: first byte is type marker (0x01 = audio)
        var arr = new Uint8Array(event.data);
        if (arr[0] === 0x01 && arr.length > 1) {
          playAudio(arr.slice(1));
        }
      } else {
        try {
          var msg = JSON.parse(event.data);
          if (msg.type === 'welcome') {
            addMessage(msg.text, 'system');
          } else if (msg.type === 'transcript') {
            if (msg.user) addMessage(msg.user, 'user');
            if (msg.assistant) addMessage(msg.assistant, 'assistant');
          } else if (msg.type === 'processing') {
            setStatus('processing');
          } else if (msg.type === 'ready') {
            setStatus('');
          }
        } catch (e) {
          console.warn('[STRBOSS] Parse error:', e);
        }
      }
    };
  }

  // ── Recording ──
  async function startRecording() {
    try {
      var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });

      mediaRecorder.ondataavailable = function(e) {
        if (e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = function() {
        stream.getTracks().forEach(function(t) { t.stop(); });
        if (audioChunks.length === 0) return;
        var blob = new Blob(audioChunks, { type: 'audio/webm' });
        blob.arrayBuffer().then(function(buf) {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(buf);
            setStatus('processing');
          }
        });
      };

      mediaRecorder.start();
      isRecording = true;
      setStatus('recording');
    } catch (e) {
      console.error('[STRBOSS] Mic access error:', e);
      addMessage('Microphone access denied. Please allow mic access and try again.', 'system');
    }
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
      mediaRecorder.stop();
    }
    isRecording = false;
  }

  // ── Event handlers ──
  var panelOpen = false;

  micBtn.addEventListener('mousedown', function(e) {
    e.preventDefault();
    if (!panelOpen) {
      panelOpen = true;
      transcriptPanel.classList.add('open');
      connectWS();
      return;
    }
    if (!isConnected) {
      connectWS();
      return;
    }
    startRecording();
  });

  micBtn.addEventListener('mouseup', function(e) {
    e.preventDefault();
    if (isRecording) stopRecording();
  });

  micBtn.addEventListener('mouseleave', function(e) {
    if (isRecording) stopRecording();
  });

  // Touch support
  micBtn.addEventListener('touchstart', function(e) {
    e.preventDefault();
    if (!panelOpen) {
      panelOpen = true;
      transcriptPanel.classList.add('open');
      connectWS();
      return;
    }
    if (!isConnected) {
      connectWS();
      return;
    }
    startRecording();
  }, { passive: false });

  micBtn.addEventListener('touchend', function(e) {
    e.preventDefault();
    if (isRecording) stopRecording();
  });

  closeBtn.addEventListener('click', function() {
    panelOpen = false;
    transcriptPanel.classList.remove('open');
    if (ws) ws.close();
  });

  // Text input
  textField.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && textField.value.trim()) {
      var text = textField.value.trim();
      textField.value = '';
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'text', text: text }));
        addMessage(text, 'user');
        setStatus('processing');
      } else {
        addMessage('Not connected. Click the mic button to connect.', 'system');
      }
    }
  });

})();
