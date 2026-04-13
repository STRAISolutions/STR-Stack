#!/usr/bin/env python3
"""GHL Lead Audit v2 — Segmented by Customer Type (Franchise / VR Operator / Traveller)"""
import urllib.request, json

BASE = "https://services.leadconnectorhq.com"
ACCOUNTS = [
    {"name": "Master", "loc": "1OOZ4AKIgxO8QKKMnIcK", "token": "pit-8e3c20cd-0d7f-43a3-be9d-c087e925b3e7"},
    {"name": "Call Center", "loc": "7hTDBClatcBgmUv36bZX", "token": "pit-48465a41-26c9-4115-8195-b0a557dbdb6d"},
]

def get_all(loc, token):
    contacts = []
    url = f"/contacts/?locationId={loc}&limit=100"
    while url:
        req = urllib.request.Request(f"{BASE}{url}", headers={
            "Authorization": f"Bearer {token}", "Version": "2021-07-28",
            "Accept": "application/json", "User-Agent": "STR-Stack/1.0"
        })
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        contacts.extend(data.get("contacts", []))
        meta = data.get("meta", {})
        sa, said = meta.get("startAfter"), meta.get("startAfterId")
        url = f"/contacts/?locationId={loc}&limit=100&startAfter={sa}&startAfterId={said}" if sa and said else None
    return contacts

def get_opps(loc, token, pipeline_id):
    opps = []
    url = f"/opportunities/search?location_id={loc}&pipeline_id={pipeline_id}"
    req = urllib.request.Request(f"{BASE}{url}", headers={
        "Authorization": f"Bearer {token}", "Version": "2021-07-28",
        "Accept": "application/json", "User-Agent": "STR-Stack/1.0"
    }, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        opps = data.get("opportunities", [])
    except:
        pass
    return opps

def get_pipelines(loc, token):
    req = urllib.request.Request(f"{BASE}/opportunities/pipelines?locationId={loc}", headers={
        "Authorization": f"Bearer {token}", "Version": "2021-07-28",
        "Accept": "application/json", "User-Agent": "STR-Stack/1.0"
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("pipelines", [])

# Pull data
master = get_all(ACCOUNTS[0]["loc"], ACCOUNTS[0]["token"])
cc = get_all(ACCOUNTS[1]["loc"], ACCOUNTS[1]["token"])
m_pipelines = get_pipelines(ACCOUNTS[0]["loc"], ACCOUNTS[0]["token"])
c_pipelines = get_pipelines(ACCOUNTS[1]["loc"], ACCOUNTS[1]["token"])

# Build pipeline stage lookup
def build_stage_map(pipelines):
    pmap = {}
    for p in pipelines:
        pid = p["id"]
        pname = p["name"]
        for s in p.get("stages", []):
            pmap[s["id"]] = {"pipeline": pname, "pipeline_id": pid, "stage": s["name"]}
    return pmap

m_stage_map = build_stage_map(m_pipelines)
c_stage_map = build_stage_map(c_pipelines)

# Get all opportunities for pipeline mapping
def get_all_opps(loc, token, pipelines):
    all_opps = {}
    for p in pipelines:
        pid = p["id"]
        page = 1
        while True:
            try:
                req = urllib.request.Request(
                    f"{BASE}/opportunities/search?location_id={loc}&pipeline_id={pid}&limit=100&page={page}",
                    headers={"Authorization": f"Bearer {token}", "Version": "2021-07-28",
                             "Accept": "application/json", "User-Agent": "STR-Stack/1.0"},
                    method="GET"
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read())
                opps = data.get("opportunities", [])
                if not opps:
                    break
                for o in opps:
                    cid = o.get("contact", {}).get("id") or o.get("contactId")
                    if cid:
                        if cid not in all_opps:
                            all_opps[cid] = []
                        stage_info = m_stage_map.get(o.get("pipelineStageId"), c_stage_map.get(o.get("pipelineStageId"), {}))
                        all_opps[cid].append({
                            "pipeline": stage_info.get("pipeline", p["name"]),
                            "stage": stage_info.get("stage", o.get("pipelineStageId", "?")),
                            "status": o.get("status", ""),
                        })
                meta = data.get("meta", {})
                if meta.get("nextPage"):
                    page += 1
                else:
                    break
            except Exception as e:
                break
    return all_opps

m_opps = get_all_opps(ACCOUNTS[0]["loc"], ACCOUNTS[0]["token"], m_pipelines)
c_opps = get_all_opps(ACCOUNTS[1]["loc"], ACCOUNTS[1]["token"], c_pipelines)

# ── Classify customer type ──
# Method: Tags + Source + Pipeline
# Franchise:    tag "franchise" OR tag "src:instantly" OR source contains "Instantly"
# VR Operator:  tag "str-scraper" OR tag "hipcamp" OR source contains "Scraper" OR source "STR Solutions"
# Traveller:    tag "traveler" OR tag "#hostfully" OR source contains "Hostfully"
# Unclassified: everything else

def classify(c, opps_map):
    tags = [t.lower() for t in c.get("tags", [])]
    source = (c.get("source") or "").lower()
    cid = c.get("id", "")
    contact_opps = opps_map.get(cid, [])

    # Check pipeline for additional signal
    in_b1 = any("traveler" in o.get("pipeline","").lower() or "inquir" in o.get("pipeline","").lower() for o in contact_opps)
    in_b2 = any("booking" in o.get("pipeline","").lower() for o in contact_opps)
    in_a2 = any("activation" in o.get("pipeline","").lower() for o in contact_opps)

    # Franchise
    if "franchise" in tags or ("src:instantly" in tags and "type:warm_reply" in tags) or "instantly" in source:
        return "Franchise"
    # Traveller
    if "traveler" in tags or "#hostfully" in tags or "hostfully" in source or in_b1 or in_b2:
        return "Traveller"
    # VR Operator
    if "str-scraper" in tags or "hipcamp" in tags or "scraper" in source or "str solutions" in source:
        return "VR Operator"
    # CC phone leads - likely franchise prospects (called in from campaign)
    if "cc pipeline sync" in source or (not source and c.get("phone")):
        return "Franchise"

    return "Unclassified"

# Cross-match
def get_keys(c):
    keys = set()
    e = (c.get("email") or "").strip().lower()
    p = (c.get("phone") or "").strip()
    if e: keys.add(("email", e))
    if p: keys.add(("phone", p))
    return keys

cc_lookup = {}
for c in cc:
    for k in get_keys(c): cc_lookup.setdefault(k, []).append(c)
master_lookup = {}
for c in master:
    for k in get_keys(c): master_lookup.setdefault(k, []).append(c)

m_overlap = set()
c_overlap = set()
for c in master:
    for k in get_keys(c):
        if k in cc_lookup:
            m_overlap.add(c["id"])
            for x in cc_lookup[k]: c_overlap.add(x["id"])
for c in cc:
    for k in get_keys(c):
        if k in master_lookup: c_overlap.add(c["id"])

# Distinct
seen = set()
distinct = 0
for c in master + cc:
    ks = get_keys(c)
    if not ks: distinct += 1; continue
    fk = frozenset(ks)
    if fk not in seen: seen.add(fk); distinct += 1

# Classify all
m_classified = [(c, classify(c, m_opps)) for c in master]
c_classified = [(c, classify(c, c_opps)) for c in cc]

# ── Print Report ──
W = 95
sep = "=" * W
dsep = "-" * W

print(sep)
print("GHL LEAD AUDIT — BY CUSTOMER TYPE".center(W))
print("Classification: Tags + Source + Pipeline".center(W))
print(sep)
print(f"  Master Sub-Account:      {len(master)} contacts")
print(f"  Call Center Sub-Account: {len(cc)} contacts")
print(f"  Overlap (in both):       {len(m_overlap)} master / {len(c_overlap)} CC")
print(f"  DISTINCT LEADS (TOTAL):  {distinct}")

# Type counts
types = ["Franchise", "VR Operator", "Traveller", "Unclassified"]

for acct_name, classified, overlap_ids, opps_map in [
    ("MASTER", m_classified, m_overlap, m_opps),
    ("CALL CENTER", c_classified, c_overlap, c_opps)
]:
    print()
    print(dsep)
    print(f"{acct_name} SUB-ACCOUNT — BY CUSTOMER TYPE".center(W))
    print(dsep)

    for ctype in types:
        group = [(c, t) for c, t in classified if t == ctype]
        if not group:
            continue
        overlap_count = sum(1 for c, _ in group if c["id"] in overlap_ids)
        email_count = sum(1 for c, _ in group if c.get("email"))
        phone_count = sum(1 for c, _ in group if c.get("phone"))
        dnd_count = sum(1 for c, _ in group if c.get("dnd"))

        print(f"\n  [{ctype.upper()}] — {len(group)} contacts  (In other acct: {overlap_count})")

        # Source breakdown within type
        src_counts = {}
        for c, _ in group:
            src = c.get("source") or "(no source)"
            src_counts[src] = src_counts.get(src, 0) + 1

        print(f"    Sources:")
        for s in sorted(src_counts, key=lambda x: src_counts[x], reverse=True):
            print(f"      {s:<38} {src_counts[s]:>4}")

        # Tag breakdown within type
        tag_counts = {}
        for c, _ in group:
            for t in c.get("tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        print(f"    Tags:")
        for t in sorted(tag_counts, key=lambda x: tag_counts[x], reverse=True):
            print(f"      {t:<38} {tag_counts[t]:>4}")

        # Pipeline/Stage breakdown
        stage_counts = {}
        no_opp = 0
        for c, _ in group:
            cid = c["id"]
            contact_opps = opps_map.get(cid, [])
            if not contact_opps:
                no_opp += 1
            for o in contact_opps:
                key = f"{o['pipeline']} > {o['stage']}"
                stage_counts[key] = stage_counts.get(key, 0) + 1
        if stage_counts or no_opp:
            print(f"    Pipeline Stages:")
            for ps in sorted(stage_counts, key=lambda x: stage_counts[x], reverse=True):
                print(f"      {ps:<55} {stage_counts[ps]:>4}")
            if no_opp:
                print(f"      {'(no opportunity)':55} {no_opp:>4}")

        print(f"    Has Email: {email_count}  |  Has Phone: {phone_count}  |  DND: {dnd_count}")

# Distinct by type
print()
print(dsep)
print("DISTINCT LEADS BY CUSTOMER TYPE".center(W))
print(dsep)

all_classified = []
seen_keys = set()
for c, t in m_classified + c_classified:
    ks = get_keys(c)
    if not ks:
        all_classified.append((c, t))
        continue
    fk = frozenset(ks)
    if fk not in seen_keys:
        seen_keys.add(fk)
        all_classified.append((c, t))

for ctype in types:
    count = sum(1 for _, t in all_classified if t == ctype)
    if count:
        print(f"  {ctype:<20} {count:>6}")
print(f"  {'TOTAL':<20} {len(all_classified):>6}")

print()
print(sep)
print("CLASSIFICATION METHOD".center(W))
print(sep)
print("  Franchise:     tag 'franchise' OR tag 'src:instantly' + 'type:warm_reply'")
print("                 OR source contains 'Instantly' OR CC phone leads")
print("  VR Operator:   tag 'str-scraper' OR 'hipcamp' OR source contains 'Scraper'")
print("  Traveller:     tag 'traveler' OR '#hostfully' OR source contains 'Hostfully'")
print("                 OR in B1/B2 pipeline")
print("  Unclassified:  none of the above")
print(sep)
