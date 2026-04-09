#!/usr/bin/env python3
"""
str_pipeline.py — Daily STR contact pipeline

Flow per new contact:
  1. Apollo people/match  → find email by host name + property
  2. Fallback             → scrape listing URL for email
  3. GHL                  → cold storage (ALL contacts, with or without email)
  4. Clay                 → enrichment push (if CLAY_WEBHOOK_URL set)
  5. Instantly ICP 1      → outreach (only if email found)
  6. Discord #general     → daily summary

Usage:
    python3 str_pipeline.py [--markets "City, ST" ...] [--batch N]

Required env vars (in /root/.openclaw/.env):
    GHL_MASTER_OAUTH        OAuth token for GHL master subaccount
    GHL_MASTER_LOCATION     GHL master location ID
    INSTANTLY_API_KEY_V2    Instantly API key
    APOLLO_API_KEY          Apollo.io API key (add to .env)
    DISCORD_TOKEN           Discord bot token (auto-posts to #general)

Optional:
    CLAY_WEBHOOK_URL        Clay HTTP API Source URL (set up in Clay UI)
"""

import os, sys, csv, json, time, subprocess, re, logging
from datetime import date
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError

# ─── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path("/root/str-stack/prompts")
SCRAPER    = BASE_DIR / "str_mega_scraper.py"
MASTER_CSV = BASE_DIR / "str_master_contacts.csv"
DAILY_DIR  = BASE_DIR / "daily"
LOG_FILE   = BASE_DIR / "pipeline.log"
ENV_FILE   = Path("/root/.openclaw/.env")

# ─── Instantly campaign ─────────────────────────────────────────────────────────
INSTANTLY_CAMPAIGN_ID = "72d96a63-ab0c-4a93-a181-5d4a96497446"  # ICP 1 — Side-Hustle Host

# ─── Discord channel ────────────────────────────────────────────────────────────
DISCORD_CHANNEL_ID = "1472376608223658017"  # #general in STRSolutionsAI

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("pipeline")

# ─── Markets (rotating batches of 30) ──────────────────────────────────────────
ALL_MARKETS = [
    # Arizona
    "Scottsdale, AZ", "Sedona, AZ", "Flagstaff, AZ", "Phoenix, AZ", "Tucson, AZ",
    "Lake Havasu City, AZ", "Show Low, AZ", "Pinetop, AZ", "Prescott, AZ", "Page, AZ",
    "Payson, AZ", "Fountain Hills, AZ", "Cave Creek, AZ", "Gold Canyon, AZ", "Williams, AZ",
    # Florida
    "Miami, FL", "Orlando, FL", "Tampa, FL", "Destin, FL", "Panama City Beach, FL",
    "Fort Lauderdale, FL", "Key West, FL", "Naples, FL", "Sarasota, FL", "Clearwater, FL",
    "St. Pete Beach, FL", "Fort Myers, FL", "Cape Coral, FL", "Pensacola, FL", "Daytona Beach, FL",
    "St. Augustine, FL", "Jacksonville, FL", "Gainesville, FL", "Tallahassee, FL", "Bradenton, FL",
    "Anna Maria, FL", "Amelia Island, FL",
    # Tennessee
    "Gatlinburg, TN", "Pigeon Forge, TN", "Nashville, TN", "Sevierville, TN",
    "Chattanooga, TN", "Memphis, TN",
    # Colorado
    "Breckenridge, CO", "Vail, CO", "Aspen, CO", "Steamboat Springs, CO",
    "Denver, CO", "Telluride, CO", "Colorado Springs, CO", "Estes Park, CO",
    "Durango, CO", "Glenwood Springs, CO",
    # Texas
    "Austin, TX", "San Antonio, TX", "South Padre Island, TX", "Galveston, TX",
    "Fredericksburg, TX", "Dallas, TX", "Houston, TX", "Port Aransas, TX",
    "Wimberley, TX", "Glen Rose, TX",
    # California
    "Los Angeles, CA", "San Diego, CA", "San Francisco, CA", "Lake Tahoe, CA",
    "Palm Springs, CA", "Napa, CA", "Big Sur, CA", "Santa Barbara, CA",
    "Malibu, CA", "Carmel, CA", "Mammoth Lakes, CA", "Joshua Tree, CA",
    "Half Moon Bay, CA", "Monterey, CA", "Temecula, CA",
    # Southeast / Carolinas
    "Myrtle Beach, SC", "Hilton Head Island, SC", "Charleston, SC",
    "Outer Banks, NC", "Asheville, NC", "Wilmington, NC",
    "Savannah, GA", "Atlanta, GA", "Gulf Shores, AL", "Orange Beach, AL",
    # Northeast
    "Cape Cod, MA", "Martha's Vineyard, MA", "Nantucket, MA",
    "Bar Harbor, ME", "Portland, ME", "Burlington, VT",
    "Newport, RI", "Hamptons, NY", "Lake Placid, NY", "Catskills, NY",
    "Rehoboth Beach, DE", "Annapolis, MD",
    # Mountain / West
    "Jackson Hole, WY", "Yellowstone, WY", "Glacier National Park, MT",
    "Whitefish, MT", "Sun Valley, ID", "Coeur d'Alene, ID",
    "Bend, OR", "Portland, OR", "Seattle, WA", "Leavenworth, WA",
    "Moab, UT", "Park City, UT", "St. George, UT", "Zion, UT", "Bryce Canyon, UT",
    # Hawaii
    "Maui, HI", "Kauai, HI", "Big Island, HI", "Oahu, HI", "Lanai, HI",
    # Midwest
    "Traverse City, MI", "Mackinac Island, MI", "Lake Geneva, WI",
    "Branson, MO", "Door County, WI", "Put-in-Bay, OH",
    # Canada
    "Muskoka, ON", "Collingwood, ON", "Prince Edward County, ON",
    "Whistler, BC", "Kelowna, BC", "Tofino, BC",
    "Banff, AB", "Canmore, AB", "Jasper, AB",
    "Mont-Tremblant, QC", "Quebec City, QC",
    "Lunenburg, NS", "Charlottetown, PE",
    "Niagara-on-the-Lake, ON", "Ottawa, ON", "Victoria, BC",
    "Calgary, AB", "Vancouver, BC",
]

# ─── Load .env ──────────────────────────────────────────────────────────────────
def load_env():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k not in os.environ:
            os.environ[k] = v

# ─── HTTP helpers ───────────────────────────────────────────────────────────────
def http_post(url, data, headers=None, timeout=15):
    body = json.dumps(data).encode()
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; STRPipeline/1.0)")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        return {"error": e.code, "msg": e.read().decode()[:300]}
    except Exception as e:
        return {"error": str(e)}

def http_get(url, timeout=10):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""

# ─── Apollo enrichment ──────────────────────────────────────────────────────────
def apollo_find_email(row, api_key):
    """
    Use Apollo people/match to find email by host name + property name.
    Returns (email, first_name, last_name) or ("", "", "").
    """
    if not api_key:
        return "", "", ""

    name_parts = row.get("host_name", "").strip().split(None, 1)
    first = row.get("first_name") or (name_parts[0] if name_parts else "")
    last  = row.get("last_name")  or (name_parts[1] if len(name_parts) > 1 else "")

    if not first:
        return "", "", ""

    # Extract domain from listing URL if available
    listing_url = row.get("listing_url", "")
    website     = row.get("website", "")
    domain = ""
    for u in [website, listing_url]:
        m = re.search(r"https?://(?:www\.)?([^/]+)", u or "")
        if m:
            d = m.group(1)
            # Skip known OTA domains
            if not any(ota in d for ota in ["houfy", "hipcamp", "glamping", "airbnb", "vrbo", "booking"]):
                domain = d
                break

    payload = {
        "first_name":             first,
        "last_name":              last,
        "organization_name":      row.get("company_name") or row.get("property_name", ""),
        "reveal_personal_emails": True,
        "reveal_phone_number":    False,
    }
    if domain:
        payload["domain"] = domain

    resp = http_post(
        "https://api.apollo.io/api/v1/people/match",
        payload,
        {"X-Api-Key": api_key, "Cache-Control": "no-cache"},
    )

    person = resp.get("person") or {}
    email  = person.get("email", "")
    a_first = person.get("first_name", first)
    a_last  = person.get("last_name",  last)

    # Apollo returns None for unmatched emails
    if not email or email == "null":
        return "", a_first, a_last

    return email.lower().strip(), a_first, a_last

# ─── Fallback: scrape listing page for email ────────────────────────────────────
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
SKIP_EMAIL_DOMAINS = {
    "houfy.com", "hipcamp.com", "glampinghub.com", "airbnb.com",
    "vrbo.com", "booking.com", "example.com", "sentry.io",
    "wixpress.com", "squarespace.com", "cloudflare.com",
}

def scrape_email(listing_url):
    if not listing_url:
        return ""
    html = http_get(listing_url)
    for email in EMAIL_RE.findall(html):
        domain = email.split("@")[-1].lower()
        if domain not in SKIP_EMAIL_DOMAINS and not domain.startswith("2x."):
            return email.lower()
    return ""

# ─── Master CSV helpers ─────────────────────────────────────────────────────────
def load_master_keys():
    keys = set()
    if not MASTER_CSV.exists():
        return keys
    with open(MASTER_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            keys.add((
                row.get("property_name", "").strip().lower(),
                row.get("listing_url",   "").strip().lower(),
                row.get("source_platform","").strip().lower(),
            ))
    return keys

def append_to_master(rows):
    if not rows:
        return
    write_header = not MASTER_CSV.exists()
    with open(MASTER_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if write_header:
            w.writeheader()
        w.writerows(rows)

# ─── GHL — cold storage (all contacts) ─────────────────────────────────────────
GHL_BASE = "https://services.leadconnectorhq.com"

def ghl_add_contact(row, api_key, location_id):
    name_parts = row.get("host_name", "").strip().split(None, 1)
    first = row.get("first_name") or (name_parts[0] if name_parts else "")
    last  = row.get("last_name")  or (name_parts[1] if len(name_parts) > 1 else "")

    payload = {
        "locationId": location_id,
        "firstName":  first or row.get("property_name", "")[:40],
        "lastName":   last,
        "email":      row.get("contact_email", ""),
        "phone":      row.get("contact_phone", ""),
        "source":     f"STR Scraper — {row.get('source_platform', '')}",
        "tags":       ["str-scraper", row.get("source_platform", "").lower(), "auto"],
        "customFields": [
            {"key": "property_name",   "field_value": row.get("property_name", "")},
            {"key": "listing_url",     "field_value": row.get("listing_url", "")},
            {"key": "market",          "field_value": row.get("market", "")},
            {"key": "source_platform", "field_value": row.get("source_platform", "")},
            {"key": "nightly_rate",    "field_value": row.get("nightly_rate", "")},
            {"key": "bedrooms",        "field_value": row.get("bedrooms", "")},
        ],
    }
    payload = {k: v for k, v in payload.items() if v not in ("", None, [])}
    headers = {"Authorization": f"Bearer {api_key}", "Version": "2021-07-28"}
    return http_post(f"{GHL_BASE}/contacts/", payload, headers)

# ─── Clay — enrichment push (optional) ─────────────────────────────────────────
def clay_push_row(row, webhook_url):
    """POST row to a Clay HTTP API Source. Set CLAY_WEBHOOK_URL in .env."""
    return http_post(webhook_url, row)

# ─── Instantly ICP 1 — outreach (email required) ───────────────────────────────
def instantly_add_lead(row, email, api_key):
    name_parts = row.get("host_name", "").strip().split(None, 1)
    first = row.get("first_name") or (name_parts[0] if name_parts else "Host")
    last  = row.get("last_name")  or (name_parts[1] if len(name_parts) > 1 else "")

    payload = {
        "campaign_id":  INSTANTLY_CAMPAIGN_ID,
        "email":        email,
        "first_name":   first,
        "last_name":    last,
        "company_name": row.get("company_name") or row.get("property_name", ""),
        "custom_variables": {
            "Property Name": row.get("property_name", ""),
            "Listing URL":   row.get("listing_url", ""),
            "Market":        row.get("market", ""),
            "Platform":      row.get("source_platform", ""),
            "Nightly Rate":  row.get("nightly_rate", ""),
        },
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    return http_post("https://api.instantly.ai/api/v2/leads", payload, headers)

# ─── Discord summary ────────────────────────────────────────────────────────────
def discord_notify(message):
    token = os.environ.get("DISCORD_TOKEN", "")
    if not token:
        return
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    http_post(url, {"content": message}, {"Authorization": f"Bot {token}"})

# ─── Scraper runner ─────────────────────────────────────────────────────────────
def run_scraper(markets, max_pages=3, workers=6):
    today   = date.today().isoformat()
    out_csv = DAILY_DIR / f"scrape_{today}.csv"
    cmd = [
        sys.executable, str(SCRAPER),
        "--sources", "houfy,hipcamp,glampinghub",
        "--markets", ",".join(markets),
        "--max-pages", str(max_pages),
        "--workers",   str(workers),
        "--output",    str(out_csv),
    ]
    log.info(f"Running scraper: {len(markets)} markets → {out_csv.name}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            log.warning(f"Scraper stderr: {result.stderr[-500:]}")
    except subprocess.TimeoutExpired:
        log.error("Scraper timed out (15 min)")
    if out_csv.exists():
        with open(out_csv) as f:
            log.info(f"Scraper produced {sum(1 for _ in f) - 1} rows")
    return out_csv

def get_batch_markets(batch_size=30):
    day_index = (date.today() - date(2026, 1, 1)).days
    start     = (day_index * batch_size) % len(ALL_MARKETS)
    markets   = ALL_MARKETS[start:start + batch_size]
    if len(markets) < batch_size:
        markets += ALL_MARKETS[:batch_size - len(markets)]
    return markets

# ─── Main ───────────────────────────────────────────────────────────────────────
def main():
    load_env()
    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    ghl_key       = os.environ.get("GHL_MASTER_OAUTH", "")
    ghl_loc       = os.environ.get("GHL_MASTER_LOCATION", "")
    instantly_key = os.environ.get("INSTANTLY_API_KEY_V2", "")
    apollo_key    = os.environ.get("APOLLO_API_KEY", "")
    clay_url      = os.environ.get("CLAY_WEBHOOK_URL", "")

    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets",   nargs="*", default=None)
    ap.add_argument("--batch",     type=int,  default=30)
    ap.add_argument("--max-pages", type=int,  default=3)
    ap.add_argument("--workers",   type=int,  default=6)
    args = ap.parse_args()

    markets = args.markets or get_batch_markets(args.batch)
    log.info(f"=== STR Pipeline {date.today()} | {len(markets)} markets ===")
    log.info(f"Markets: {', '.join(markets[:5])}{'...' if len(markets) > 5 else ''}")
    log.info(f"Apollo: {'ON' if apollo_key else 'OFF (add APOLLO_API_KEY to .env)'}")

    # ── 1. Scrape ────────────────────────────────────────────────────────────────
    scrape_csv = run_scraper(markets, args.max_pages, args.workers)
    if not scrape_csv.exists():
        log.error("No scraper output — aborting")
        sys.exit(1)

    # ── 2. Deduplicate ───────────────────────────────────────────────────────────
    existing_keys = load_master_keys()
    log.info(f"Master has {len(existing_keys)} existing records")

    new_rows = []
    with open(scrape_csv, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (
                row.get("property_name",  "").strip().lower(),
                row.get("listing_url",    "").strip().lower(),
                row.get("source_platform","").strip().lower(),
            )
            if key not in existing_keys:
                existing_keys.add(key)
                new_rows.append(row)

    log.info(f"New unique contacts: {len(new_rows)}")
    if not new_rows:
        msg = f"STR Pipeline {date.today()}: 0 new contacts across {len(markets)} markets."
        log.info(msg)
        discord_notify(msg)
        sys.exit(0)

    # ── 3. Per-contact pipeline ──────────────────────────────────────────────────
    apollo_found = apollo_miss = 0
    scrape_found = 0
    ghl_ok = ghl_fail = 0
    clay_ok = clay_fail = 0
    instantly_ok = instantly_fail = instantly_skip = 0

    for i, row in enumerate(new_rows):

        # Step A — Apollo email lookup (primary enrichment)
        email = row.get("contact_email", "").strip()
        if not email and apollo_key:
            email, a_first, a_last = apollo_find_email(row, apollo_key)
            if email:
                row["contact_email"] = email
                if a_first: row["first_name"] = a_first
                if a_last:  row["last_name"]  = a_last
                apollo_found += 1
            else:
                apollo_miss += 1

        # Step B — Fallback: scrape listing page for email
        if not email:
            email = scrape_email(row.get("listing_url", ""))
            if email:
                row["contact_email"] = email
                scrape_found += 1

        # Step C — GHL cold storage (all contacts)
        if ghl_key and ghl_loc:
            r = ghl_add_contact(row, ghl_key, ghl_loc)
            if r.get("error"):
                ghl_fail += 1
                if ghl_fail <= 3:
                    log.warning(f"GHL error: {r}")
            else:
                ghl_ok += 1

        # Step D — Clay enrichment push (optional)
        if clay_url:
            r = clay_push_row(row, clay_url)
            if r.get("error"):
                clay_fail += 1
            else:
                clay_ok += 1

        # Step E — Instantly ICP 1 (email required)
        if email and instantly_key:
            r = instantly_add_lead(row, email, instantly_key)
            if r.get("error"):
                instantly_fail += 1
                if instantly_fail <= 3:
                    log.warning(f"Instantly error: {r}")
            else:
                instantly_ok += 1
        elif not email:
            instantly_skip += 1

        if (i + 1) % 10 == 0:
            time.sleep(0.5)
            log.info(f"  {i+1}/{len(new_rows)} — apollo:{apollo_found} ghl:{ghl_ok} instantly:{instantly_ok}")

    # ── 4. Update master CSV ─────────────────────────────────────────────────────
    append_to_master(new_rows)
    log.info(f"Master CSV updated → {MASTER_CSV.name}")

    # ── 5. Summary ───────────────────────────────────────────────────────────────
    apollo_status = f"found {apollo_found}, no match {apollo_miss}" if apollo_key else "OFF — add APOLLO_API_KEY to .env"
    clay_status   = f"{clay_ok} pushed, {clay_fail} failed" if clay_url else "not configured (set CLAY_WEBHOOK_URL)"

    summary = (
        f"**STR Pipeline — {date.today()}**\n"
        f"Markets: {len(markets)} | New contacts: {len(new_rows)}\n"
        f"→ Apollo: {apollo_status}\n"
        f"→ Scrape fallback emails: {scrape_found}\n"
        f"→ GHL (cold storage): {ghl_ok} added, {ghl_fail} failed\n"
        f"→ Clay (enrichment): {clay_status}\n"
        f"→ Instantly ICP 1: {instantly_ok} added, {instantly_skip} no email, {instantly_fail} failed\n"
        f"Master total: {len(existing_keys)} records"
    )
    log.info("\n" + summary)
    discord_notify(summary)

if __name__ == "__main__":
    main()
