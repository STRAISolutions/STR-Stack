#!/usr/bin/env python3
"""Fix OpenClaw voice: greeting, visible transcript, auto-send after pause"""

FILE = '/srv/str-stack-public/dashboard.html'
with open(FILE, 'r') as f:
    html = f.read()

# Replace entire voice module
old_start = '/* ═══ OpenClaw Voice Module ═══ */'
old_end = '/* ═══ End Voice Module ═══ */'

vs = html.find(old_start)
ve = html.find(old_end)
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
  supported: !!(window.SpeechRecognition || window.webkitSpeechRecognition),
  finalText: '',
  sendTimer: null,
  greeted: false
};

/* ── Speech-to-Text ── */
function ocInitSTT() {
  if (!OC_VOICE.supported) { console.warn('[voice] SpeechRecognition not supported'); return; }
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var rec = new SR();
  rec.continuous = false;
  rec.interimResults = true;
  rec.lang = 'en-US';
  rec.maxAlternatives = 1;

  rec.onresult = function(e) {
    var interim = '';
    var final = '';
    for (var i = e.resultIndex; i < e.results.length; i++) {
      var t = e.results[i][0].transcript;
      if (e.results[i].isFinal) {
        final += t;
      } else {
        interim += t;
      }
    }

    if (OC_VOICE.activeTile === null) return;
    var input = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
    if (!input) return;

    if (final) {
      // Accumulate final text
      OC_VOICE.finalText = (OC_VOICE.finalText ? OC_VOICE.finalText + ' ' : '') + final.trim();
      input.value = OC_VOICE.finalText;
      input.style.color = '#fff';

      // Auto-send after 1.5s of silence (no more speech)
      if (OC_VOICE.sendTimer) clearTimeout(OC_VOICE.sendTimer);
      OC_VOICE.sendTimer = setTimeout(function() {
        var inp = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
        if (inp && inp.value.trim()) {
          // Stop mic, send task
          try { OC_VOICE.recognition.stop(); } catch(ex) {}
          inp.style.color = '#fff';
          ocAddTask(inp);
          OC_VOICE.finalText = '';
        }
      }, 1500);
    } else if (interim) {
      // Show live interim transcript (muted)
      input.value = (OC_VOICE.finalText ? OC_VOICE.finalText + ' ' : '') + interim;
      input.style.color = 'rgba(201,185,154,0.6)';
    }
  };

  rec.onend = function() {
    // If mic is still supposed to be active (user didn't click stop), restart
    if (OC_VOICE.activeTile !== null && !OC_VOICE.speaking) {
      try { rec.start(); } catch(ex) {
        ocStopMicUI();
      }
      return;
    }
    // Finalize
    if (OC_VOICE.activeTile !== null) {
      var input = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
      if (input) input.style.color = '#fff';
    }
    if (!OC_VOICE.speaking) ocStopMicUI();
  };

  rec.onerror = function(e) {
    if (e.error === 'no-speech') {
      // Silence — restart if still active
      if (OC_VOICE.activeTile !== null && !OC_VOICE.speaking) {
        try { rec.start(); } catch(ex) { ocStopMicUI(); }
        return;
      }
    }
    if (e.error !== 'aborted') console.warn('[voice] STT error:', e.error);
    ocStopMicUI();
  };

  OC_VOICE.recognition = rec;
}

function ocToggleMic(btn) {
  var tileIdx = parseInt(btn.getAttribute('data-tile'));
  if (isNaN(tileIdx)) return;

  if (!OC_VOICE.supported) {
    alert('Voice input requires Chrome browser.');
    return;
  }

  // Stop any TTS playback first
  if (OC_VOICE.speaking) ocStopSpeaking();

  // If already listening on this tile, stop
  if (OC_VOICE.activeTile === tileIdx) {
    if (OC_VOICE.sendTimer) { clearTimeout(OC_VOICE.sendTimer); OC_VOICE.sendTimer = null; }
    try { OC_VOICE.recognition.stop(); } catch(e) {}
    var input = document.querySelector('.oc-task-input[data-tile="' + tileIdx + '"]');
    if (input) input.style.color = '#fff';
    // If there's text, send it
    if (input && input.value.trim()) {
      ocAddTask(input);
      OC_VOICE.finalText = '';
    }
    ocStopMicUI();
    return;
  }

  // Stop any other active mic session
  if (OC_VOICE.activeTile !== null) {
    if (OC_VOICE.sendTimer) { clearTimeout(OC_VOICE.sendTimer); OC_VOICE.sendTimer = null; }
    try { OC_VOICE.recognition.stop(); } catch(e) {}
    ocStopMicUI();
  }

  // Start listening
  OC_VOICE.activeTile = tileIdx;
  OC_VOICE.finalText = '';
  btn.classList.add('oc-mic-active');
  var vbar = document.getElementById('oc-vbar-' + tileIdx);
  if (vbar) vbar.classList.add('active');

  if (!OC_VOICE.recognition) ocInitSTT();
  try {
    OC_VOICE.recognition.start();
  } catch(e) {
    console.warn('[voice] start error:', e);
    ocStopMicUI();
  }
}

function ocStopMicUI() {
  document.querySelectorAll('.oc-mic-btn').forEach(function(b) { b.classList.remove('oc-mic-active'); });
  document.querySelectorAll('.oc-voice-bar').forEach(function(v) { v.classList.remove('active'); });
  OC_VOICE.activeTile = null;
}

/* ── Text-to-Speech (ElevenLabs) ── */
function ocSpeak(text, tileIdx) {
  if (!text || text.length < 3) return;
  var clean = text.replace(/<[^>]*>/g, '').replace(/[\u{1F000}-\u{1FFFF}]/gu, '').trim();
  if (!clean) return;

  // Pause mic while speaking
  if (OC_VOICE.activeTile !== null) {
    try { OC_VOICE.recognition.stop(); } catch(e) {}
  }

  OC_VOICE.audioQueue.push({ text: clean, tile: tileIdx });
  if (!OC_VOICE.speaking) ocPlayNext();
}

function ocPlayNext() {
  if (OC_VOICE.audioQueue.length === 0) {
    OC_VOICE.speaking = false;
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
      console.warn('[voice] play error:', e);
      if (vbar) vbar.classList.remove('active');
      OC_VOICE.currentAudio = null;
      ocPlayNext();
    });
  })
  .catch(function(e) {
    console.warn('[voice] TTS error:', e);
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

/* ── Greeting on OpenClaw tab open ── */
function ocGreeting() {
  if (OC_VOICE.greeted) return;
  OC_VOICE.greeted = true;
  var now = new Date();
  var hour = now.getHours();
  var timeGreet = hour < 12 ? 'Good morning' : (hour < 17 ? 'Good afternoon' : 'Good evening');
  var msg = timeGreet + ' Mike. STRBOSS is online. All agents are standing by. Send a task from any tile or use the mic to speak.';

  // Add to STRBOSS feed
  var ts = now.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  if (ocTileState && ocTileState[0]) {
    ocTileState[0].feed.unshift({ time: ts, text: msg });
    ocSaveState();
    ocRenderTiles();
  }

  // Speak greeting
  setTimeout(function() { ocSpeak(msg, 0); }, 500);
}

// Trigger greeting when OpenClaw tab is clicked
document.addEventListener('click', function(e) {
  var btn = e.target.closest && e.target.closest('.tab-btn[data-tab="openclaw"]');
  if (btn) setTimeout(ocGreeting, 300);
});

// Init STT on load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', ocInitSTT);
} else {
  ocInitSTT();
}
/* ═══ End Voice Module ═══ */
"""

html = html[:vs] + new_voice + html[ve + len(old_end):]

with open(FILE, 'w') as f:
    f.write(html)

checks = [
    ("Greeting function", "ocGreeting" in html),
    ("Time-based greeting", "Good morning" in html),
    ("Greeting on tab click", "data-tab=\"openclaw\"" in html and "ocGreeting" in html),
    ("finalText accumulator", "OC_VOICE.finalText" in html),
    ("Auto-send after 1.5s", "1500" in html and "sendTimer" in html),
    ("Auto-restart on no-speech", "no-speech" in html),
    ("Auto-restart on end", "rec.start" in html),
    ("Mic click sends text", "ocAddTask(input)" in html),
    ("Interim gold color", "201,185,154" in html),
    ("STRBOSS feed greeting", "STRBOSS is online" in html),
]
for name, ok in checks:
    print(("  OK" if ok else "MISS") + " - " + name)
print("Done")
