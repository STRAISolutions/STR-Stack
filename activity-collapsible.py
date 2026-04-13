#!/usr/bin/env python3
"""Make Activity Log sections collapsible + move GHL Command Center underneath"""

FILE = '/srv/str-stack-public/dashboard.html'
with open(FILE, 'r') as f:
    html = f.read()

# ── 1. Add collapsible CSS ──
collapse_css = """
/* Collapsible Activity Sections */
.act-collapse-hdr {
  display: flex; justify-content: space-between; align-items: center; cursor: pointer;
  user-select: none; padding: 4px 0;
}
.act-collapse-hdr:hover h2 { color: var(--gold); }
.act-collapse-hdr .act-chevron {
  font-size: 12px; color: var(--muted); transition: transform 0.25s;
}
.act-collapse-hdr.collapsed .act-chevron { transform: rotate(-90deg); }
.act-collapse-body { transition: max-height 0.3s ease, opacity 0.2s; overflow: hidden; }
.act-collapse-body.collapsed { max-height: 0 !important; opacity: 0; padding: 0; margin: 0; }
"""
html = html.replace('.tab-panel { display:none; }', collapse_css + '\n.tab-panel { display:none; }')

# ── 2. Make "Completed Tasks" collapsible ──
html = html.replace(
    '''<div style="display:flex; justify-content:space-between; align-items:center;">
            <h2>Completed Tasks</h2>
            <button class="refresh" onclick="loadChangelog()">Refresh</button>
          </div>
          <div id="changelog-container" style="max-height:400px; overflow-y:auto; margin-top:10px;">''',
    '''<div class="act-collapse-hdr" onclick="actToggle(this)">
            <h2>Completed Tasks</h2>
            <div style="display:flex;align-items:center;gap:8px;">
              <button class="refresh" onclick="event.stopPropagation();loadChangelog()">Refresh</button>
              <span class="act-chevron">&#9660;</span>
            </div>
          </div>
          <div class="act-collapse-body" id="changelog-container" style="max-height:400px; overflow-y:auto; margin-top:10px;">'''
)

# ── 3. Make "Pending Tasks" collapsible ──
html = html.replace(
    '''<div style="display:flex; justify-content:space-between; align-items:center;">
            <h2>Pending Tasks</h2>
            <button class="refresh" onclick="loadPendingTasks()">Refresh</button>
          </div>
          <div id="pending-container" style="max-height:350px; overflow-y:auto; margin-top:10px;">''',
    '''<div class="act-collapse-hdr" onclick="actToggle(this)">
            <h2>Pending Tasks</h2>
            <div style="display:flex;align-items:center;gap:8px;">
              <button class="refresh" onclick="event.stopPropagation();loadPendingTasks()">Refresh</button>
              <span class="act-chevron">&#9660;</span>
            </div>
          </div>
          <div class="act-collapse-body" id="pending-container" style="max-height:350px; overflow-y:auto; margin-top:10px;">'''
)

# ── 4. Make "Latest CONTEXT.md" collapsible ──
html = html.replace(
    '''<h2>Latest CONTEXT.md</h2>
        <pre id="context-raw">Loading...</pre>''',
    '''<div class="act-collapse-hdr" onclick="actToggle(this)">
            <h2>Latest CONTEXT.md</h2>
            <span class="act-chevron">&#9660;</span>
          </div>
          <div class="act-collapse-body">
            <pre id="context-raw">Loading...</pre>
          </div>'''
)

# ── 5. Extract GHL Command Center from financials and insert into activity tab ──
# Find the GHL Command Center block
ghl_cc_start = '<!-- GHL Command Interfaces -->'
ghl_cc_marker = '<div class="section-title">GHL Command Center</div>'

# The GHL Command Center block starts at the section-title and ends before the next section
# Let's find and extract it
idx_start = html.find(ghl_cc_marker)
if idx_start < 0:
    print("WARN: GHL Command Center marker not found")
else:
    # Find the grid that follows
    grid_start = html.find('<div style="display:grid; grid-template-columns:1fr 1fr; gap:18px;">', idx_start)
    # Find the closing of this grid — count div opens/closes
    # The grid contains two .card divs. Find the end by searching for the cc-history div's closing
    cc_history_end = html.find('</div>\n          </div>\n        </div>\n      </div>', grid_start)
    if cc_history_end < 0:
        # Try alternative pattern
        cc_history_end = html.find("</div>\n          </div>\n        </div>\n      </div>", grid_start)

    # Let's be more precise — find the end of ghl-cc-history block
    cc_hist_idx = html.find('id="ghl-cc-history"', grid_start)
    if cc_hist_idx > 0:
        # Find closing </div> sequence after cc-history
        # After ghl-cc-history div, there are closing divs: history-div, card-div, grid-div
        pos = cc_hist_idx
        # Skip past the history div content
        pos = html.find('</div>', pos) + 6  # close history div
        pos = html.find('</div>', pos) + 6  # close card div
        pos = html.find('</div>', pos) + 6  # close grid div

        ghl_block = html[idx_start:pos]

        # Remove from original location
        # Also remove the comment and divider before it
        comment_start = html.rfind('<!-- GHL Command Interfaces -->', 0, idx_start + 5)
        if comment_start < 0:
            comment_start = idx_start

        # Check for divider before
        divider_check = html[comment_start-50:comment_start].strip()
        remove_start = comment_start
        if '<div class="divider"></div>' in html[comment_start-60:comment_start]:
            remove_start = html.rfind('<div class="divider"></div>', 0, comment_start)

        html = html[:remove_start] + html[pos:]

        # Now insert into activity tab, after the last card (CONTEXT.md)
        activity_end = html.find('</section>', html.find('id="tab-activity"'))

        ghl_insert = '\n      <div class="divider" style="margin:20px 0;"></div>\n      ' + ghl_block + '\n'
        html = html[:activity_end] + ghl_insert + html[activity_end:]

# ── 6. Add toggle JS ──
toggle_js = """
/* Activity Log Collapse Toggle */
function actToggle(hdr) {
  hdr.classList.toggle('collapsed');
  var body = hdr.nextElementSibling;
  if (body) body.classList.toggle('collapsed');
}
"""
html = html.replace('/* === OpenClaw Agent Monitor === */', toggle_js + '\n/* === OpenClaw Agent Monitor === */')

with open(FILE, 'w') as f:
    f.write(html)

# Verify
checks = [
    ("Collapse CSS", ".act-collapse-hdr" in html),
    ("Completed collapsible", "act-collapse-hdr" in html and "Completed Tasks" in html),
    ("Pending collapsible", "act-collapse-hdr" in html and "Pending Tasks" in html),
    ("Context collapsible", "act-collapse-body" in html and "context-raw" in html),
    ("Toggle JS", "actToggle" in html),
    ("GHL in activity tab", html.find("GHL Command Center") > html.find("tab-activity")),
    ("GHL removed from financials", html.find("GHL Command Center") > html.find("tab-financials")),
]
for name, ok in checks:
    print(("  OK" if ok else "MISS") + " - " + name)
print("Done")
