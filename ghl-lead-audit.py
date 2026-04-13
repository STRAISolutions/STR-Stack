#!/usr/bin/env python3
"""GHL Lead Audit — Both Sub-Accounts"""
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

master = get_all(ACCOUNTS[0]["loc"], ACCOUNTS[0]["token"])
cc = get_all(ACCOUNTS[1]["loc"], ACCOUNTS[1]["token"])

def get_keys(c):
    keys = set()
    e = (c.get("email") or "").strip().lower()
    p = (c.get("phone") or "").strip()
    if e: keys.add(("email", e))
    if p: keys.add(("phone", p))
    return keys

# Build lookup indexes
cc_lookup = {}
for c in cc:
    for k in get_keys(c): cc_lookup.setdefault(k, []).append(c)
master_lookup = {}
for c in master:
    for k in get_keys(c): master_lookup.setdefault(k, []).append(c)

# Cross-match
m_overlap = set()
c_overlap = set()
for c in master:
    for k in get_keys(c):
        if k in cc_lookup:
            m_overlap.add(c["id"])
            for x in cc_lookup[k]: c_overlap.add(x["id"])
for c in cc:
    for k in get_keys(c):
        if k in master_lookup:
            c_overlap.add(c["id"])

# Distinct leads
seen = set()
distinct = 0
for c in master + cc:
    ks = get_keys(c)
    if not ks:
        distinct += 1
        continue
    fk = frozenset(ks)
    if fk not in seen:
        seen.add(fk)
        distinct += 1

# Source breakdown helper
def src_table(contacts, overlap_ids):
    sources = {}
    for c in contacts:
        src = c.get("source") or "(no source)"
        if src not in sources:
            sources[src] = {"count": 0, "overlap": 0, "dnd": 0, "email": 0, "phone": 0}
        s = sources[src]
        s["count"] += 1
        if c["id"] in overlap_ids: s["overlap"] += 1
        if c.get("dnd"): s["dnd"] += 1
        if c.get("email"): s["email"] += 1
        if c.get("phone"): s["phone"] += 1
    return sources

def tag_table(contacts):
    tags = {}
    for c in contacts:
        for t in c.get("tags", []): tags[t] = tags.get(t, 0) + 1
    return tags

m_src = src_table(master, m_overlap)
c_src = src_table(cc, c_overlap)
m_tags = tag_table(master)
c_tags = tag_table(cc)

W = 90
sep = "=" * W
dsep = "-" * W
hdr = "GHL LEAD SUMMARY"
print(sep)
print(hdr.center(W))
print(sep)
print(f"  Master Sub-Account:      {len(master)} contacts")
print(f"  Call Center Sub-Account: {len(cc)} contacts")
print(f"  Overlap (in both):       {len(m_overlap)} master / {len(c_overlap)} CC")
print(f"  DISTINCT LEADS (TOTAL):  {distinct}")
print()
print(dsep)
title1 = "MASTER SUB-ACCOUNT - BY SOURCE"
print(title1.center(W))
print(dsep)
row = "  {:<35} {:>6} {:>6} {:>6} {:>5} {:>7}"
print(row.format("Source", "Count", "Email", "Phone", "DND", "In CC"))
print(row.format("-" * 35, "-" * 6, "-" * 6, "-" * 6, "-" * 5, "-" * 7))
for src in sorted(m_src, key=lambda x: m_src[x]["count"], reverse=True):
    s = m_src[src]
    print(row.format(src[:35], s["count"], s["email"], s["phone"], s["dnd"], s["overlap"]))
print(row.format("TOTAL", len(master), "", "", "", str(len(m_overlap))))

print()
print(dsep)
title2 = "CALL CENTER SUB-ACCOUNT - BY SOURCE"
print(title2.center(W))
print(dsep)
row2 = "  {:<35} {:>6} {:>6} {:>6} {:>5} {:>10}"
print(row2.format("Source", "Count", "Email", "Phone", "DND", "In Master"))
print(row2.format("-" * 35, "-" * 6, "-" * 6, "-" * 6, "-" * 5, "-" * 10))
for src in sorted(c_src, key=lambda x: c_src[x]["count"], reverse=True):
    s = c_src[src]
    print(row2.format(src[:35], s["count"], s["email"], s["phone"], s["dnd"], s["overlap"]))
print(row2.format("TOTAL", len(cc), "", "", "", str(len(c_overlap))))

print()
print(dsep)
title3 = "MASTER - TAGS"
print(title3.center(W))
print(dsep)
for t in sorted(m_tags, key=lambda x: m_tags[x], reverse=True):
    print(f"  {t:<35} {m_tags[t]:>6}")

print()
print(dsep)
title4 = "CALL CENTER - TAGS"
print(title4.center(W))
print(dsep)
for t in sorted(c_tags, key=lambda x: c_tags[x], reverse=True):
    print(f"  {t:<35} {c_tags[t]:>6}")

print()

# Overlap detail
print(dsep)
title5 = "OVERLAP DETAIL - CONTACTS IN BOTH ACCOUNTS"
print(title5.center(W))
print(dsep)
row3 = "  {:<30} {:<35} {:<20}"
print(row3.format("Name", "Email", "Source (Master)"))
print(row3.format("-" * 30, "-" * 35, "-" * 20))
for c in master:
    if c["id"] in m_overlap:
        print(row3.format(
            (c.get("contactName") or "")[:30],
            (c.get("email") or "")[:35],
            (c.get("source") or "")[:20]
        ))
print(f"\n  Total overlapping: {len(m_overlap)} contacts exist in both sub-accounts")
print(sep)
