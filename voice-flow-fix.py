#!/usr/bin/env python3
"""Rebuild voice to Vapi-like flow: greeting -> auto-listen -> transcript -> auto-send"""

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
  greeted: false,
  micPermission: false,
  autoListenAfterSpeak: false
};

/* ── Request mic permission (one-time) ── */
function ocRequestMic() {
  return new Promise(function(resolve, reject) {
    if (OC_VOICE.micPermission) { resolve(); return; }
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      navigator.mediaDevices.getUserMedia({ audio: true })
        .then(function(stream) {
          stream.getTracks().forEach(function(t) { t.stop(); });
          OC_VOICE.micPermission = true;
          console.log('[voice] Mic permission granted');
          resolve();
        })
        .catch(function(err) {
          console.error('[voice] Mic denied:', err);
          reject(err);
        });
    } else {
      resolve();
    }
  });
}

/* ── Speech-to-Text ── */
function ocInitSTT() {
  if (!OC_VOICE.supported) { console.warn('[voice] SpeechRecognition not supported'); return; }
  if (OC_VOICE.recognition) return;
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var rec = new SR();
  rec.continuous = true;
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
      OC_VOICE.finalText = (OC_VOICE.finalText ? OC_VOICE.finalText + ' ' : '') + final.trim();
      input.value = OC_VOICE.finalText;
      input.style.color = '#fff';
      console.log('[voice] final:', OC_VOICE.finalText);

      // Auto-send after 2s of silence
      if (OC_VOICE.sendTimer) clearTimeout(OC_VOICE.sendTimer);
      OC_VOICE.sendTimer = setTimeout(function() {
        var inp = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
        if (inp && inp.value.trim()) {
          console.log('[voice] Auto-sending after silence');
          try { OC_VOICE.recognition.stop(); } catch(ex) {}
          ocStopMicUI();
          inp.style.color = '#fff';
          ocAddTask(inp);
          OC_VOICE.finalText = '';
        }
      }, 2000);
    } else if (interim) {
      input.value = (OC_VOICE.finalText ? OC_VOICE.finalText + ' ' : '') + interim;
      input.style.color = 'rgba(201,185,154,0.6)';
    }
  };

  rec.onend = function() {
    console.log('[voice] recognition ended, activeTile:', OC_VOICE.activeTile, 'speaking:', OC_VOICE.speaking);
    if (OC_VOICE.activeTile !== null && !OC_VOICE.speaking) {
      setTimeout(function() {
        if (OC_VOICE.activeTile !== null && !OC_VOICE.speaking) {
          try { rec.start(); console.log('[voice] restarted after onend'); } catch(ex) {
            console.warn('[voice] restart failed:', ex);
            ocStopMicUI();
          }
        }
      }, 100);
      return;
    }
    if (OC_VOICE.activeTile !== null) {
      var input = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
      if (input) input.style.color = '#fff';
    }
  };

  rec.onerror = function(e) {
    console.warn('[voice] STT error:', e.error);
    if (e.error === 'no-speech' || e.error === 'aborted') {
      if (OC_VOICE.activeTile !== null && !OC_VOICE.speaking) {
        setTimeout(function() {
          if (OC_VOICE.activeTile !== null && !OC_VOICE.speaking) {
            try { rec.start(); } catch(ex) { ocStopMicUI(); }
          }
        }, 200);
        return;
      }
    }
    if (e.error !== 'aborted') ocStopMicUI();
  };

  OC_VOICE.recognition = rec;
  console.log('[voice] STT initialized');
}

/* ── Start listening on a tile ── */
function ocStartListening(tileIdx) {
  if (OC_VOICE.activeTile === tileIdx) return;

  if (OC_VOICE.activeTile !== null) {
    if (OC_VOICE.sendTimer) { clearTimeout(OC_VOICE.sendTimer); OC_VOICE.sendTimer = null; }
    try { OC_VOICE.recognition.stop(); } catch(e) {}
    ocStopMicUI();
  }

  OC_VOICE.activeTile = tileIdx;
  OC_VOICE.finalText = '';

  var btn = document.querySelector('.oc-mic-btn[data-tile="' + tileIdx + '"]');
  if (btn) btn.classList.add('oc-mic-active');
  var vbar = document.getElementById('oc-vbar-' + tileIdx);
  if (vbar) vbar.classList.add('active');

  ocInitSTT();
  try {
    OC_VOICE.recognition.start();
    console.log('[voice] Listening on tile', tileIdx);
  } catch(e) {
    console.warn('[voice] start error:', e);
    try { OC_VOICE.recognition.stop(); } catch(ex) {}
    setTimeout(function() {
      try { OC_VOICE.recognition.start(); console.log('[voice] Retry start OK'); }
      catch(ex2) { console.warn('[voice] retry failed:', ex2); ocStopMicUI(); }
    }, 200);
  }
}

/* ── Mic button click = stop listening + send ── */
function ocToggleMic(btn) {
  var tileIdx = parseInt(btn.getAttribute('data-tile'));
  if (isNaN(tileIdx)) return;

  if (!OC_VOICE.supported) {
    alert('Voice input requires Chrome browser.');
    return;
  }

  if (OC_VOICE.speaking) ocStopSpeaking();

  // If listening on this tile — stop and send
  if (OC_VOICE.activeTile === tileIdx) {
    if (OC_VOICE.sendTimer) { clearTimeout(OC_VOICE.sendTimer); OC_VOICE.sendTimer = null; }
    try { OC_VOICE.recognition.stop(); } catch(e) {}
    var input = document.querySelector('.oc-task-input[data-tile="' + tileIdx + '"]');
    if (input) input.style.color = '#fff';
    if (input && input.value.trim()) {
      ocAddTask(input);
      OC_VOICE.finalText = '';
    }
    ocStopMicUI();
    return;
  }

  // Not listening — start listening on this tile
  ocRequestMic().then(function() {
    ocStartListening(tileIdx);
  }).catch(function() {
    alert('Microphone access denied. Allow mic access in Chrome settings.');
  });
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

  if (OC_VOICE.activeTile !== null) {
    try { OC_VOICE.recognition.stop(); } catch(e) {}
  }

  OC_VOICE.audioQueue.push({ text: clean, tile: tileIdx });
  if (!OC_VOICE.speaking) ocPlayNext();
}

function ocPlayNext() {
  if (OC_VOICE.audioQueue.length === 0) {
    OC_VOICE.speaking = false;
    // After TTS finishes, auto-start listening on STRBOSS tile
    if (OC_VOICE.autoListenAfterSpeak) {
      OC_VOICE.autoListenAfterSpeak = false;
      console.log('[voice] TTS done, auto-starting mic on tile 0');
      setTimeout(function() {
        ocRequestMic().then(function() {
          ocStartListening(0);
        });
      }, 300);
    }
    return;
  }
  OC_VOICE.speaking = true;
  var item = OC_VOICE.audioQueue.shift();

  var vbar = document.getElementById('oc-vbar-' + item.tile);
  if (vbar) vbar.classList.add('active');

  fetch('/api/tts', {
    method: 'POST',
    credentials: 'include',
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
  OC_VOICE.autoListenAfterSpeak = false;
  document.querySelectorAll('.oc-voice-bar').forEach(function(v) { v.classList.remove('active'); });
}

/* ── Greeting: short "Hey Mike" then auto-listen ── */
function ocGreeting() {
  if (OC_VOICE.greeted) return;
  OC_VOICE.greeted = true;

  var msg = 'Hey Mike';

  var ts = new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  if (ocTileState && ocTileState[0]) {
    ocTileState[0].feed.unshift({ time: ts, text: 'STRBOSS online. Listening...' });
    ocSaveState();
    ocRenderTiles();
  }

  // Request mic permission now (triggers Chrome prompt during greeting)
  ocRequestMic().then(function() {
    OC_VOICE.autoListenAfterSpeak = true;
    ocInitSTT();
    setTimeout(function() { ocSpeak(msg, 0); }, 300);
  }).catch(function() {
    setTimeout(function() { ocSpeak(msg, 0); }, 300);
  });
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
    ("Short greeting", "'Hey Mike'" in html),
    ("Auto-listen flag", "autoListenAfterSpeak" in html),
    ("Auto-start after TTS", "auto-starting mic on tile 0" in html),
    ("getUserMedia permission", "navigator.mediaDevices.getUserMedia" in html),
    ("ocStartListening function", "function ocStartListening" in html),
    ("Continuous mode", "rec.continuous = true" in html),
    ("Auto-send 2s silence", "Auto-sending after silence" in html),
    ("Restart on end", "restarted after onend" in html),
    ("Restart on no-speech", "no-speech" in html),
    ("Mic click sends text", "ocAddTask(input)" in html),
    ("Feed shows listening", "Listening..." in html),
    ("Old long greeting gone", "All 8 agents are online" not in html),
]
for name, ok in checks:
    print(("  OK" if ok else "MISS") + " - " + name)
print("Done")
