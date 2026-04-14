#!/usr/bin/env python3
"""Fix OpenClaw voice: Samantha voice, visible transcript, no auto-send, mic/speaker conflict"""

FILE = '/srv/str-stack-public/dashboard.html'
with open(FILE, 'r') as f:
    html = f.read()

# ── 1. Fix voice ID in TTS fetch (old Lily → omit to use server default Samantha) ──
html = html.replace(
    "body: JSON.stringify({ text: item.text, voice: 'pFZP5JQG7iQjIQuC4Bku' })",
    "body: JSON.stringify({ text: item.text })"
)

# ── 2. Replace the entire voice module with fixed version ──
old_voice_start = '/* ═══ OpenClaw Voice Module ═══ */'
old_voice_end = '/* ═══ End Voice Module ═══ */'

vs = html.find(old_voice_start)
ve = html.find(old_voice_end)
if vs < 0 or ve < 0:
    print("ERROR: Voice module markers not found")
    exit(1)

new_voice = r"""/* ═══ OpenClaw Voice Module ═══ */
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
  OC_VOICE.recognition.continuous = true;
  OC_VOICE.recognition.interimResults = true;
  OC_VOICE.recognition.lang = 'en-US';

  OC_VOICE.recognition.onresult = function(e) {
    var interim = '';
    var final = '';
    for (var i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) {
        final += e.results[i][0].transcript;
      } else {
        interim += e.results[i][0].transcript;
      }
    }
    if (OC_VOICE.activeTile !== null) {
      var input = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
      if (input) {
        // Show transcript live in the input field
        if (final) {
          input.value = (input.value ? input.value + ' ' : '') + final;
          input.style.color = '#fff';
        } else if (interim) {
          // Show interim in muted color as placeholder-like text
          input.value = interim;
          input.style.color = 'rgba(255,255,255,0.4)';
        }
      }
    }
  };

  OC_VOICE.recognition.onend = function() {
    // Finalize the input text color
    if (OC_VOICE.activeTile !== null) {
      var input = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
      if (input) input.style.color = '#fff';
    }
    ocStopMicUI();
  };

  OC_VOICE.recognition.onerror = function(e) {
    if (e.error !== 'aborted') console.warn('[voice] STT error:', e.error);
    if (OC_VOICE.activeTile !== null) {
      var input = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
      if (input) input.style.color = '#fff';
    }
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

  // If TTS is speaking, stop it first so mic doesn't pick up speaker
  if (OC_VOICE.speaking) {
    ocStopSpeaking();
  }

  if (OC_VOICE.activeTile === tileIdx) {
    // Stop listening — text stays in input for user to review/edit/send
    try { OC_VOICE.recognition.stop(); } catch(e) {}
    var input = document.querySelector('.oc-task-input[data-tile="' + tileIdx + '"]');
    if (input) input.style.color = '#fff';
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
  var clean = text.replace(/<[^>]*>/g, '').replace(/[\u{1F000}-\u{1FFFF}]/gu, '').trim();
  if (!clean) return;

  // If mic is active, pause it while speaking to avoid feedback loop
  if (OC_VOICE.activeTile !== null) {
    try { OC_VOICE.recognition.stop(); } catch(e) {}
    // Don't reset activeTile — we'll restart mic after speech ends
  }

  OC_VOICE.audioQueue.push({ text: clean, tile: tileIdx });
  if (!OC_VOICE.speaking) ocPlayNext();
}

function ocPlayNext() {
  if (OC_VOICE.audioQueue.length === 0) {
    OC_VOICE.speaking = false;
    // If mic was active before speech, don't auto-restart — let user click mic again
    return;
  }
  OC_VOICE.speaking = true;
  var item = OC_VOICE.audioQueue.shift();

  var vbar = document.getElementById('oc-vbar-' + item.tile);
  if (vbar) vbar.classList.add('active');

  fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: item.text })
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

html = html[:vs] + new_voice + html[ve + len(old_voice_end):]

with open(FILE, 'w') as f:
    f.write(html)

checks = [
    ("No old Lily ID", "pFZP5JQG7iQjIQuC4Bku" not in html),
    ("Continuous mode", "continuous = true" in html),
    ("Interim results shown", "input.style.color" in html),
    ("No auto-send", "ocAddTask" not in html[html.find("onresult"):html.find("onresult")+500]),
    ("Mic stops speaker", "ocStopSpeaking" in html and "If TTS is speaking" in html),
    ("Speaker stops mic", "pause it while speaking" in html),
    ("STT init", "ocInitSTT" in html),
    ("TTS no voice param", "JSON.stringify({ text: item.text })" in html),
]
for name, ok in checks:
    print(("  OK" if ok else "MISS") + " - " + name)
print("Done")
