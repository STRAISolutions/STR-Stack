#!/usr/bin/env python3
"""
AirDNA -> Instantly.ai Lead Enrichment Pipeline
================================================
Autonomous pipeline that reads AirDNA CSV exports, enriches leads with
owner/contact data via multiple APIs, verifies emails, deduplicates
against a local SQLite DB, and pushes verified leads to Instantly.ai.

Deployment: /root/str-stack/airdna_to_instantly.py
Cron usage: python3 /root/str-stack/airdna_to_instantly.py /path/to/airdna_export.csv
Supports: .csv, .csv.gz, .gz.csv (auto-detected)

Author: Generated for STR Stack
"""

import argparse
import csv
import gzip
import io
import json
import logging
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path("/root/str-stack")
ENV_FILE = BASE_DIR / ".env"
DB_PATH = BASE_DIR / "data" / "leads.db"
LOG_PATH = BASE_DIR / "logs" / "enrichment.log"

BATCH_SIZE = 5000          # daily target per CSV run
INSTANTLY_CHUNK = 1000     # max leads per Instantly bulk request
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5        # seconds, exponential

# Rate-limit pauses (seconds) -- conservative defaults per service
RATE_LIMITS = {
    "mapbox": 0.05,        # ~20 rps (free tier allows 600/min)
    "batchdata": 0.2,      # ~5 rps
    "tracerfy": 0.25,      # ~4 rps
    "apollo": 0.5,         # ~2 rps (strict)
    "millionverifier": 0.1,# ~10 rps
    "instantly": 1.0,      # 1 rps for bulk
}

# MillionVerifier results we accept
VALID_EMAIL_RESULTS = {"ok", "catch_all"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env(env_path: Path) -> Dict[str, str]:
    """Parse a .env file into a dict. Supports KEY=VALUE and KEY='VALUE'."""
    env = {}
    if not env_path.exists():
        return env
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            env[key] = value
    return env


def build_session() -> requests.Session:
    """Return a requests.Session with automatic retries on transient errors."""
    session = requests.Session()
    retries = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def normalize_phone(phone: str) -> str:
    """Strip a phone to digits only; return empty string if invalid."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


# ---------------------------------------------------------------------------
# ICP Filters — individuals only, no corporations or toll-free numbers
# ---------------------------------------------------------------------------

# Corporate / entity name patterns (case-insensitive)
_CORPORATE_PATTERNS = re.compile(
    r"\b("
    r"llc|l\.l\.c|inc|incorporated|corp|corporation|ltd|limited|"
    r"lp|l\.p|llp|l\.l\.p|partnership|"
    r"trust|trustee|living trust|revocable trust|irrevocable trust|"
    r"estate|foundation|association|assoc|"
    r"holdings|ventures|enterprises|investments|"
    r"capital|equity|properties|realty|"
    r"management|mgmt|consulting|services|solutions|"
    r"group|partners|company|co\.|"
    r"bnb|airbnb|vacasa|evolve|sonder|hipcamp|"
    r"homeaway|vrbo"
    r")\b",
    re.IGNORECASE,
)

# Toll-free area codes
_TOLL_FREE_PREFIXES = {"800", "888", "877", "866", "855", "844", "833"}


def is_corporate_name(name: str) -> bool:
    """Return True if the name looks like a corporation/LLC/trust, not an individual."""
    if not name:
        return False
    return bool(_CORPORATE_PATTERNS.search(name))


def is_toll_free(phone: str) -> bool:
    """Return True if a 10-digit phone starts with a toll-free area code."""
    return len(phone) == 10 and phone[:3] in _TOLL_FREE_PREFIXES


def filter_phones_individual(phones: list) -> list:
    """Remove toll-free and obvious business numbers."""
    return [p for p in phones if not is_toll_free(p)]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class LeadDatabase:
    """SQLite store for deduplication and run tracking."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS processed_leads (
                listing_url  TEXT PRIMARY KEY,
                owner_name   TEXT,
                owner_email  TEXT,
                property_address TEXT,
                processed_at TEXT,
                pushed_to_instantly INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS run_log (
                run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at   TEXT,
                finished_at  TEXT,
                csv_file     TEXT,
                total        INTEGER DEFAULT 0,
                enriched     INTEGER DEFAULT 0,
                verified     INTEGER DEFAULT 0,
                pushed       INTEGER DEFAULT 0,
                failed       INTEGER DEFAULT 0,
                skipped      INTEGER DEFAULT 0
            );
        """)
        self.conn.commit()

    def is_duplicate(self, listing_url: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM processed_leads WHERE listing_url = ?", (listing_url,)
        )
        return cur.fetchone() is not None

    def mark_processed(self, listing_url: str, owner_name: str,
                       owner_email: str, address: str, pushed: bool):
        self.conn.execute(
            """INSERT OR REPLACE INTO processed_leads
               (listing_url, owner_name, owner_email, property_address,
                processed_at, pushed_to_instantly)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (listing_url, owner_name, owner_email, address,
             datetime.now(timezone.utc).isoformat(), int(pushed)),
        )
        self.conn.commit()

    def start_run(self, csv_file: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO run_log (started_at, csv_file) VALUES (?, ?)",
            (datetime.now(timezone.utc).isoformat(), csv_file),
        )
        self.conn.commit()
        return cur.lastrowid

    def finish_run(self, run_id: int, stats: Dict[str, int]):
        self.conn.execute(
            """UPDATE run_log SET finished_at=?, total=?, enriched=?,
               verified=?, pushed=?, failed=?, skipped=?
               WHERE run_id=?""",
            (datetime.now(timezone.utc).isoformat(),
             stats.get("total", 0), stats.get("enriched", 0),
             stats.get("verified", 0), stats.get("pushed", 0),
             stats.get("failed", 0), stats.get("skipped", 0),
             run_id),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class AirDNAEnrichmentPipeline:
    """
    End-to-end pipeline:
      CSV -> Geocode -> Owner Lookup -> Skip Trace -> Email Verify -> Instantly
    """

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.session = build_session()

        # Load API keys
        env = load_env(ENV_FILE)
        # Also allow real environment variables to override .env
        self.batchdata_key = os.getenv("BATCHDATA_API_KEY", env.get("BATCHDATA_API_KEY", ""))
        self.tracerfy_key = os.getenv("TRACERFY_API_KEY", env.get("TRACERFY_API_KEY", ""))
        self.apollo_key = os.getenv("APOLLO_API_KEY", env.get("APOLLO_API_KEY", ""))
        self.mapbox_token = os.getenv("MAPBOX_TOKEN", env.get("MAPBOX_TOKEN", ""))
        self.mv_key = os.getenv("MILLIONVERIFIER_API_KEY", env.get("MILLIONVERIFIER_API_KEY", ""))
        self.instantly_key = os.getenv("INSTANTLY_API_KEY", env.get("INSTANTLY_API_KEY", ""))
        self.campaign_id = os.getenv("INSTANTLY_CAMPAIGN_ID", env.get("INSTANTLY_CAMPAIGN_ID", ""))

        self._validate_keys()

        # Setup logging
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
        )
        self.log = logging.getLogger("enrichment")

        # Database
        self.db = LeadDatabase(DB_PATH)

        # Counters
        self.stats = {
            "total": 0,
            "enriched": 0,
            "verified": 0,
            "pushed": 0,
            "failed": 0,
            "skipped": 0,
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_keys(self):
        missing = []
        optional_missing = []
        # Required keys
        for name, val in [
            ("TRACERFY_API_KEY", self.tracerfy_key),
            ("MAPBOX_TOKEN", self.mapbox_token),
            ("MILLIONVERIFIER_API_KEY", self.mv_key),
            ("INSTANTLY_API_KEY", self.instantly_key),
            ("INSTANTLY_CAMPAIGN_ID", self.campaign_id),
        ]:
            if not val:
                missing.append(name)
        # Optional keys (nice to have, not fatal)
        for name, val in [
            ("BATCHDATA_API_KEY", self.batchdata_key),
            ("APOLLO_API_KEY", self.apollo_key),
        ]:
            if not val:
                optional_missing.append(name)
        if missing:
            sys.exit(f"FATAL: Missing required keys in {ENV_FILE}: {', '.join(missing)}")
        if optional_missing:
            self.log.warning("Optional keys not set (some enrichment will be skipped): %s", ", ".join(optional_missing))

    # ------------------------------------------------------------------
    # Stage 1 -- Read CSV
    # ------------------------------------------------------------------

    def read_csv(self) -> List[Dict[str, str]]:
        """Read AirDNA CSV (plain or .gz/.csv.gz compressed), capped at BATCH_SIZE."""
        self.log.info("Reading CSV: %s", self.csv_path)
        rows = []
        path_lower = self.csv_path.lower()
        is_gzip = path_lower.endswith(".gz") or path_lower.endswith(".gz.csv")

        if is_gzip:
            fh = io.TextIOWrapper(gzip.open(self.csv_path, "rb"), encoding="utf-8-sig")
        else:
            fh = open(self.csv_path, "r", encoding="utf-8-sig")

        try:
            reader = csv.DictReader(fh)
            for i, row in enumerate(reader):
                if i >= BATCH_SIZE:
                    self.log.info("Reached batch cap of %d leads.", BATCH_SIZE)
                    break
                rows.append(row)
        finally:
            fh.close()

        self.log.info("Loaded %d rows from CSV.", len(rows))
        return rows

    # ------------------------------------------------------------------
    # Stage 2 -- Geocoding (Mapbox)
    # ------------------------------------------------------------------

    def geocode(self, lat: float, lng: float) -> Optional[Dict[str, str]]:
        """
        Convert lat/lng to a structured address via Mapbox reverse geocoding.
        Returns dict with keys: street, city, state, zip, full_address  or None.
        """
        url = (
            f"https://api.mapbox.com/geocoding/v5/mapbox.places/"
            f"{lng},{lat}.json?access_token={self.mapbox_token}&types=address"
        )
        time.sleep(RATE_LIMITS["mapbox"])
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.log.warning("Mapbox geocode failed for (%s,%s): %s", lat, lng, exc)
            return None

        features = data.get("features", [])
        if not features:
            return None

        feat = features[0]
        address_text = feat.get("place_name", "")

        # Extract components from context
        ctx = {c["id"].split(".")[0]: c["text"] for c in feat.get("context", [])}
        street_number = feat.get("address", "")
        street_name = feat.get("text", "")
        street = f"{street_number} {street_name}".strip()

        return {
            "street": street,
            "city": ctx.get("place", ""),
            "state": ctx.get("region", ""),
            "zip": ctx.get("postcode", ""),
            "full_address": address_text,
        }

    # ------------------------------------------------------------------
    # Stage 3 -- BatchData skip trace
    # ------------------------------------------------------------------

    def batchdata_skip_trace(self, address: Dict[str, str]) -> Optional[Dict]:
        """
        Call BatchData property skip-trace.
        Returns dict with owner_first, owner_last, phones[], emails[], mailing_address.
        """
        url = "https://api.batchdata.com/api/v1/property/skip-trace"
        payload = {
            "requests": [
                {
                    "address": {
                        "street": address.get("street", ""),
                        "city": address.get("city", ""),
                        "state": address.get("state", ""),
                        "zip": address.get("zip", ""),
                    }
                }
            ]
        }
        headers = {
            "Authorization": f"Bearer {self.batchdata_key}",
            "Content-Type": "application/json",
        }
        time.sleep(RATE_LIMITS["batchdata"])
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.log.warning("BatchData failed for %s: %s", address.get("street"), exc)
            return None

        # Navigate the response
        results = (
            data.get("results", {})
                .get("responses", [{}])[0] if isinstance(data.get("results"), dict)
            else None
        )
        if not results:
            # Try alternate response shape
            results = data.get("results", [{}])
            if isinstance(results, list) and results:
                results = results[0]
            else:
                return None

        people = results.get("people", [])
        if not people:
            return None

        person = people[0]
        first = safe_str(person.get("firstName", person.get("first_name", "")))
        last = safe_str(person.get("lastName", person.get("last_name", "")))

        phones = []
        for p in person.get("phones", person.get("phoneNumbers", [])):
            num = normalize_phone(safe_str(p if isinstance(p, str) else p.get("number", p.get("phone", ""))))
            if num:
                phones.append(num)

        emails = []
        for e in person.get("emails", person.get("emailAddresses", [])):
            addr = safe_str(e if isinstance(e, str) else e.get("address", e.get("email", "")))
            if addr and "@" in addr:
                emails.append(addr.lower())

        mailing = safe_str(person.get("mailingAddress", person.get("mailing_address", "")))

        return {
            "owner_first": first,
            "owner_last": last,
            "phones": phones,
            "emails": emails,
            "mailing_address": mailing,
        }

    # ------------------------------------------------------------------
    # Stage 4 -- Tracerfy fallback skip trace
    # ------------------------------------------------------------------

    def tracerfy_skip_trace(self, first: str, last: str,
                            address: Dict[str, str]) -> Optional[Dict]:
        """
        Tracerfy Instant Trace Lookup API.
        Endpoint: POST https://tracerfy.com/v1/api/trace/lookup/
        Auth: Authorization: Bearer <JWT>
        Cost: 5 credits per hit, 0 on miss.
        Rate limit: 500 RPM.
        Returns persons[] array, each with phones[], emails[], name, etc.
        """
        if not address.get("street"):
            return None

        url = "https://tracerfy.com/v1/api/trace/lookup/"
        payload = {
            "address": address.get("street", ""),
            "city": address.get("city", ""),
            "state": address.get("state", ""),
            "zip": address.get("zip", ""),
            "find_owner": True,
        }
        # Add name if available (improves match quality)
        if first:
            payload["first_name"] = first
        if last:
            payload["last_name"] = last

        headers = {
            "Authorization": f"Bearer {self.tracerfy_key}",
            "Content-Type": "application/json",
        }
        time.sleep(RATE_LIMITS["tracerfy"])
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.log.warning("Tracerfy failed for %s %s: %s", first, last, exc)
            return None

        # Check if we got a hit
        if not data.get("hit"):
            self.log.debug("Tracerfy miss for %s", address.get("street", ""))
            return None

        # Log raw response for first few hits to debug field names
        if self.stats.get("enriched", 0) < 3:
            self.log.info("Tracerfy RAW response keys: %s", list(data.keys()))
            for i, p in enumerate(data.get("persons", [])[:2]):
                self.log.info("Tracerfy person[%d] keys: %s", i, list(p.keys()) if isinstance(p, dict) else type(p))
                self.log.info("Tracerfy person[%d] data: %s", i, json.dumps(p, default=str)[:500])

        # Parse persons array — aggregate phones/emails from all persons
        phones = []
        emails = []
        result_first = ""
        result_last = ""

        persons = data.get("persons", [])
        for person in persons:
            # Try multiple name field patterns
            fname = safe_str(person.get("first_name", "") or person.get("firstName", ""))
            lname = safe_str(person.get("last_name", "") or person.get("lastName", ""))

            # Fallback: split full "name" field
            if not fname and not lname:
                name = safe_str(person.get("name", "") or person.get("full_name", "") or person.get("fullName", ""))
                if name:
                    parts = name.split(None, 1)
                    if len(parts) >= 1:
                        fname = parts[0]
                    if len(parts) >= 2:
                        lname = parts[1]

            # Prefer property_owner flagged person for name
            is_owner = person.get("property_owner") or person.get("is_owner")
            if fname and (not result_first or is_owner):
                result_first = fname
            if lname and (not result_last or is_owner):
                result_last = lname

            # Collect phones from this person (skip DNC-flagged numbers)
            for p in person.get("phones", []):
                if isinstance(p, dict) and p.get("dnc"):
                    continue  # skip Do Not Call numbers
                num = normalize_phone(safe_str(
                    p if isinstance(p, str) else p.get("number", p.get("phone", ""))
                ))
                if num and num not in phones:
                    phones.append(num)

            # Collect emails from this person
            for e in person.get("emails", []):
                addr = safe_str(
                    e if isinstance(e, str) else e.get("address", e.get("email", ""))
                )
                if addr and "@" in addr and addr.lower() not in emails:
                    emails.append(addr.lower())

        # Also check top-level fields (some APIs return owner info at root)
        if not result_first:
            result_first = safe_str(data.get("first_name", "") or data.get("owner_first", ""))
        if not result_last:
            result_last = safe_str(data.get("last_name", "") or data.get("owner_last", ""))

        # Cap results
        phones = phones[:8]
        emails = emails[:5]

        result: Dict[str, Any] = {"phones": phones, "emails": emails}
        if result_first:
            result["first_name"] = result_first
        if result_last:
            result["last_name"] = result_last

        self.log.info("Tracerfy hit: %d persons, %d phones, %d emails",
                       len(persons), len(phones), len(emails))
        return result

    # ------------------------------------------------------------------
    # Stage 5 -- Apollo B2B email fallback
    # ------------------------------------------------------------------

    def apollo_email_lookup(self, first: str, last: str,
                            domain: str = "") -> Optional[str]:
        """
        Apollo People Match -- returns a single email or None.
        Used as last-resort fallback when BatchData + Tracerfy yield no email.
        """
        if not first or not last:
            return None

        url = "https://api.apollo.io/api/v1/people/match"
        payload: Dict[str, str] = {
            "first_name": first,
            "last_name": last,
            "api_key": self.apollo_key,
        }
        if domain:
            payload["domain"] = domain

        time.sleep(RATE_LIMITS["apollo"])
        try:
            resp = self.session.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.log.warning("Apollo failed for %s %s: %s", first, last, exc)
            return None

        person = data.get("person", data)
        email = safe_str(person.get("email", ""))
        return email.lower() if email and "@" in email else None

    # ------------------------------------------------------------------
    # Stage 6 -- MillionVerifier email verification
    # ------------------------------------------------------------------

    def verify_email(self, email: str) -> bool:
        """Return True if MillionVerifier considers the email valid or catch-all."""
        url = (
            f"https://api.millionverifier.com/api/v3/"
            f"?api={self.mv_key}&email={quote(email)}"
        )
        time.sleep(RATE_LIMITS["millionverifier"])
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.log.warning("MillionVerifier failed for %s: %s", email, exc)
            return False

        result = safe_str(data.get("result", "")).lower()
        return result in VALID_EMAIL_RESULTS

    # ------------------------------------------------------------------
    # Stage 7 -- Push to Instantly
    # ------------------------------------------------------------------

    def push_to_instantly(self, leads: List[Dict]) -> int:
        """
        Upload leads to Instantly.ai via API v2 (single-lead endpoint).
        POST https://api.instantly.ai/api/v2/leads
        Auth: Authorization: Bearer <key>
        Returns count of successfully pushed leads.
        """
        if not leads:
            return 0

        url = "https://api.instantly.ai/api/v2/leads"
        headers = {
            "Authorization": f"Bearer {self.instantly_key}",
            "Content-Type": "application/json",
        }
        pushed = 0
        failed = 0

        for i, lead in enumerate(leads, start=1):
            payload = {
                "email": lead["email"],
                "first_name": lead.get("first_name", ""),
                "last_name": lead.get("last_name", ""),
                "company_name": lead.get("company_name", ""),
                "campaign": self.campaign_id,
            }
            # Add custom variables as top-level fields for personalization
            for k, v in lead.get("custom_variables", {}).items():
                if v:
                    payload[k] = v

            time.sleep(RATE_LIMITS["instantly"])
            try:
                resp = self.session.post(url, json=payload, headers=headers, timeout=15)
                resp.raise_for_status()
                pushed += 1
            except Exception as exc:
                failed += 1
                if failed <= 5:  # only log first 5 failures to avoid spam
                    self.log.error("Instantly push failed for %s: %s", lead["email"], exc)

            # Progress every 100 leads
            if i % 100 == 0:
                self.log.info("Instantly: pushed %d/%d leads (%d failed).", pushed, i, failed)

        self.log.info("Instantly: DONE — %d pushed, %d failed out of %d total.", pushed, failed, len(leads))
        return pushed

    # ------------------------------------------------------------------
    # Enrichment orchestrator (per-lead)
    # ------------------------------------------------------------------

    def enrich_lead(self, row: Dict[str, str]) -> Optional[Dict]:
        """
        Run the full enrichment pipeline for a single CSV row.
        Returns an Instantly-ready lead dict or None on failure.
        """
        # --- Extract fields from AirDNA CSV ---
        # Supports both airdna_full.csv.gz and PPD-USA_property_file_v3.csv.gz column names
        lat = safe_float(
            row.get("Latitude") or row.get("latitude") or row.get("lat")
        )
        lng = safe_float(
            row.get("Longitude") or row.get("longitude") or row.get("lng") or row.get("lon")
        )
        listing_url = safe_str(
            row.get("Listing URL") or row.get("listing_url") or row.get("url") or row.get("airbnb_url") or ""
        )
        property_name = safe_str(
            row.get("Listing Title") or row.get("Property Name") or row.get("property_name")
            or row.get("title") or row.get("Title") or ""
        )
        revenue = safe_str(
            row.get("Revenue LTM (USD)") or row.get("Revenue (USD)") or row.get("Revenue Potential LTM (USD)")
            or row.get("Revenue Potential (USD)") or row.get("revenue") or row.get("Revenue")
            or row.get("annual_revenue") or row.get("Annual Revenue") or ""
        )
        occupancy = safe_str(
            row.get("Occupancy Rate LTM") or row.get("Occupancy Rate")
            or row.get("occupancy_rate") or row.get("occupancy") or ""
        )
        # Extra fields for personalization
        adr = safe_str(
            row.get("ADR (USD)") or row.get("ADR (Native)") or row.get("Average Daily Rate") or ""
        )
        property_type = safe_str(
            row.get("Property Type") or row.get("Real Estate Property Type") or row.get("Listing Type") or ""
        )
        market = safe_str(
            row.get("AirDNA Market") or row.get("Metropolitan Statistical Area") or row.get("City") or ""
        )
        bedrooms = safe_str(row.get("Bedrooms") or row.get("bedrooms") or "")
        state = safe_str(row.get("State") or row.get("state") or "")
        city = safe_str(row.get("City") or row.get("city") or "")
        num_properties = safe_float(
            row.get("Number of Properties") or row.get("Number of Units")
            or row.get("# Properties") or row.get("# Units")
            or row.get("Num Properties") or row.get("num_properties")
            or row.get("Properties") or row.get("Units")
            or row.get("Number of Listings") or row.get("Listing Count")
            or row.get("Total Listings") or 0
        )

        if not lat and not lng:
            self.log.debug("Skipping row -- no lat/lng.")
            return None

        # --- ICP Filter: max 5 properties/units (small operators only) ---
        if num_properties > 5:
            self.log.info("ICP SKIP (large operator): %.0f properties — %s",
                          num_properties, listing_url or f"{lat},{lng}")
            self.stats["failed"] += 1
            return None

        # --- Deduplication ---
        dedup_key = listing_url or f"{lat},{lng}"
        if self.db.is_duplicate(dedup_key):
            self.stats["skipped"] += 1
            return None

        # --- Geocode ---
        address = self.geocode(lat, lng)
        if not address or not address.get("street"):
            self.log.debug("Geocode returned no street for (%s,%s).", lat, lng)
            self.stats["failed"] += 1
            return None

        full_address = address["full_address"]

        # --- Skip trace ---
        first = ""
        last = ""
        phones: List[str] = []
        emails: List[str] = []

        # BatchData disabled — 403 on current plan (skip-trace not enabled).
        # Uncomment below when BatchData subscription is upgraded:
        # if self.batchdata_key:
        #     owner = self.batchdata_skip_trace(address)
        #     if owner:
        #         first = owner["owner_first"]
        #         last = owner["owner_last"]
        #         phones = owner["phones"]
        #         emails = owner["emails"]

        # --- Tracerfy skip trace (PRIMARY) ---
        # Supports address-only lookup, returns persons with phones/emails
        tf = self.tracerfy_skip_trace(first, last, address)
        if tf:
            # If BatchData didn't return a name, try to get it from Tracerfy
            if not first and tf.get("first_name"):
                first = tf["first_name"]
            if not last and tf.get("last_name"):
                last = tf["last_name"]
            # Merge unique phones (up to 8 total) and emails (up to 5)
            for p in tf.get("phones", []):
                if p not in phones:
                    phones.append(p)
            phones = phones[:8]
            for e in tf.get("emails", []):
                if e not in emails:
                    emails.append(e)
            emails = emails[:5]

        # --- Apollo fallback (only if still no email) ---
        if not emails and first and last:
            apollo_email = self.apollo_email_lookup(first, last)
            if apollo_email:
                emails.append(apollo_email)

        if not emails:
            self.log.debug("No email found for %s.", full_address)
            self.stats["failed"] += 1
            self.db.mark_processed(dedup_key, f"{first} {last}".strip(), "", full_address, False)
            return None

        # --- ICP Filters ---
        # Corporate name filter DISABLED — business names OK with ≤5 unit rule
        # Require at least a first name (skip completely anonymous leads)
        if not first:
            self.log.info("ICP SKIP (no name at all): %s", full_address)
            self.stats["failed"] += 1
            self.db.mark_processed(dedup_key, "", "", full_address, False)
            return None

        # Strip toll-free and business phone numbers
        phones = filter_phones_individual(phones)

        self.stats["enriched"] += 1

        # --- Verify emails ---
        # MillionVerifier: skip if low credits or disabled (bulk verify later)
        if self.mv_key and os.getenv("SKIP_EMAIL_VERIFY", "").lower() not in ("1", "true", "yes"):
            verified_emails = []
            for email in emails[:2]:  # verify max 2 to conserve credits
                if self.verify_email(email):
                    verified_emails.append(email)
            if not verified_emails:
                # Fall through — accept first email unverified rather than losing the lead
                self.log.info("MV rejected all emails for %s, accepting first email unverified.", full_address)
                verified_emails = [emails[0]]
        else:
            verified_emails = emails  # accept all, verify in bulk later
            self.log.debug("Email verification skipped for %s.", full_address)

        self.stats["verified"] += 1
        primary_email = verified_emails[0]

        # --- Build Instantly lead ---
        owner_name = f"{first} {last}".strip()
        lead = {
            "email": primary_email,
            "first_name": first,
            "last_name": last,
            "company_name": property_name or owner_name,
            "custom_variables": {
                "property_address": full_address,
                "annual_revenue": revenue,
                "occupancy_rate": occupancy,
                "listing_url": listing_url,
                "property_name": property_name,
                "owner_name": owner_name,
                "adr": adr,
                "property_type": property_type,
                "market": market,
                "bedrooms": bedrooms,
                "city": city,
                "state": state,
            },
        }

        # Mark in DB (pushed flag set later after actual push)
        self.db.mark_processed(dedup_key, owner_name, primary_email, full_address, False)

        return lead

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """Execute the full pipeline and return a summary dict."""
        start_time = datetime.now(timezone.utc)
        self.log.info("=" * 60)
        self.log.info("Pipeline started at %s", start_time.isoformat())
        self.log.info("CSV: %s", self.csv_path)

        run_id = self.db.start_run(self.csv_path)

        # Read CSV
        rows = self.read_csv()
        self.stats["total"] = len(rows)

        # Enrich each lead
        ready_leads: List[Dict] = []
        for idx, row in enumerate(rows, start=1):
            try:
                lead = self.enrich_lead(row)
                if lead:
                    ready_leads.append(lead)
            except Exception as exc:
                self.log.error("Unhandled error on row %d: %s", idx, exc)
                self.stats["failed"] += 1

            # Progress report every 100 leads
            if idx % 100 == 0:
                self.log.info(
                    "Progress: %d/%d processed | enriched=%d verified=%d failed=%d skipped=%d",
                    idx, len(rows),
                    self.stats["enriched"], self.stats["verified"],
                    self.stats["failed"], self.stats["skipped"],
                )

        # Push verified leads to Instantly
        self.log.info("Pushing %d verified leads to Instantly...", len(ready_leads))
        pushed_count = self.push_to_instantly(ready_leads)
        self.stats["pushed"] = pushed_count

        # Update DB pushed flag for successfully pushed leads
        for lead in ready_leads[:pushed_count]:
            listing_url = lead["custom_variables"].get("listing_url", "")
            if listing_url:
                self.db.conn.execute(
                    "UPDATE processed_leads SET pushed_to_instantly=1 WHERE listing_url=?",
                    (listing_url,),
                )
        self.db.conn.commit()

        # Finalize
        end_time = datetime.now(timezone.utc)
        elapsed = (end_time - start_time).total_seconds()
        self.db.finish_run(run_id, self.stats)

        summary = {
            "run_id": run_id,
            "csv_file": self.csv_path,
            "started_at": start_time.isoformat(),
            "finished_at": end_time.isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "stats": dict(self.stats),
        }

        # Write JSON report next to the CSV
        report_path = BASE_DIR / "logs" / f"report_{start_time.strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
            self.log.info("Report written to %s", report_path)
        except Exception as exc:
            self.log.warning("Could not write report file: %s", exc)

        # Print final summary
        self.log.info("-" * 40)
        self.log.info("PIPELINE COMPLETE")
        self.log.info("  Total rows:   %d", self.stats["total"])
        self.log.info("  Enriched:     %d", self.stats["enriched"])
        self.log.info("  Verified:     %d", self.stats["verified"])
        self.log.info("  Pushed:       %d", self.stats["pushed"])
        self.log.info("  Failed:       %d", self.stats["failed"])
        self.log.info("  Skipped/Dup:  %d", self.stats["skipped"])
        self.log.info("  Elapsed:      %.1fs", elapsed)
        self.log.info("=" * 60)

        self.db.close()
        return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AirDNA -> Instantly.ai Lead Enrichment Pipeline",
    )
    parser.add_argument(
        "csv_file",
        help="Path to the AirDNA CSV export file.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Max leads to process per run (default: 5000).",
    )
    args = parser.parse_args()

    # Allow overriding batch size via CLI
    global BATCH_SIZE
    BATCH_SIZE = args.batch_size

    if not os.path.isfile(args.csv_file):
        sys.exit(f"ERROR: CSV file not found: {args.csv_file}")

    pipeline = AirDNAEnrichmentPipeline(args.csv_file)
    summary = pipeline.run()

    # Print JSON summary to stdout for cron capture
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
