#!/usr/bin/env python3
"""Fix STT: explicitly request mic permission via getUserMedia before SpeechRecognition"""

FILE = '/srv/str-stack-public/dashboard.html'
with open(FILE, 'r') as f:
    html = f.read()

# Replace ocToggleMic to explicitly request mic permission first
old_toggle = """function ocToggleMic(btn) {
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
}"""

new_toggle = """function ocToggleMic(btn) {
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

  // Request mic permission explicitly, then start recognition
  var startRec = function() {
    OC_VOICE.activeTile = tileIdx;
    OC_VOICE.finalText = '';
    btn.classList.add('oc-mic-active');
    var vbar = document.getElementById('oc-vbar-' + tileIdx);
    if (vbar) vbar.classList.add('active');
    if (!OC_VOICE.recognition) ocInitSTT();
    try {
      OC_VOICE.recognition.start();
      console.log('[voice] Recognition started on tile', tileIdx);
    } catch(e) {
      console.warn('[voice] start error:', e);
      ocStopMicUI();
    }
  };

  // getUserMedia triggers Chrome's mic permission prompt if not yet granted
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then(function(stream) {
        // Permission granted — stop the stream (SpeechRecognition manages its own)
        stream.getTracks().forEach(function(t) { t.stop(); });
        console.log('[voice] Mic permission granted');
        startRec();
      })
      .catch(function(err) {
        console.error('[voice] Mic permission denied:', err);
        alert('Microphone access denied. Please allow mic access in Chrome and try again.');
      });
  } else {
    // Fallback: try starting directly
    startRec();
  }
}"""

html = html.replace(old_toggle, new_toggle)

# Also add console logging to onresult for debugging
old_onresult_guard = """    if (OC_VOICE.activeTile === null) return;
    var input = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
    if (!input) return;"""

new_onresult_guard = """    if (OC_VOICE.activeTile === null) { console.log('[voice] onresult but no activeTile'); return; }
    var input = document.querySelector('.oc-task-input[data-tile="' + OC_VOICE.activeTile + '"]');
    if (!input) { console.log('[voice] onresult but no input found for tile', OC_VOICE.activeTile); return; }
    console.log('[voice] result:', final || interim, 'final:', !!final);"""

html = html.replace(old_onresult_guard, new_onresult_guard)

with open(FILE, 'w') as f:
    f.write(html)

checks = [
    ("getUserMedia prompt", "navigator.mediaDevices.getUserMedia" in html),
    ("Stream cleanup", "stream.getTracks" in html),
    ("Permission denied alert", "Microphone access denied" in html),
    ("Console log start", "Recognition started on tile" in html),
    ("Console log result", "[voice] result:" in html),
    ("startRec function", "var startRec = function()" in html),
]
for name, ok in checks:
    print(("  OK" if ok else "MISS") + " - " + name)
print("Done")
