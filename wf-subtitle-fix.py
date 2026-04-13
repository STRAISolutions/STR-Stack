#!/usr/bin/env python3
"""Update GHL Workflow Map: replace Source badges with Source → Destination format"""

FILE = '/srv/str-stack-public/ghl-workflow-dashboard.html'
with open(FILE, 'r') as f:
    html = f.read()

# WF-INSTANTLY: Instantly Campaigns → A1 Master · New Lead
html = html.replace(
    '<span class="wf-source-badge">Source: Instantly Campaigns</span>',
    '<span class="wf-source-badge">Instantly Campaigns &rarr; A1 Master &middot; New Lead</span>'
)

# WF-WEBSITE: GHL Website Form → A1 Master · New Lead
html = html.replace(
    '<span class="wf-source-badge">Source: GHL Website Form</span>',
    '<span class="wf-source-badge">GHL Website Form &rarr; A1 Master &middot; New Lead</span>'
)

# WF2-HOSTFULLY: Hostfully PMS (port 8500/wf2) → A1 Master · Guest
html = html.replace(
    '<span class="wf-source-badge">Source: Hostfully PMS (port 8500/wf2)</span>',
    '<span class="wf-source-badge">Hostfully PMS (wf2) &rarr; A1 Master &middot; Guest</span>'
)

# WF3-DISCOVERY: Franchise Page (port 8500/wf3) → A1 Master · Discovery
html = html.replace(
    '<span class="wf-source-badge">Source: Franchise Page (port 8500/wf3)</span>',
    '<span class="wf-source-badge">Franchise Page (wf3) &rarr; A1 Master &middot; Discovery</span>'
)

# WF-ACTIVATION: A1 Closed Won → A2 Activation Pipeline
html = html.replace(
    '<span class="wf-source-badge">Source: A1 Closed Won &rarr; A2</span>',
    '<span class="wf-source-badge">A1 Closed Won &rarr; A2 Activation Pipeline</span>'
)

# WF-CALLCENTER: A1 Master Pipeline → CC Dialer Queue
html = html.replace(
    '<span class="wf-source-badge">Source: A1 Master Pipeline</span>',
    '<span class="wf-source-badge">A1 Master Pipeline &rarr; CC Dialer Queue</span>'
)

with open(FILE, 'w') as f:
    f.write(html)

checks = [
    ("WF-INSTANTLY", "Instantly Campaigns &rarr; A1 Master" in html),
    ("WF-WEBSITE", "GHL Website Form &rarr; A1 Master" in html),
    ("WF2-HOSTFULLY", "Hostfully PMS (wf2) &rarr; A1 Master" in html),
    ("WF3-DISCOVERY", "Franchise Page (wf3) &rarr; A1 Master" in html),
    ("WF-ACTIVATION", "A1 Closed Won &rarr; A2 Activation" in html),
    ("WF-CALLCENTER", "A1 Master Pipeline &rarr; CC Dialer" in html),
    ("No 'Source:' left", "Source:" not in html),
]
for name, ok in checks:
    print(("  OK" if ok else "  MISS") + " - " + name)
print("Done")
