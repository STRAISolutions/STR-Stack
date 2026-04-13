#!/usr/bin/env python3
"""CRM Tab v2 — Full dropdowns, live stats, deep links to GHL"""

FILE = '/srv/str-stack-public/dashboard.html'
with open(FILE, 'r') as f:
    html = f.read()

# GHL contact URL patterns
# Master: https://app.gohighlevel.com/v2/location/1OOZ4AKIgxO8QKKMnIcK/contacts/detail/{contactId}
# CC:     https://app.gohighlevel.com/v2/location/7hTDBClatcBgmUv36bZX/contacts/detail/{contactId}

# ── 1. Replace KPI cards with clickable ones ──
old_kpis = """<div class="crm-kpis" id="crm-kpis">
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
      </div>"""

new_kpis = """<div class="crm-kpis" id="crm-kpis">
        <div class="crm-kpi" style="cursor:pointer;" onclick="crmKpiClick('Franchise')">
          <div class="crm-kpi-icon" style="background:rgba(74,158,110,0.12);color:#4a9e6e;">&#9733;</div>
          <div class="crm-kpi-data">
            <h3 id="crm-k-franchise">--</h3>
            <p>Franchise</p>
            <span id="crm-k-franchise-sub" style="font-size:10px;color:rgba(255,255,255,0.3);"></span>
          </div>
        </div>
        <div class="crm-kpi" style="cursor:pointer;" onclick="crmKpiClick('VR Operator')">
          <div class="crm-kpi-icon" style="background:rgba(212,168,67,0.12);color:#d4a843;">&#9873;</div>
          <div class="crm-kpi-data">
            <h3 id="crm-k-vroperator">--</h3>
            <p>VR Operator</p>
            <span id="crm-k-vroperator-sub" style="font-size:10px;color:rgba(255,255,255,0.3);"></span>
          </div>
        </div>
        <div class="crm-kpi" style="cursor:pointer;" onclick="crmKpiClick('Traveller')">
          <div class="crm-kpi-icon" style="background:rgba(74,158,255,0.12);color:#4a9eff;">&#9992;</div>
          <div class="crm-kpi-data">
            <h3 id="crm-k-traveller">--</h3>
            <p>Traveller</p>
            <span id="crm-k-traveller-sub" style="font-size:10px;color:rgba(255,255,255,0.3);"></span>
          </div>
        </div>
        <div class="crm-kpi" style="cursor:pointer;" onclick="crmKpiClick('')">
          <div class="crm-kpi-icon" style="background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.5);">&#8721;</div>
          <div class="crm-kpi-data">
            <h3 id="crm-k-total">--</h3>
            <p>Distinct Total</p>
            <span id="crm-k-total-sub" style="font-size:10px;color:rgba(255,255,255,0.3);"></span>
          </div>
        </div>
      </div>"""

html = html.replace(old_kpis, new_kpis)

# ── 2. Replace filter bar with full dropdowns ──
old_filters = """<div class="crm-filter-bar">
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
      </div>"""

new_filters = """<div class="crm-filter-bar">
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
        <select id="crm-f-pipeline" onchange="crmFilter()">
          <option value="">All Pipelines</option>
        </select>
        <select id="crm-f-tag" onchange="crmFilter()">
          <option value="">All Tags</option>
        </select>
        <select id="crm-f-overlap" onchange="crmFilter()">
          <option value="">All</option>
          <option value="yes">In Both Accounts</option>
          <option value="no">Single Account Only</option>
        </select>
        <select id="crm-f-hascontact" onchange="crmFilter()">
          <option value="">Any Contact Info</option>
          <option value="email">Has Email</option>
          <option value="phone">Has Phone</option>
          <option value="both">Has Email + Phone</option>
          <option value="none">No Email or Phone</option>
        </select>
        <input id="crm-f-search" placeholder="Search name / email / phone / tag..." oninput="crmFilter()" style="min-width:200px;">
        <span id="crm-f-count" style="font-size:12px;color:var(--gold);margin-left:auto;"></span>
      </div>"""

html = html.replace(old_filters, new_filters)

# ── 3. Replace the entire CRM JS module ──
old_js_start = '/* ═══ CRM Tab Module ═══ */'
old_js_end = '/* ═══ End CRM Module ═══ */'

start_idx = html.find(old_js_start)
end_idx = html.find(old_js_end)
if start_idx < 0 or end_idx < 0:
    print("ERROR: Could not find CRM JS markers")
    exit(1)

new_crm_js = r"""/* ═══ CRM Tab Module ═══ */
var CRM_DATA = [];
var CRM_SORT = { col: 'name', asc: true };
var CRM_GHL_MASTER = 'https://app.gohighlevel.com/v2/location/1OOZ4AKIgxO8QKKMnIcK/contacts/detail/';
var CRM_GHL_CC = 'https://app.gohighlevel.com/v2/location/7hTDBClatcBgmUv36bZX/contacts/detail/';

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

function crmKpiClick(type) {
  var sel = document.getElementById('crm-f-type');
  if (sel) { sel.value = type; crmFilter(); }
}

async function crmFetchContacts(loc, token) {
  var all = [];
  var url = '/contacts/?locationId=' + loc + '&limit=100';
  while (url) {
    var r = await fetch('https://services.leadconnectorhq.com' + url, {
      headers: { 'Authorization': 'Bearer ' + token, 'Version': '2021-07-28' }
    });
    var data = await r.json();
    all = all.concat(data.contacts || []);
    var meta = data.meta || {};
    if (meta.startAfter && meta.startAfterId) {
      url = '/contacts/?locationId=' + loc + '&limit=100&startAfter=' + meta.startAfter + '&startAfterId=' + meta.startAfterId;
    } else { url = null; }
  }
  return all;
}

async function crmFetchOpps(loc, token) {
  var map = {};
  var pr = await fetch('https://services.leadconnectorhq.com/opportunities/pipelines?locationId=' + loc, {
    headers: { 'Authorization': 'Bearer ' + token, 'Version': '2021-07-28' }
  });
  var pData = await pr.json();
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
        account: 'Master', loc: '1OOZ4AKIgxO8QKKMnIcK',
        overlap: !!overlap, stage: opps.length ? opps[0] : '', allStages: opps,
        dateAdded: c.dateAdded || '', dnd: c.dnd
      });
    });
    cContacts.forEach(function(c) {
      var overlap = (c.email && mEmails[c.email.toLowerCase()]) || (c.phone && mPhones[c.phone]);
      var opps = cOpps[c.id] || [];
      CRM_DATA.push({
        id: c.id, name: c.contactName || '', email: c.email || '', phone: c.phone || '',
        source: c.source || '', tags: c.tags || [], type: crmClassify(c),
        account: 'Call Center', loc: '7hTDBClatcBgmUv36bZX',
        overlap: !!overlap, stage: opps.length ? opps[0] : '', allStages: opps,
        dateAdded: c.dateAdded || '', dnd: c.dnd
      });
    });

    // Populate source dropdown
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
    }

    // KPIs — distinct + total
    var seen = {};
    var distinctByType = { 'Franchise': 0, 'VR Operator': 0, 'Traveller': 0, 'Unclassified': 0 };
    var totalByType = { 'Franchise': 0, 'VR Operator': 0, 'Traveller': 0, 'Unclassified': 0 };
    var distinctTotal = 0;
    CRM_DATA.forEach(function(c) {
      totalByType[c.type] = (totalByType[c.type]||0) + 1;
      var key = (c.email || c.phone || c.id).toLowerCase();
      if (!seen[key]) { seen[key] = true; distinctByType[c.type]++; distinctTotal++; }
    });

    document.getElementById('crm-k-franchise').textContent = distinctByType['Franchise'];
    document.getElementById('crm-k-vroperator').textContent = distinctByType['VR Operator'];
    document.getElementById('crm-k-traveller').textContent = distinctByType['Traveller'];
    document.getElementById('crm-k-total').textContent = distinctTotal;
    document.getElementById('crm-k-franchise-sub').textContent = totalByType['Franchise'] + ' total across accounts';
    document.getElementById('crm-k-vroperator-sub').textContent = totalByType['VR Operator'] + ' total across accounts';
    document.getElementById('crm-k-traveller-sub').textContent = totalByType['Traveller'] + ' total across accounts';
    document.getElementById('crm-k-total-sub').textContent = CRM_DATA.length + ' total rows';

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
  var fPipeline = document.getElementById('crm-f-pipeline').value;
  var fTag = document.getElementById('crm-f-tag').value;
  var fOverlap = document.getElementById('crm-f-overlap').value;
  var fContact = document.getElementById('crm-f-hascontact').value;
  var fSearch = (document.getElementById('crm-f-search').value || '').toLowerCase().trim();

  var filtered = CRM_DATA.filter(function(c) {
    if (fType && c.type !== fType) return false;
    if (fAcct && c.account !== fAcct) return false;
    if (fSource && c.source !== fSource) return false;
    if (fPipeline === '_none_' && c.allStages && c.allStages.length > 0) return false;
    if (fPipeline && fPipeline !== '_none_' && (!c.allStages || c.allStages.indexOf(fPipeline) < 0)) return false;
    if (fTag && c.tags.indexOf(fTag) < 0) return false;
    if (fOverlap === 'yes' && !c.overlap) return false;
    if (fOverlap === 'no' && c.overlap) return false;
    if (fContact === 'email' && !c.email) return false;
    if (fContact === 'phone' && !c.phone) return false;
    if (fContact === 'both' && (!c.email || !c.phone)) return false;
    if (fContact === 'none' && (c.email || c.phone)) return false;
    if (fSearch) {
      var hay = (c.name + ' ' + c.email + ' ' + c.phone + ' ' + c.tags.join(' ') + ' ' + c.source + ' ' + c.stage).toLowerCase();
      if (hay.indexOf(fSearch) < 0) return false;
    }
    return true;
  });

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

  var rows = '';
  var ghlBase = { 'Master': CRM_GHL_MASTER, 'Call Center': CRM_GHL_CC };
  filtered.forEach(function(c) {
    var dateStr = c.dateAdded ? new Date(c.dateAdded).toLocaleDateString('en-US', {month:'short', day:'numeric'}) : '';
    var tagStr = c.tags.slice(0, 3).join(', ');
    if (c.tags.length > 3) tagStr += ' +' + (c.tags.length - 3);
    var ghlUrl = (ghlBase[c.account] || '') + c.id;
    var nameLink = '<a href="' + ghlUrl + '" target="_blank" style="color:var(--text);text-decoration:none;border-bottom:1px dotted var(--border);" title="Open in GHL">' + (c.name || '(no name)') + '</a>';
    var stageHtml = '';
    if (c.allStages && c.allStages.length > 0) {
      stageHtml = '<span class="crm-stage-tag">' + c.allStages[0] + '</span>';
      if (c.allStages.length > 1) stageHtml += ' <span style="font-size:9px;color:var(--muted);">+' + (c.allStages.length-1) + '</span>';
    }
    rows += '<tr>'
      + '<td>' + nameLink + '</td>'
      + '<td><span class="crm-type-badge ' + crmTypeClass(c.type) + '">' + c.type + '</span></td>'
      + '<td>' + c.account + '</td>'
      + '<td>' + c.source + '</td>'
      + '<td>' + c.email + '</td>'
      + '<td>' + c.phone + '</td>'
      + '<td>' + stageHtml + '</td>'
      + '<td title="' + c.tags.join(', ') + '">' + tagStr + '</td>'
      + '<td>' + (c.overlap ? '<span class="crm-overlap-dot"></span>Yes' : '') + '</td>'
      + '<td>' + dateStr + '</td>'
      + '</tr>';
  });
  tbody.innerHTML = rows;
}

function crmSort(col) {
  if (CRM_SORT.col === col) { CRM_SORT.asc = !CRM_SORT.asc; }
  else { CRM_SORT.col = col; CRM_SORT.asc = true; }
  crmFilter();
}

document.addEventListener('click', function(e) {
  var btn = e.target.closest && e.target.closest('.tab-btn[data-tab="crm"]');
  if (btn && CRM_DATA.length === 0) setTimeout(crmLoad, 100);
});
/* ═══ End CRM Module ═══ */
"""

html = html[:start_idx] + new_crm_js + html[end_idx + len(old_js_end):]

# ── 4. Add clickable hover to KPI cards CSS ──
html = html.replace(
    '.crm-kpi-data p { font-size: 11px;',
    '.crm-kpi:hover { border-color: var(--gold); transform: translateY(-1px); }\n.crm-kpi-data p { font-size: 11px;'
)

with open(FILE, 'w') as f:
    f.write(html)

checks = [
    ("KPI click", "crmKpiClick" in html),
    ("KPI sub-labels", "crm-k-franchise-sub" in html),
    ("Pipeline filter", "crm-f-pipeline" in html),
    ("Tag filter", "crm-f-tag" in html),
    ("Contact info filter", "crm-f-hascontact" in html),
    ("GHL links", "CRM_GHL_MASTER" in html),
    ("Name links", "Open in GHL" in html),
    ("Source counts", "sources[s]" in html),
    ("Pipeline populate", "pipeSel" in html),
    ("Tag populate", "tagSel" in html),
    ("KPI hover CSS", "crm-kpi:hover" in html),
]
for name, ok in checks:
    print(("  OK" if ok else "MISS") + " - " + name)
print("Done")
