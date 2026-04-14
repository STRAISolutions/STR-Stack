#!/usr/bin/env python3
"""Fix: (1) TTS fetch needs credentials, (2) Agent responses should be contextual"""

FILE = '/srv/str-stack-public/dashboard.html'
with open(FILE, 'r') as f:
    html = f.read()

# ── 1. Fix TTS fetch to include credentials ──
html = html.replace(
    "fetch('/api/tts', {\n    method: 'POST',\n    headers: { 'Content-Type': 'application/json' },\n    body: JSON.stringify({ text: item.text })\n  })",
    "fetch('/api/tts', {\n    method: 'POST',\n    credentials: 'include',\n    headers: { 'Content-Type': 'application/json' },\n    body: JSON.stringify({ text: item.text })\n  })"
)

# ── 2. Replace the generic agent response with contextual replies ──
# Currently when a task is delegated, the agent just says "accepted task" / "acknowledged task"
# We need the agents to give a more meaningful spoken reply based on the task content

# Replace the STRBOSS delegation speech
old_strboss_speak = "ocSpeak(capturedDelegate + ' has accepted the task and is working on it.', capturedTarget);"
new_strboss_speak = "ocSpeak(ocAgentReply(capturedDelegate, task), capturedTarget);"

html = html.replace(old_strboss_speak, new_strboss_speak)

# Replace the worker acknowledgment speech
old_worker_speak = "ocSpeak(capturedName + ' has acknowledged your task and is processing it.', capturedIdx2);"
new_worker_speak = "ocSpeak(ocAgentReply(capturedName, task), capturedIdx2);"

html = html.replace(old_worker_speak, new_worker_speak)

# ── 3. Add the contextual reply function ──
reply_fn = r"""
/* Agent contextual reply generator */
function ocAgentReply(agentName, taskText) {
  var t = (taskText || '').toLowerCase();
  var name = agentName || 'Agent';

  // Handle conversational / identity questions
  if (t.match(/what.*(call|name)|who are you|your name|introduce/)) {
    var ag = OC_AGENTS[agentName] || {};
    return "I'm " + name + ". I'm your " + (ag.role === 'coordinator' ? 'coordinator agent' : name.toLowerCase()) + " powered by " + (ag.model || 'AI') + ". How can I help you today?";
  }
  if (t.match(/hello|hey|hi |good morning|good afternoon|good evening/)) {
    return "Hey Mike. " + name + " here. What would you like me to work on?";
  }
  if (t.match(/how are you|how.s it going|what.s up/)) {
    return "All systems green, Mike. " + name + " is standing by. What do you need?";
  }
  if (t.match(/thank|thanks|good job|nice work/)) {
    return "Anytime, Mike. " + name + " is here whenever you need me.";
  }
  if (t.match(/status|update|progress|report/)) {
    return name + " checking status now. I'll have an update for you shortly.";
  }

  // Task-specific contextual replies based on agent role
  if (agentName === 'STRBOSS') {
    return "Got it. I've routed your task to the best agent for this. Stand by for confirmation.";
  }
  if (agentName === 'GHL Ops Analyst') {
    if (t.match(/pipeline|stage|funnel/)) return "Pulling pipeline data now. I'll have the breakdown ready in a moment.";
    if (t.match(/contact|lead/)) return "Searching contacts across both sub-accounts. One moment.";
    return "On it. Analyzing the GHL data for you now.";
  }
  if (agentName === 'Sales Strategy Coach') {
    if (t.match(/script|pitch/)) return "Working on that script now. I'll tailor it to your ICP.";
    if (t.match(/call|demo/)) return "Reviewing the call strategy. I'll have recommendations shortly.";
    return "Thinking through the best sales approach for this. Give me a moment.";
  }
  if (agentName === 'Comms Router') {
    if (t.match(/email|reply/)) return "Drafting the email response now. I'll have it ready for your review.";
    if (t.match(/sms|text|message/)) return "Composing the message. I'll route it through the right channel.";
    return "Setting up the communication flow. I'll confirm routing shortly.";
  }
  if (agentName === 'GHL Master Manager') {
    if (t.match(/workflow|automation/)) return "Reviewing the workflow configuration. I'll report back on any issues.";
    if (t.match(/webhook|trigger/)) return "Checking the webhook endpoints now. Stand by.";
    return "Managing the Master sub-account updates now.";
  }
  if (agentName === 'GHL CC Manager') {
    if (t.match(/outbound|dial/)) return "Checking the call queue and dialer status now.";
    if (t.match(/voicemail/)) return "Reviewing voicemail drops. I'll optimize the sequence.";
    return "Running the Call Center operations check now.";
  }
  if (agentName === 'STR Ops Agent') {
    if (t.match(/deploy|server|code/)) return "Connecting to the server now. I'll handle the deployment.";
    if (t.match(/fix|bug|error/)) return "Investigating the issue. I'll diagnose and fix it.";
    if (t.match(/dashboard/)) return "Updating the dashboard. Changes will be live shortly.";
    return "Working on the infrastructure task now. I'll confirm when complete.";
  }
  if (agentName === 'Assistant') {
    if (t.match(/search|find|look/)) return "Searching for that information now. One moment.";
    if (t.match(/summary|summarize/)) return "Pulling together a summary. I'll have it shortly.";
    return "Looking into that for you now, Mike.";
  }

  return name + " is working on your request. I'll update you when it's done.";
}
"""

# Insert before the ocAddTask function
html = html.replace(
    "function ocAddTask(input) {",
    reply_fn + "\nfunction ocAddTask(input) {"
)

# ── 4. Also improve the greeting to be warmer ──
html = html.replace(
    "var msg = timeGreet + ' Mike. STRBOSS is online. All agents are standing by. Send a task from any tile or use the mic to speak.';",
    "var msg = timeGreet + ' Mike. This is Samantha with STRBOSS. All 8 agents are online and standing by. You can type a task or tap the mic to speak.';"
)

with open(FILE, 'w') as f:
    f.write(html)

checks = [
    ("credentials include", "credentials: 'include'" in html),
    ("ocAgentReply function", "function ocAgentReply" in html),
    ("Identity response", "I'm " in html and "coordinator agent" in html),
    ("Hello response", "Hey Mike" in html),
    ("STRBOSS reply", "routed your task" in html),
    ("Agent-specific replies", "Pulling pipeline data" in html),
    ("Greeting updated", "This is Samantha" in html),
    ("Old generic removed", "has accepted the task and is working on it" not in html),
]
for name, ok in checks:
    print(("  OK" if ok else "MISS") + " - " + name)
print("Done")
