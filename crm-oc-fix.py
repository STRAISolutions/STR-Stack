#!/usr/bin/env python3
"""Fix CRM dropdown visibility + OpenClaw voice rendering"""

FILE = '/srv/str-stack-public/dashboard.html'
with open(FILE, 'r') as f:
    html = f.read()

# ── 1. Fix CRM dropdown option visibility on Windows Chrome ──
# Native <select> options on Windows need explicit bg/color or they inherit badly
old_select_css = ".crm-filter-bar select, .crm-filter-bar input {\n  background: rgba(255,255,255,0.05); border: 1px solid var(--border); color: #fff;\n  padding: 7px 12px; border-radius: 6px; font-size: 12px; font-family: 'DM Sans', sans-serif;\n}"
new_select_css = """.crm-filter-bar select, .crm-filter-bar input {
  background: #1a1a1a; border: 1px solid var(--border); color: #fff;
  padding: 7px 12px; border-radius: 6px; font-size: 12px; font-family: 'DM Sans', sans-serif;
}
.crm-filter-bar select option {
  background: #1a1a1a; color: #fff; padding: 6px 10px;
}
.crm-filter-bar select option:checked {
  background: #2a2a2a; color: var(--gold);
}"""
html = html.replace(old_select_css, new_select_css)

# ── 2. Also fix any other dark-on-dark select issues across dashboard ──
# Check if the oc-agent-select has same problem
old_oc_select = ".oc-agent-select:focus { border-color: var(--gold); }"
new_oc_select = """.oc-agent-select:focus { border-color: var(--gold); }
.oc-agent-select option { background: #1a1a1a; color: #fff; }"""
html = html.replace(old_oc_select, new_oc_select)

# ── 3. Fix OpenClaw: ensure voice-widget.js script tag doesn't break ──
# Remove the old voice-widget.js script tag if it exists (the voice is now inline)
html = html.replace('<script src="voice-widget.js"></script>\n', '')
html = html.replace('<script src="voice-widget.js"></script>', '')

# ── 4. Verify ocRenderTiles builds mic buttons correctly ──
# The tile HTML uses querySelector('input') for Send which should work
# But let's also ensure the input placeholder shows voice state
old_placeholder = """placeholder="Enter task...\""""
new_placeholder = """placeholder="Type or click mic to speak...\""""
html = html.replace(old_placeholder, new_placeholder)

# ── 5. Fix CRM: ensure pipeline/tag/source selects populate after data loads ──
# The issue might be that innerHTML += creates issues in some browsers
# Replace innerHTML approach with proper DOM manipulation in the JS

old_src_populate = """    // Populate source dropdown
    var sources = {};
    CRM_DATA.forEach(function(c) { if (c.source) sources[c.source] = (sources[c.source]||0) + 1; });
    var srcSel = document.getElementById('crm-f-source');
    if (srcSel) {
      srcSel.innerHTML = '<option value="">All Sources</option>';
      Object.keys(sources).sort().forEach(function(s) {
        srcSel.innerHTML += '<option value="' + s + '">' + s + ' (' + sources[s] + ')</option>';
      });
    }

    // Populate pipeline dropdown
    var stages = {};
    CRM_DATA.forEach(function(c) {
      (c.allStages || []).forEach(function(s) { stages[s] = (stages[s]||0) + 1; });
    });
    var pipeSel = document.getElementById('crm-f-pipeline');
    if (pipeSel) {
      pipeSel.innerHTML = '<option value="">All Pipelines</option><option value="_none_">No Pipeline</option>';
      Object.keys(stages).sort().forEach(function(s) {
        pipeSel.innerHTML += '<option value="' + s + '">' + s + ' (' + stages[s] + ')</option>';
      });
    }

    // Populate tag dropdown
    var tagCounts = {};
    CRM_DATA.forEach(function(c) {
      (c.tags || []).forEach(function(t) { tagCounts[t] = (tagCounts[t]||0) + 1; });
    });
    var tagSel = document.getElementById('crm-f-tag');
    if (tagSel) {
      tagSel.innerHTML = '<option value="">All Tags</option>';
      Object.keys(tagCounts).sort(function(a,b){ return tagCounts[b]-tagCounts[a]; }).forEach(function(t) {
        tagSel.innerHTML += '<option value="' + t + '">' + t + ' (' + tagCounts[t] + ')</option>';
      });
    }"""

new_src_populate = """    // Populate source dropdown
    var sources = {};
    CRM_DATA.forEach(function(c) { if (c.source) sources[c.source] = (sources[c.source]||0) + 1; });
    var srcSel = document.getElementById('crm-f-source');
    if (srcSel) {
      var srcOpts = '<option value="">All Sources (' + Object.keys(sources).length + ')</option>';
      Object.keys(sources).sort().forEach(function(s) {
        srcOpts += '<option value="' + s + '">' + s + ' (' + sources[s] + ')</option>';
      });
      srcSel.innerHTML = srcOpts;
    }

    // Populate pipeline dropdown
    var stageMap = {};
    CRM_DATA.forEach(function(c) {
      (c.allStages || []).forEach(function(s) { stageMap[s] = (stageMap[s]||0) + 1; });
    });
    var noOppCount = CRM_DATA.filter(function(c){ return !c.allStages || c.allStages.length === 0; }).length;
    var pipeSel = document.getElementById('crm-f-pipeline');
    if (pipeSel) {
      var pipeOpts = '<option value="">All Pipelines (' + Object.keys(stageMap).length + ')</option>';
      pipeOpts += '<option value="_none_">No Pipeline (' + noOppCount + ')</option>';
      Object.keys(stageMap).sort().forEach(function(s) {
        pipeOpts += '<option value="' + s + '">' + s + ' (' + stageMap[s] + ')</option>';
      });
      pipeSel.innerHTML = pipeOpts;
    }

    // Populate tag dropdown
    var tagCounts = {};
    CRM_DATA.forEach(function(c) {
      (c.tags || []).forEach(function(t) { tagCounts[t] = (tagCounts[t]||0) + 1; });
    });
    var tagSel = document.getElementById('crm-f-tag');
    if (tagSel) {
      var tagOpts = '<option value="">All Tags (' + Object.keys(tagCounts).length + ')</option>';
      Object.keys(tagCounts).sort(function(a,b){ return tagCounts[b]-tagCounts[a]; }).forEach(function(t) {
        tagOpts += '<option value="' + t + '">' + t + ' (' + tagCounts[t] + ')</option>';
      });
      tagSel.innerHTML = tagOpts;
    }"""

html = html.replace(old_src_populate, new_src_populate)

with open(FILE, 'w') as f:
    f.write(html)

checks = [
    ("Option BG CSS", "select option" in html and "background: #1a1a1a" in html),
    ("OC select option CSS", ".oc-agent-select option" in html),
    ("No voice-widget.js", "voice-widget.js" not in html),
    ("New placeholder", "Type or click mic" in html),
    ("Source count in label", "All Sources (' + Object.keys" in html),
    ("Pipeline count", "All Pipelines (' + Object.keys" in html),
    ("Tag count", "All Tags (' + Object.keys" in html),
    ("No Pipeline option", "No Pipeline (" in html),
    ("Batch innerHTML", "srcOpts +=" in html),
]
for name, ok in checks:
    print(("  OK" if ok else "MISS") + " - " + name)
print("Done")
