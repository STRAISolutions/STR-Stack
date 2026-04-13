#!/usr/bin/env python3
"""Add CRM tab to STR Dashboard under Operations"""

FILE = '/srv/str-stack-public/dashboard.html'
with open(FILE, 'r') as f:
    html = f.read()

# ── 1. Add CRM nav button under Operations ──
html = html.replace(
    '<button class="tab-btn" data-tab="workflows">GHL Workflows</button>',
    '<button class="tab-btn" data-tab="crm">CRM</button>\n        <button class="tab-btn" data-tab="workflows">GHL Workflows</button>'
)

# ── 2. Add CRM CSS ──
crm_css = """
/* CRM Tab */
.crm-kpis { display: flex; gap: 14px; margin-bottom: 20px; flex-wrap: wrap; }
.crm-kpi {
  flex: 1; min-width: 160px; background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px 20px; display: flex; align-items: center; gap: 14px;
}
.crm-kpi-icon { font-size: 28px; width: 48px; height: 48px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.crm-kpi-data h3 { font-family: 'Cormorant Garamond', serif; font-size: 28px; font-weight: 600; margin: 0; line-height: 1; }
.crm-kpi-data p { font-size: 11px; color: rgba(255,255,255,0.5); margin: 2px 0 0; text-transform: uppercase; letter-spacing: 0.5px; }
.crm-filter-bar { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }
.crm-filter-bar select, .crm-filter-bar input {
  background: rgba(255,255,255,0.05); border: 1px solid var(--border); color: #fff;
  padding: 7px 12px; border-radius: 6px; font-size: 12px; font-family: 'DM Sans', sans-serif;
}
.crm-filter-bar select:focus, .crm-filter-bar input:focus { border-color: var(--gold); outline: none; }
.crm-table-wrap { overflow-x: auto; }
.crm-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
}
.crm-table th {
  text-align: left; padding: 8px 10px; font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.5px; color: var(--gold); border-bottom: 1px solid var(--border);
  font-weight: 600; cursor: pointer; white-space: nowrap;
}
.crm-table th:hover { color: #fff; }
.crm-table td {
  padding: 7px 10px; border-bottom: 1px solid rgba(255,255,255,0.04);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px;
}
.crm-table tr:hover td { background: rgba(201,185,154,0.05); }
.crm-type-badge {
  display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px;
  font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px;
}
.crm-type-franchise { background: rgba(74,158,110,0.15); color: #4a9e6e; }
.crm-type-vroperator { background: rgba(212,168,67,0.15); color: #d4a843; }
.crm-type-traveller { background: rgba(74,158,255,0.15); color: #4a9eff; }
.crm-type-unclassified { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.4); }
.crm-overlap-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--gold); margin-right: 4px; vertical-align: middle;
}
.crm-stage-tag {
  display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px;
  background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.6);
}
.crm-refresh-btn {
  background: rgba(255,255,255,0.06); border: 1px solid var(--border); color: rgba(255,255,255,0.6);
  padding: 7px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; font-family: 'DM Sans', sans-serif;
}
.crm-refresh-btn:hover { border-color: var(--gold); color: var(--gold); }
.crm-loading { text-align: center; padding: 40px; color: rgba(255,255,255,0.3); font-style: italic; }
"""

html = html.replace('/* CRM Tab */', '')  # remove if exists
html = html.replace('.tab-panel { display:none; }', crm_css + '\n.tab-panel { display:none; }')

# ── 3. Add CRM tab panel HTML ──
crm_html = """
    <!-- === CRM TAB === -->
    <section id="tab-crm" class="tab-panel">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;">
        <h2 style="font-family:'Cormorant Garamond',serif;font-size:22px;font-weight:600;color:var(--gold);margin:0;">
          CRM &mdash; Lead Summary
        </h2>
        <div style="display:flex;align-items:center;gap:12px;">
          <span id="crm-last-update" style="font-size:11px;color:rgba(255,255,255,0.35);"></span>
          <button class="crm-refresh-btn" onclick="crmLoad()">&#8635; Refresh</button>
        </div>
      </div>

      <div class="crm-kpis" id="crm-kpis">
        <div class="crm-kpi">
          <div class="crm-kpi-icon" style="background:rgba(74,158,110,0.12);color:#4a9e6e;">&#9733;</div>
          <div class="crm-kpi-data"><h3 id="crm-k-franchise">--</h3><p>Franchise</p></div>
        </div>
        <div class="crm-kpi">
          <div class="crm-kpi-icon" style="background:rgba(212,168,67,0.12);color:#d4a843;">&#9873;</div>
          <div class="crm-kpi-data"><h3 id="crm-k-vroperator">--</h3><p>VR Operator</p></div>
        </div>
        <div class="crm-kpi">
          <div class="crm-kpi-icon" style="background:rgba(74,158,255,0.12);color:#4a9eff;">&#9992;</div>
          <div class="crm-kpi-data"><h3 id="crm-k-traveller">--</h3><p>Traveller</p></div>
        </div>
        <div class="crm-kpi">
          <div class="crm-kpi-icon" style="background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.5);">&#8721;</div>
          <div class="crm-kpi-data"><h3 id="crm-k-total">--</h3><p>Distinct Total</p></div>
        </div>
      </div>

      <div class="crm-filter-bar">
        <select id="crm-f-type" onchange="crmFilter()">
          <option value="">All Types</option>
          <option value="Franchise">Franchise</option>
          <option value="VR Operator">VR Operator</option>
          <option value="Traveller">Traveller</option>
          <option value="Unclassified">Unclassified</option>
        </select>
        <select id="crm-f-acct" onchange="crmFilter()">
          <option value="">Both Accounts</option>
          <option value="Master">Master</option>
          <option value="Call Center">Call Center</option>
        </select>
        <select id="crm-f-source" onchange="crmFilter()">
          <option value="">All Sources</option>
        </select>
        <select id="crm-f-overlap" onchange="crmFilter()">
          <option value="">All</option>
          <option value="yes">In Both Accounts</option>
          <option value="no">Single Account Only</option>
        </select>
        <input id="crm-f-search" placeholder="Search name / email / phone..." oninput="crmFilter()" style="min-width:200px;">
        <span id="crm-f-count" style="font-size:12px;color:var(--gold);margin-left:auto;"></span>
      </div>

      <div class="crm-table-wrap">
        <table class="crm-table">
          <thead>
            <tr>
              <th onclick="crmSort('name')">Name</th>
              <th onclick="crmSort('type')">Type</th>
              <th onclick="crmSort('account')">Account</th>
              <th onclick="crmSort('source')">Source</th>
              <th onclick="crmSort('email')">Email</th>
              <th onclick="crmSort('phone')">Phone</th>
              <th onclick="crmSort('stage')">Pipeline &gt; Stage</th>
              <th onclick="crmSort('tags')">Tags</th>
              <th onclick="crmSort('overlap')">In Both</th>
              <th onclick="crmSort('dateAdded')">Added</th>
            </tr>
          </thead>
          <tbody id="crm-tbody"></tbody>
        </table>
      </div>
      <div class="crm-loading" id="crm-loading">Loading CRM data...</div>
    </section>
"""

# Insert before workflows tab panel
html = html.replace(
    '    <!-- === CRM TAB === -->',
    ''
)
html = html.replace(
    '<section id="tab-workflows"',
    crm_html + '\n    <section id="tab-workflows"'
)

# ── 4. Add CRM JavaScript ──
crm_js = r"""
/* ═══ CRM Tab Module ═══ */
var CRM_DATA = [];
var CRM_SORT = { col: 'name', asc: true };

function crmClassify(c) {
  var tags = (c.tags || []).map(function(t){ return t.toLowerCase(); });
  var src = (c.source || '').toLowerCase();
  if (tags.indexOf('franchise') >= 0 || (tags.indexOf('src:instantly') >= 0 && tags.indexOf('type:warm_reply') >= 0) || src.indexOf('instantly') >= 0) return 'Franchise';
  if (tags.indexOf('traveler') >= 0 || tags.indexOf('#hostfully') >= 0 || src.indexOf('hostfully') >= 0) return 'Traveller';
  if (tags.indexOf('str-scraper') >= 0 || tags.indexOf('hipcamp') >= 0 || src.indexOf('scraper') >= 0) return 'VR Operator';
  if (src.indexOf('cc pipeline') >= 0 || (!src && c.phone)) return 'Franchise';
  return 'Unclassified';
}

function crmTypeClass(t) {
  return 'crm-type-' + t.toLowerCase().replace(/\s+/g, '');
}

async function crmFetchContacts(loc, token) {
  var all = [];
  var url = '/contacts/?locationId=' + loc + '&limit=100';
  while (url) {
    var r = await fetch('https://services.leadconnectorhq.com' + url, {
      headers: { 'Authorization': 'Bearer ' + token, 'Version': '2021-07-28' }
    });
    var data = await r.json();
    var batch = data.contacts || [];
    all = all.concat(batch);
    var meta = data.meta || {};
    if (meta.startAfter && meta.startAfterId) {
      url = '/contacts/?locationId=' + loc + '&limit=100&startAfter=' + meta.startAfter + '&startAfterId=' + meta.startAfterId;
    } else { url = null; }
  }
  return all;
}

async function crmFetchOpps(loc, token) {
  var map = {};
  var pipelinesR = await fetch('https://services.leadconnectorhq.com/opportunities/pipelines?locationId=' + loc, {
    headers: { 'Authorization': 'Bearer ' + token, 'Version': '2021-07-28' }
  });
  var pData = await pipelinesR.json();
  var pipelines = pData.pipelines || [];
  var stageMap = {};
  pipelines.forEach(function(p) {
    (p.stages || []).forEach(function(s) { stageMap[s.id] = { pipeline: p.name, stage: s.name }; });
  });
  for (var pi = 0; pi < pipelines.length; pi++) {
    var pid = pipelines[pi].id;
    var page = 1;
    while (true) {
      try {
        var r = await fetch('https://services.leadconnectorhq.com/opportunities/search?location_id=' + loc + '&pipeline_id=' + pid + '&limit=100&page=' + page, {
          headers: { 'Authorization': 'Bearer ' + token, 'Version': '2021-07-28' }
        });
        var d = await r.json();
        var opps = d.opportunities || [];
        if (!opps.length) break;
        opps.forEach(function(o) {
          var cid = (o.contact || {}).id || o.contactId;
          if (!cid) return;
          var si = stageMap[o.pipelineStageId] || { pipeline: '?', stage: '?' };
          if (!map[cid]) map[cid] = [];
          map[cid].push(si.pipeline + ' > ' + si.stage);
        });
        if (d.meta && d.meta.nextPage) page++; else break;
      } catch(e) { break; }
    }
  }
  return map;
}

async function crmLoad() {
  var loading = document.getElementById('crm-loading');
  if (loading) loading.style.display = 'block';
  var tbody = document.getElementById('crm-tbody');
  if (tbody) tbody.innerHTML = '';

  try {
    var mContacts = await crmFetchContacts('1OOZ4AKIgxO8QKKMnIcK', 'pit-8e3c20cd-0d7f-43a3-be9d-c087e925b3e7');
    var cContacts = await crmFetchContacts('7hTDBClatcBgmUv36bZX', 'pit-48465a41-26c9-4115-8195-b0a557dbdb6d');
    var mOpps = await crmFetchOpps('1OOZ4AKIgxO8QKKMnIcK', 'pit-8e3c20cd-0d7f-43a3-be9d-c087e925b3e7');
    var cOpps = await crmFetchOpps('7hTDBClatcBgmUv36bZX', 'pit-48465a41-26c9-4115-8195-b0a557dbdb6d');

    // Build cross-match lookup
    var mEmails = {}, mPhones = {}, cEmails = {}, cPhones = {};
    mContacts.forEach(function(c) {
      if (c.email) mEmails[c.email.toLowerCase()] = true;
      if (c.phone) mPhones[c.phone] = true;
    });
    cContacts.forEach(function(c) {
      if (c.email) cEmails[c.email.toLowerCase()] = true;
      if (c.phone) cPhones[c.phone] = true;
    });

    CRM_DATA = [];
    mContacts.forEach(function(c) {
      var overlap = (c.email && cEmails[c.email.toLowerCase()]) || (c.phone && cPhones[c.phone]);
      var opps = mOpps[c.id] || [];
      CRM_DATA.push({
        id: c.id, name: c.contactName || '', email: c.email || '', phone: c.phone || '',
        source: c.source || '', tags: c.tags || [], type: crmClassify(c),
        account: 'Master', overlap: !!overlap, stage: opps.length ? opps[0] : '',
        dateAdded: c.dateAdded || '', dnd: c.dnd
      });
    });
    cContacts.forEach(function(c) {
      var overlap = (c.email && mEmails[c.email.toLowerCase()]) || (c.phone && mPhones[c.phone]);
      var opps = cOpps[c.id] || [];
      CRM_DATA.push({
        id: c.id, name: c.contactName || '', email: c.email || '', phone: c.phone || '',
        source: c.source || '', tags: c.tags || [], type: crmClassify(c),
        account: 'Call Center', overlap: !!overlap, stage: opps.length ? opps[0] : '',
        dateAdded: c.dateAdded || '', dnd: c.dnd
      });
    });

    // Populate source filter
    var sources = {};
    CRM_DATA.forEach(function(c) { if (c.source) sources[c.source] = true; });
    var srcSel = document.getElementById('crm-f-source');
    if (srcSel) {
      srcSel.innerHTML = '<option value="">All Sources</option>';
      Object.keys(sources).sort().forEach(function(s) {
        srcSel.innerHTML += '<option value="' + s + '">' + s + '</option>';
      });
    }

    // KPIs — distinct count
    var seen = {};
    var distinctByType = { 'Franchise': 0, 'VR Operator': 0, 'Traveller': 0, 'Unclassified': 0 };
    var distinctTotal = 0;
    CRM_DATA.forEach(function(c) {
      var key = (c.email || c.phone || c.id).toLowerCase();
      if (!seen[key]) { seen[key] = true; distinctByType[c.type]++; distinctTotal++; }
    });

    var kf = document.getElementById('crm-k-franchise');
    var kv = document.getElementById('crm-k-vroperator');
    var kt = document.getElementById('crm-k-traveller');
    var ka = document.getElementById('crm-k-total');
    if (kf) kf.textContent = distinctByType['Franchise'];
    if (kv) kv.textContent = distinctByType['VR Operator'];
    if (kt) kt.textContent = distinctByType['Traveller'];
    if (ka) ka.textContent = distinctTotal;

    document.getElementById('crm-last-update').textContent = 'Updated ' + new Date().toLocaleTimeString();
    crmFilter();
  } catch(e) {
    console.error('[crm] load error:', e);
    if (loading) loading.innerHTML = 'Error loading CRM data: ' + e.message;
  }
}

function crmFilter() {
  var fType = document.getElementById('crm-f-type').value;
  var fAcct = document.getElementById('crm-f-acct').value;
  var fSource = document.getElementById('crm-f-source').value;
  var fOverlap = document.getElementById('crm-f-overlap').value;
  var fSearch = (document.getElementById('crm-f-search').value || '').toLowerCase().trim();

  var filtered = CRM_DATA.filter(function(c) {
    if (fType && c.type !== fType) return false;
    if (fAcct && c.account !== fAcct) return false;
    if (fSource && c.source !== fSource) return false;
    if (fOverlap === 'yes' && !c.overlap) return false;
    if (fOverlap === 'no' && c.overlap) return false;
    if (fSearch) {
      var hay = (c.name + ' ' + c.email + ' ' + c.phone + ' ' + c.tags.join(' ')).toLowerCase();
      if (hay.indexOf(fSearch) < 0) return false;
    }
    return true;
  });

  // Sort
  filtered.sort(function(a, b) {
    var va = a[CRM_SORT.col] || '';
    var vb = b[CRM_SORT.col] || '';
    if (typeof va === 'boolean') { va = va ? 1 : 0; vb = vb ? 1 : 0; }
    if (va < vb) return CRM_SORT.asc ? -1 : 1;
    if (va > vb) return CRM_SORT.asc ? 1 : -1;
    return 0;
  });

  var countEl = document.getElementById('crm-f-count');
  if (countEl) countEl.textContent = filtered.length + ' of ' + CRM_DATA.length + ' contacts';

  var tbody = document.getElementById('crm-tbody');
  if (!tbody) return;
  var loading = document.getElementById('crm-loading');
  if (loading) loading.style.display = 'none';

  var html = '';
  filtered.forEach(function(c) {
    var dateStr = c.dateAdded ? new Date(c.dateAdded).toLocaleDateString('en-US', {month:'short', day:'numeric'}) : '';
    var tagStr = c.tags.slice(0, 3).join(', ');
    if (c.tags.length > 3) tagStr += ' +' + (c.tags.length - 3);
    html += '<tr>'
      + '<td title="' + c.name + '">' + c.name + '</td>'
      + '<td><span class="crm-type-badge ' + crmTypeClass(c.type) + '">' + c.type + '</span></td>'
      + '<td>' + c.account + '</td>'
      + '<td>' + c.source + '</td>'
      + '<td>' + c.email + '</td>'
      + '<td>' + c.phone + '</td>'
      + '<td>' + (c.stage ? '<span class="crm-stage-tag">' + c.stage + '</span>' : '') + '</td>'
      + '<td title="' + c.tags.join(', ') + '">' + tagStr + '</td>'
      + '<td>' + (c.overlap ? '<span class="crm-overlap-dot"></span>Yes' : '') + '</td>'
      + '<td>' + dateStr + '</td>'
      + '</tr>';
  });
  tbody.innerHTML = html;
}

function crmSort(col) {
  if (CRM_SORT.col === col) { CRM_SORT.asc = !CRM_SORT.asc; }
  else { CRM_SORT.col = col; CRM_SORT.asc = true; }
  crmFilter();
}

// Auto-load when CRM tab is clicked
document.addEventListener('click', function(e) {
  var btn = e.target.closest && e.target.closest('.tab-btn[data-tab="crm"]');
  if (btn && CRM_DATA.length === 0) setTimeout(crmLoad, 100);
});
/* ═══ End CRM Module ═══ */
"""

# Insert before OpenClaw JS
html = html.replace('/* === OpenClaw Agent Monitor === */', crm_js + '\n/* === OpenClaw Agent Monitor === */')

with open(FILE, 'w') as f:
    f.write(html)

# Verify
checks = [
    ("Nav button", 'data-tab="crm"' in html),
    ("Tab panel", 'id="tab-crm"' in html),
    ("KPIs", 'crm-k-franchise' in html),
    ("Filter bar", 'crm-f-type' in html),
    ("Table", 'crm-tbody' in html),
    ("JS classify", 'crmClassify' in html),
    ("JS fetch", 'crmFetchContacts' in html),
    ("JS opps", 'crmFetchOpps' in html),
    ("CSS", '.crm-type-franchise' in html),
]
for name, ok in checks:
    print(("  OK" if ok else "MISS") + " - " + name)
print("Done")
