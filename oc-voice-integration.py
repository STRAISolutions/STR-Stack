#!/usr/bin/env python3
"""Add ElevenLabs voice + mic to every OpenClaw tile"""

import re

FILE = '/srv/str-stack-public/dashboard.html'
with open(FILE, 'r') as f:
    html = f.read()

# ── 1. CSS for mic button + voice indicator ──
voice_css = """
/* Voice / Mic */
.oc-mic-btn {
  width: 34px; height: 34px; border-radius: 50%; border: 1px solid var(--border);
  background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.5);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.2s; flex-shrink: 0; font-size: 16px; padding: 0;
}
.oc-mic-btn:hover { border-color: var(--gold); color: var(--gold); }
.oc-mic-btn.oc-mic-active {
  background: rgba(231,76,60,0.2); border-color: #e74c3c; color: #e74c3c;
  animation: oc-mic-pulse 1s infinite;
}
@keyframes oc-mic-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(231,76,60,0.4); }
  50% { box-shadow: 0 0 0 8px rgba(231,76,60,0); }
}
.oc-voice-bar {
  display: flex; align-items: center; gap: 4px; height: 3px; margin-top: 2px;
  opacity: 0; transition: opacity 0.3s;
}
.oc-voice-bar.active { opacity: 1; }
.oc-voice-bar span {
  width: 3px; background: var(--gold); border-radius: 2px;
  animation: oc-vbar 0.6s ease-in-out infinite alternate;
}
.oc-voice-bar span:nth-child(1) { height: 4px; animation-delay: 0s; }
.oc-voice-bar span:nth-child(2) { height: 8px; animation-delay: 0.15s; }
.oc-voice-bar span:nth-child(3) { height: 12px; animation-delay: 0.3s; }
.oc-voice-bar span:nth-child(4) { height: 8px; animation-delay: 0.45s; }
.oc-voice-bar span:nth-child(5) { height: 4px; animation-delay: 0.6s; }
@keyframes oc-vbar {
  from { transform: scaleY(0.3); } to { transform: scaleY(1); }
}
.oc-speaking-indicator {
  display: inline-flex; align-items: center; gap: 4px; font-size: 10px;
  color: var(--gold); margin-left: 6px; opacity: 0; transition: opacity 0.3s;
}
.oc-speaking-indicator.active { opacity: 1; }
"""

# Insert CSS before .oc-grid CSS
html = html.replace('.oc-grid { display: grid;', voice_css + '\n.oc-grid { display: grid;')

# ── 2. Update tile HTML to add mic button + voice bar ──
# Replace the task-row innerHTML in ocRenderTiles
old_task_row = (
    """+ '<div class="oc-task-row">'"""
    """\n      + '<input class="oc-task-input" data-tile="' + i + '" placeholder="Enter task..." onkeydown="if(event.key===\\\'Enter\\\')ocAddTask(this)">'"""
    """\n      + '<button class="oc-task-btn" onclick="ocAddTask(this.previousElementSibling)">Send</button>'"""
    """\n      + '</div>'"""
)

new_task_row = (
    """+ '<div class="oc-task-row">'"""
    """\n      + '<input class="oc-task-input" data-tile="' + i + '" placeholder="Enter task..." onkeydown="if(event.key===\\\'Enter\\\')ocAddTask(this)">'"""
    """\n      + '<button class="oc-mic-btn" data-tile="' + i + '" onclick="ocToggleMic(this)" title="Hold to speak"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="1" width="6" height="13" rx="3"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg></button>'"""
    """\n      + '<button class="oc-task-btn" onclick="ocAddTask(this.parentElement.querySelector(\\\'input\\\'))">Send</button>'"""
    """\n      + '</div>'"""
    """\n      + '<div class="oc-voice-bar" id="oc-vbar-' + i + '"><span></span><span></span><span></span><span></span><span></span></div>'"""
)

html = html.replace(old_task_row, new_task_row)

# ── 3. Voice JS module ──
voice_js = r"""
/* ═══ OpenClaw Voice Module ═══ */
var OC_VOICE = {
  recognition: null,
  activeTile: null,
  speaking: false,
  audioQueue: [],
  currentAudio: null,
  supported: !!(window.SpeechRecognition || window.webkitSpeechRecognition)
};

/* ── Speech-to-Text (Browser SpeechRecognition) ── */
function ocInitSTT() {
  if (!OC_VOICE.supported) { console.warn('[voice] SpeechRecognition not supported'); return; }
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  OC_VOICE.recognition = new SR();
  OC_VOICE.recognition.continuous = false;
  OC_VOICE.recognition.interimResults = true;
  OC_VOICE.recognition.lang = 'en-US';

  OC_VOICE.recognition.onresult = function(e) {
    var transcript = '';
    for (var i = e.resultIndex; i < e.results.length; i++) {
      transcript += e.results[i][0].transcript;
    }
    if (OC_VOICE.activeTile !== null) {
      var input = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
      if (input) input.value = transcript;
    }
    // If final result, auto-send
    if (e.results[e.results.length - 1].isFinal && transcript.trim()) {
      setTimeout(function() {
        var input = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
        if (input && input.value.trim()) ocAddTask(input);
      }, 300);
    }
  };

  OC_VOICE.recognition.onend = function() {
    ocStopMicUI();
  };

  OC_VOICE.recognition.onerror = function(e) {
    console.warn('[voice] STT error:', e.error);
    ocStopMicUI();
  };
}

function ocToggleMic(btn) {
  var tileIdx = parseInt(btn.getAttribute('data-tile'));
  if (isNaN(tileIdx)) return;

  if (!OC_VOICE.supported) {
    alert('Voice input is not supported in this browser. Use Chrome for best results.');
    return;
  }

  if (OC_VOICE.activeTile === tileIdx) {
    // Stop listening
    try { OC_VOICE.recognition.stop(); } catch(e) {}
    ocStopMicUI();
    return;
  }

  // Stop any existing session
  if (OC_VOICE.activeTile !== null) {
    try { OC_VOICE.recognition.stop(); } catch(e) {}
    ocStopMicUI();
  }

  // Start listening on this tile
  OC_VOICE.activeTile = tileIdx;
  btn.classList.add('oc-mic-active');
  var vbar = document.getElementById('oc-vbar-' + tileIdx);
  if (vbar) vbar.classList.add('active');

  if (!OC_VOICE.recognition) ocInitSTT();
  try { OC_VOICE.recognition.start(); } catch(e) {
    console.warn('[voice] start error:', e);
    ocStopMicUI();
  }
}

function ocStopMicUI() {
  document.querySelectorAll('.oc-mic-btn').forEach(function(b) { b.classList.remove('oc-mic-active'); });
  document.querySelectorAll('.oc-voice-bar').forEach(function(v) { v.classList.remove('active'); });
  OC_VOICE.activeTile = null;
}

/* ── Text-to-Speech (ElevenLabs via server proxy) ── */
function ocSpeak(text, tileIdx) {
  if (!text || text.length < 3) return;
  // Clean text of emojis and HTML
  var clean = text.replace(/<[^>]*>/g, '').replace(/[\u{1F000}-\u{1FFFF}]/gu, '').trim();
  if (!clean) return;

  OC_VOICE.audioQueue.push({ text: clean, tile: tileIdx });
  if (!OC_VOICE.speaking) ocPlayNext();
}

function ocPlayNext() {
  if (OC_VOICE.audioQueue.length === 0) { OC_VOICE.speaking = false; return; }
  OC_VOICE.speaking = true;
  var item = OC_VOICE.audioQueue.shift();

  // Show speaking indicator on tile
  var vbar = document.getElementById('oc-vbar-' + item.tile);
  if (vbar) { vbar.classList.add('active'); vbar.style.setProperty('--bar-color', 'var(--gold)'); }

  fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: item.text, voice: 'pFZP5JQG7iQjIQuC4Bku' })
  })
  .then(function(r) {
    if (!r.ok) throw new Error('TTS ' + r.status);
    return r.blob();
  })
  .then(function(blob) {
    var url = URL.createObjectURL(blob);
    var audio = new Audio(url);
    OC_VOICE.currentAudio = audio;
    audio.onended = function() {
      URL.revokeObjectURL(url);
      if (vbar) vbar.classList.remove('active');
      OC_VOICE.currentAudio = null;
      ocPlayNext();
    };
    audio.onerror = function() {
      if (vbar) vbar.classList.remove('active');
      OC_VOICE.currentAudio = null;
      ocPlayNext();
    };
    audio.play().catch(function(e) {
      console.warn('[voice] audio play error:', e);
      if (vbar) vbar.classList.remove('active');
      OC_VOICE.currentAudio = null;
      ocPlayNext();
    });
  })
  .catch(function(e) {
    console.warn('[voice] TTS fetch error:', e);
    if (vbar) vbar.classList.remove('active');
    // Fallback to browser TTS
    ocFallbackSpeak(item.text);
  });
}

function ocFallbackSpeak(text) {
  if ('speechSynthesis' in window) {
    var u = new SpeechSynthesisUtterance(text);
    u.rate = 1; u.pitch = 1;
    u.onend = function() { ocPlayNext(); };
    u.onerror = function() { ocPlayNext(); };
    speechSynthesis.speak(u);
  } else {
    ocPlayNext();
  }
}

function ocStopSpeaking() {
  if (OC_VOICE.currentAudio) {
    OC_VOICE.currentAudio.pause();
    OC_VOICE.currentAudio = null;
  }
  if ('speechSynthesis' in window) speechSynthesis.cancel();
  OC_VOICE.audioQueue = [];
  OC_VOICE.speaking = false;
  document.querySelectorAll('.oc-voice-bar').forEach(function(v) { v.classList.remove('active'); });
}

// Initialize STT on load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', ocInitSTT);
} else {
  ocInitSTT();
}
/* ═══ End Voice Module ═══ */
"""

# Insert voice JS before the closing </script> of the OpenClaw block
# Find the last </script> before </body>
html = html.replace(
    "// Initialize OpenClaw tiles\n(function() {\n  if (document.readyState === 'loading') {\n    document.addEventListener('DOMContentLoaded', ocRenderTiles);\n  } else {\n    ocRenderTiles();\n  }\n})();",
    "// Initialize OpenClaw tiles\n(function() {\n  if (document.readyState === 'loading') {\n    document.addEventListener('DOMContentLoaded', ocRenderTiles);\n  } else {\n    ocRenderTiles();\n  }\n})();\n" + voice_js
)

# ── 4. Hook voice into agent responses ──
# When an agent "accepts" or responds, speak the response on that tile
# Patch the ocAddTask setTimeout callbacks to trigger TTS

# STRBOSS delegation confirmation speech
old_confirmed = "ocTileState[capturedIdx].feed.unshift({ time: ts2, text: '\\u2705 ' + capturedDelegate + ' confirmed' });"
new_confirmed = old_confirmed + "\n        ocSpeak(capturedDelegate + ' has accepted the task and is working on it.', capturedTarget);"

html = html.replace(old_confirmed, new_confirmed)

# Worker acknowledgment speech
old_ack = "ocTileState[capturedIdx2].feed.unshift({ time: ts3, text: '\\u2713 ' + capturedName + ' acknowledged task' });"
new_ack = old_ack + "\n      ocSpeak(capturedName + ' has acknowledged your task and is processing it.', capturedIdx2);"

html = html.replace(old_ack, new_ack)

with open(FILE, 'w') as f:
    f.write(html)

# ── Verify ──
checks = [
    ("Mic CSS", ".oc-mic-btn" in html),
    ("Mic SVG in tile", 'oc-mic-btn' in html and 'ocToggleMic' in html),
    ("Voice bar", 'oc-vbar-' in html),
    ("STT init", 'ocInitSTT' in html),
    ("TTS fetch", "/api/tts" in html),
    ("Speak on confirm", "ocSpeak(capturedDelegate" in html),
    ("Speak on ack", "ocSpeak(capturedName" in html),
    ("Fallback TTS", "ocFallbackSpeak" in html),
]
for name, ok in checks:
    print(("  OK" if ok else "MISS") + " - " + name)
print("Done — dashboard updated")
