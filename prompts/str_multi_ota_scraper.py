#!/usr/bin/env python3
"""
STR Multi-OTA Contact Scraper
===============================
Searches multiple Online Travel Agents (OTAs) for short-term rental listings
in a given market, extracts property & host/manager info, and outputs a CSV
formatted for Clay.com enrichment and Instantly.ai outbound campaigns.
PROVEN scrapable sources (tested, returns real data):
  - Houfy        (direct booking platform — returns host first/last name, username, profile URL)
  - Glamping Hub (unique accommodations — returns listing names + URLs via JSON-LD)
  - Hipcamp      (outdoor stays — returns campground/property names via JSON-LD)
  - Vacasa       (PM company — returns listing data via JSON-LD)
  - Turnkey      (PM company — returns listing data via JSON-LD)
  - Evolve       (PM company — returns listing data via __NEXT_DATA__)
Features:
  - Parallel requests via ThreadPoolExecutor
  - Rotating user agents
  - Configurable rate limiting per source
  - Optional AirDNA CSV merge
  - Output formatted for Clay.com + Instantly.ai
  - Public STR registry lookup helper
Usage:
    python str_multi_ota_scraper.py --market "Scottsdale, AZ" --output contacts.csv
    python str_multi_ota_scraper.py --market "Scottsdale, AZ" --sources houfy,glampinghub,hipcamp
    python str_multi_ota_scraper.py --market "Scottsdale, AZ" --airdna-csv airdna_export.csv
    python str_multi_ota_scraper.py --market "Scottsdale, AZ" --max-pages 5 --workers 3
Environment variables:
    HUNTER_API_KEY     Hunter.io API key for email enrichment
"""
import argparse
import csv
import json
import logging
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("str_ota_scraper")
# ---------------------------------------------------------------------------
# User Agent Rotation
# ---------------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
]
def get_random_ua():
    return random.choice(USER_AGENTS)
def make_request(url, headers=None, timeout=20):
    """Make an HTTP GET request with a random user agent. Returns HTML or None."""
    default_headers = {
        "User-Agent": get_random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }
    if headers:
        default_headers.update(headers)
    try:
        req = urllib.request.Request(url, headers=default_headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        log.warning("HTTP %d: %s", e.code, url)
        return None
    except Exception as e:
        log.warning("Request failed: %s - %s", url, e)
        return None
# ---------------------------------------------------------------------------
# Output schema (Clay.com + Instantly.ai compatible)
# ---------------------------------------------------------------------------
OUTPUT_COLUMNS = [
    # -- Property Info --
    "property_name",
    "listing_url",
    "source_platform",
    "address",
    "city",
    "state",
    "zip_code",
    "country",
    "property_type",
    "bedrooms",
    "bathrooms",
    "max_guests",
    "nightly_rate",
    "rating",
    "review_count",
    # -- Host / Manager Info --
    "host_name",
    "management_company",
    "host_profile_url",
    "host_username",
    # -- Contact Info (for Clay enrichment) --
    "contact_email",
    "contact_phone",
    "website",
    # -- Enrichment metadata --
    "market",
    "scraped_at",
    # -- Instantly.ai fields --
    "first_name",
    "last_name",
    "company_name",
]
def new_listing():
    """Return a blank listing dict with all output columns."""
    return {col: "" for col in OUTPUT_COLUMNS}
def split_name(full_name):
    """Split a full name into first and last name."""
    parts = full_name.strip().split(None, 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    return first, last
# ---------------------------------------------------------------------------
# US state abbreviation mapping
# ---------------------------------------------------------------------------
STATE_ABBREV_TO_FULL = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas",
    "ca": "california", "co": "colorado", "ct": "connecticut", "de": "delaware",
    "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas",
    "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada",
    "nh": "new-hampshire", "nj": "new-jersey", "nm": "new-mexico", "ny": "new-york",
    "nc": "north-carolina", "nd": "north-dakota", "oh": "ohio", "ok": "oklahoma",
    "or": "oregon", "pa": "pennsylvania", "ri": "rhode-island", "sc": "south-carolina",
    "sd": "south-dakota", "tn": "tennessee", "tx": "texas", "ut": "utah",
    "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "west-virginia",
    "wi": "wisconsin", "wy": "wyoming",
}
def parse_market(market):
    """Parse 'Scottsdale, AZ' into (city, state_abbrev, state_full)."""
    parts = [p.strip() for p in market.split(",")]
    city = parts[0] if parts else ""
    state_abbrev = parts[1].strip().lower() if len(parts) > 1 else ""
    state_full = STATE_ABBREV_TO_FULL.get(state_abbrev, state_abbrev)
    return city, state_abbrev, state_full
# ---------------------------------------------------------------------------
# OTA Scrapers - PROVEN WORKING (tested against real sites)
# ---------------------------------------------------------------------------
class OTAScraper:
    """Base class for OTA scrapers."""
    name = "base"
    base_url = ""
    delay = 2.0
    def search(self, market, max_pages=3):
        raise NotImplementedError
    def _delay(self):
        jitter = random.uniform(0.5, 1.5)
        time.sleep(self.delay * jitter)
# ---- HOUFY (best source - returns host first/last name) ----
class HoufyScraper(OTAScraper):
    """Houfy - Direct booking platform. Returns host first/last name, username, profile URL."""
    name = "houfy"
    base_url = "https://www.houfy.com"
    delay = 2.5
    def search(self, market, max_pages=3):
        listings = []
        city, state_abbrev, state_full = parse_market(market)
        slug = city.lower().replace(" ", "-") + "-" + state_abbrev
        for page in range(1, max_pages + 1):
            url = self.base_url + "/vacation-rentals/" + slug
            if page > 1:
                url += "?page=" + str(page)
            log.info("[Houfy] Fetching page %d: %s", page, url)
            html = make_request(url)
            if not html:
                break
            page_listings = self._parse_results(html, market)
            if not page_listings:
                log.info("[Houfy] No more results on page %d", page)
                break
            listings.extend(page_listings)
            log.info("[Houfy] Found %d listings on page %d (total: %d)", len(page_listings), page, len(listings))
            self._delay()
        return listings
    def _parse_results(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not nd:
            return results
        try:
            data = json.loads(nd.group(1))
            raw_listings = (
                data.get("props", {})
                .get("pageProps", {})
                .get("data", {})
                .get("listings", [])
            )
            for item in raw_listings:
                if not isinstance(item, dict):
                    continue
                listing = new_listing()
                listing["property_name"] = item.get("TITLE", "")
                listing_id = item.get("ID", "")
                listing["listing_url"] = self.base_url + "/listing/" + str(listing_id) if listing_id else ""
                listing["source_platform"] = "Houfy"
                listing["market"] = market
                listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                # Host info - Houfy's key advantage
                fname = item.get("fname", "")
                lname = item.get("lname", "")
                uname = item.get("uname", "")
                listing["first_name"] = fname
                listing["last_name"] = lname
                listing["host_name"] = (fname + " " + lname).strip()
                listing["host_username"] = uname
                listing["host_profile_url"] = self.base_url + "/user/" + uname if uname else ""
                listing["company_name"] = uname  # Username often = business name on Houfy
                # Property details
                listing["bedrooms"] = str(item.get("bedrooms", ""))
                listing["bathrooms"] = str(item.get("bathrooms", ""))
                listing["max_guests"] = str(item.get("guests", ""))
                listing["nightly_rate"] = str(item.get("baseprice", item.get("basprice", "")))
                listing["rating"] = str(item.get("rating_avg", ""))
                listing["review_count"] = str(item.get("tot_reviews", ""))
                if listing["property_name"]:
                    results.append(listing)
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            log.warning("[Houfy] Parse error: %s", e)
        return results
# ---- GLAMPING HUB (good data via JSON-LD ItemList) ----
class GlampingHubScraper(OTAScraper):
    """Glamping Hub - Unique accommodations. Returns listings via JSON-LD ItemList."""
    name = "glampinghub"
    base_url = "https://glampinghub.com"
    delay = 2.5
    STATE_REGIONS = {
        "az": "southwest", "nm": "southwest", "tx": "southwest", "ok": "southwest",
        "ca": "west", "nv": "west", "or": "west", "wa": "west", "co": "west",
        "ut": "west", "id": "west", "mt": "west", "wy": "west",
        "hi": "west", "ak": "west",
        "fl": "southeast", "ga": "southeast", "sc": "southeast", "nc": "southeast",
        "al": "southeast", "ms": "southeast", "tn": "southeast", "va": "southeast",
        "ny": "northeast", "nj": "northeast", "ma": "northeast", "ct": "northeast",
        "pa": "northeast", "me": "northeast", "nh": "northeast", "vt": "northeast",
        "ri": "northeast", "md": "northeast", "de": "northeast",
        "il": "midwest", "oh": "midwest", "mi": "midwest", "in": "midwest",
        "wi": "midwest", "mn": "midwest", "ia": "midwest", "mo": "midwest",
        "ks": "midwest", "ne": "midwest", "nd": "midwest", "sd": "midwest",
        "ky": "south", "wv": "south", "ar": "south", "la": "south",
    }
    def search(self, market, max_pages=3):
        listings = []
        city, state_abbrev, state_full = parse_market(market)
        region = self.STATE_REGIONS.get(state_abbrev, "")
        state_name = state_full.replace("-", "")
        city_slug = city.lower().replace(" ", "")
        if not region:
            log.warning("[GlampingHub] Unknown region for state: %s", state_abbrev)
            return []
        for page in range(1, max_pages + 1):
            url = self.base_url + "/unitedstatesofamerica/" + region + "/" + state_name + "/" + city_slug + "/"
            if page > 1:
                url += "?page=" + str(page)
            log.info("[GlampingHub] Fetching page %d: %s", page, url)
            html = make_request(url)
            if not html:
                break
            page_listings = self._parse_results(html, market)
            if not page_listings:
                break
            listings.extend(page_listings)
            log.info("[GlampingHub] Found %d listings on page %d", len(page_listings), page)
            self._delay()
        return listings
    def _parse_results(self, html, market):
        results = []
        ld_matches = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
        for ld_raw in ld_matches:
            try:
                ld_data = json.loads(ld_raw)
                if not isinstance(ld_data, dict):
                    continue
                if ld_data.get("@type") == "ItemList":
                    for item in ld_data.get("itemListElement", []):
                        listing = new_listing()
                        listing["property_name"] = item.get("name", "")
                        listing["listing_url"] = item.get("url", "")
                        listing["source_platform"] = "Glamping Hub"
                        listing["market"] = market
                        listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        if listing["property_name"]:
                            results.append(listing)
            except json.JSONDecodeError:
                continue
        return results
# ---- HIPCAMP (outdoor stays - JSON-LD with property info) ----
class HipcampScraper(OTAScraper):
    """Hipcamp - Outdoor stays (camping, glamping, cabins). JSON-LD Campground blocks."""
    name = "hipcamp"
    base_url = "https://www.hipcamp.com"
    delay = 3.0
    def search(self, market, max_pages=3):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        url = self.base_url + "/en-US/" + state_full + "/" + city_slug
        log.info("[Hipcamp] Fetching: %s", url)
        html = make_request(url)
        if not html:
            return []
        listings = self._parse_results(html, market)
        log.info("[Hipcamp] Found %d listings", len(listings))
        return listings
    def _parse_results(self, html, market):
        results = []
        ld_matches = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
        for ld_raw in ld_matches:
            try:
                ld_data = json.loads(ld_raw)
                if not isinstance(ld_data, dict):
                    continue
                ld_type = ld_data.get("@type", "")
                if ld_type in ("Campground", "LodgingBusiness", "VacationRental", "Hotel"):
                    listing = new_listing()
                    listing["property_name"] = ld_data.get("name", "")
                    listing["listing_url"] = ld_data.get("url", "")
                    listing["source_platform"] = "Hipcamp"
                    listing["property_type"] = ld_type
                    listing["market"] = market
                    listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    addr = ld_data.get("address", {})
                    if isinstance(addr, dict):
                        listing["address"] = addr.get("streetAddress", "")
                        listing["city"] = addr.get("addressLocality", "")
                        listing["state"] = addr.get("addressRegion", "")
                        listing["zip_code"] = addr.get("postalCode", "")
                        listing["country"] = addr.get("addressCountry", "")
                    rating_obj = ld_data.get("aggregateRating", {})
                    if isinstance(rating_obj, dict):
                        listing["rating"] = str(rating_obj.get("ratingValue", ""))
                        listing["review_count"] = str(rating_obj.get("reviewCount", ""))
                    if listing["property_name"]:
                        results.append(listing)
            except json.JSONDecodeError:
                continue
        return results
# ---- VACASA (major PM company - JSON-LD) ----
class VacasaScraper(OTAScraper):
    """Vacasa - Major PM company. Returns listing data via JSON-LD."""
    name = "vacasa"
    base_url = "https://www.vacasa.com"
    delay = 3.0
    def search(self, market, max_pages=3):
        listings = []
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        for page in range(1, max_pages + 1):
            url = self.base_url + "/usa/" + state_full + "/" + city_slug
            if page > 1:
                url += "?page=" + str(page)
            log.info("[Vacasa] Fetching page %d: %s", page, url)
            html = make_request(url)
            if not html:
                break
            page_listings = self._parse_results(html, market)
            if not page_listings:
                break
            listings.extend(page_listings)
            log.info("[Vacasa] Found %d listings on page %d", len(page_listings), page)
            self._delay()
        return listings
    def _parse_results(self, html, market):
        results = []
        ld_matches = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
        for ld_raw in ld_matches:
            try:
                ld_data = json.loads(ld_raw)
                if not isinstance(ld_data, dict):
                    continue
                ld_type = ld_data.get("@type", "")
                if ld_type == "ItemList":
                    for item in ld_data.get("itemListElement", []):
                        it = item.get("item", item)
                        if isinstance(it, dict) and it.get("name"):
                            listing = new_listing()
                            listing["property_name"] = it["name"]
                            listing["listing_url"] = it.get("url", "")
                            listing["source_platform"] = "Vacasa"
                            listing["management_company"] = "Vacasa"
                            listing["company_name"] = "Vacasa"
                            listing["market"] = market
                            listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                            self._extract_address(it, listing)
                            results.append(listing)
                elif ld_type in ("LodgingBusiness", "VacationRental", "House", "Apartment"):
                    if ld_data.get("name") and ld_data["name"] != "Vacasa":
                        listing = new_listing()
                        listing["property_name"] = ld_data["name"]
                        listing["listing_url"] = ld_data.get("url", "")
                        listing["source_platform"] = "Vacasa"
                        listing["management_company"] = "Vacasa"
                        listing["company_name"] = "Vacasa"
                        listing["market"] = market
                        listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        self._extract_address(ld_data, listing)
                        results.append(listing)
            except json.JSONDecodeError:
                continue
        # Fallback: search for property titles in HTML
        if not results:
            title_pattern = re.findall(
                r'class="[^"]*unit-name[^"]*"[^>]*>([^<]+)<', html, re.IGNORECASE
            )
            link_pattern = re.findall(
                r'href="(/unit/[^"]+)"', html
            )
            for i, title in enumerate(title_pattern):
                listing = new_listing()
                listing["property_name"] = title.strip()
                if i < len(link_pattern):
                    listing["listing_url"] = self.base_url + link_pattern[i]
                listing["source_platform"] = "Vacasa"
                listing["management_company"] = "Vacasa"
                listing["company_name"] = "Vacasa"
                listing["market"] = market
                listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                results.append(listing)
        return results
    def _extract_address(self, data, listing):
        addr = data.get("address", {})
        if isinstance(addr, dict):
            listing["address"] = addr.get("streetAddress", "")
            listing["city"] = addr.get("addressLocality", "")
            listing["state"] = addr.get("addressRegion", "")
            listing["zip_code"] = addr.get("postalCode", "")
            listing["country"] = addr.get("addressCountry", "")
# ---- TURNKEY VR (PM company - JSON-LD) ----
class TurnkeyScraper(OTAScraper):
    """TurnKey Vacation Rentals. Returns listing data via JSON-LD."""
    name = "turnkey"
    base_url = "https://www.turnkeyvr.com"
    delay = 3.0
    def search(self, market, max_pages=3):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        url = self.base_url + "/vacation-rentals/" + state_full + "/" + city_slug
        log.info("[TurnKey] Fetching: %s", url)
        html = make_request(url)
        if not html:
            return []
        listings = self._parse_results(html, market)
        log.info("[TurnKey] Found %d listings", len(listings))
        return listings
    def _parse_results(self, html, market):
        results = []
        ld_matches = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
        )
        for ld_raw in ld_matches:
            try:
                ld_data = json.loads(ld_raw)
                if not isinstance(ld_data, dict):
                    continue
                ld_type = ld_data.get("@type", "")
                if ld_type == "ItemList":
                    for item in ld_data.get("itemListElement", []):
                        it = item.get("item", item)
                        if isinstance(it, dict) and it.get("name"):
                            listing = new_listing()
                            listing["property_name"] = it["name"]
                            listing["listing_url"] = it.get("url", "")
                            listing["source_platform"] = "TurnKey"
                            listing["management_company"] = "TurnKey Vacation Rentals"
                            listing["company_name"] = "TurnKey Vacation Rentals"
                            listing["market"] = market
                            listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                            results.append(listing)
                elif ld_type in ("LodgingBusiness", "VacationRental", "House") and ld_data.get("name"):
                    listing = new_listing()
                    listing["property_name"] = ld_data["name"]
                    listing["listing_url"] = ld_data.get("url", "")
                    listing["source_platform"] = "TurnKey"
                    listing["management_company"] = "TurnKey Vacation Rentals"
                    listing["company_name"] = "TurnKey Vacation Rentals"
                    listing["market"] = market
                    listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    results.append(listing)
            except json.JSONDecodeError:
                continue
        return results
# ---- EVOLVE (PM company - __NEXT_DATA__) ----
class EvolveScraper(OTAScraper):
    """Evolve Vacation Rental - Major PM network. Uses __NEXT_DATA__ / Algolia search."""
    name = "evolve"
    base_url = "https://evolve.com"
    delay = 3.0
    def search(self, market, max_pages=3):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        url = self.base_url + "/vacation-rentals/us/" + state_abbrev + "/" + city_slug
        log.info("[Evolve] Fetching: %s", url)
        html = make_request(url)
        if not html:
            return []
        listings = self._parse_results(html, market)
        log.info("[Evolve] Found %d listings", len(listings))
        return listings
    def _parse_results(self, html, market):
        results = []
        # Try __NEXT_DATA__ for initial search results
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                pp = data.get("props", {}).get("pageProps", {})
                pd = pp.get("pageData", {})
                # Evolve sometimes embeds initialSearch with Algolia hits
                initial = pd.get("initialSearch", {})
                if isinstance(initial, dict):
                    hits = initial.get("hits", [])
                    for hit in hits:
                        if not isinstance(hit, dict):
                            continue
                        listing = new_listing()
                        listing["property_name"] = hit.get("title", hit.get("name", ""))
                        slug = hit.get("slug", hit.get("objectID", ""))
                        listing["listing_url"] = self.base_url + "/vacation-rentals/" + slug if slug else ""
                        listing["source_platform"] = "Evolve"
                        listing["management_company"] = "Evolve Vacation Rental"
                        listing["company_name"] = "Evolve Vacation Rental"
                        listing["market"] = market
                        listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        listing["bedrooms"] = str(hit.get("bedrooms", ""))
                        listing["bathrooms"] = str(hit.get("bathrooms", ""))
                        listing["max_guests"] = str(hit.get("guests", hit.get("maxGuests", "")))
                        listing["city"] = hit.get("city", "")
                        listing["state"] = hit.get("state", "")
                        listing["property_type"] = hit.get("propertyType", "")
                        if listing["property_name"]:
                            results.append(listing)
            except (json.JSONDecodeError, KeyError, AttributeError) as e:
                log.warning("[Evolve] Parse error: %s", e)
        # Fallback: look for property-specific listing URLs in HTML
        if not results:
            # Only match deep property URLs (at least 5 path segments)
            cards = re.findall(
                r'href="(/vacation-rentals/us/[a-z]{2}/[a-z-]+/[^"]+)"',
                html
            )
            seen_urls = set()
            for href in cards:
                parts = href.strip("/").split("/")
                # Need at least: vacation-rentals/us/XX/city/property-slug
                if len(parts) < 5:
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                prop_slug = parts[-1].replace("-", " ").title()
                listing = new_listing()
                listing["property_name"] = prop_slug
                listing["listing_url"] = self.base_url + href
                listing["source_platform"] = "Evolve"
                listing["management_company"] = "Evolve Vacation Rental"
                listing["company_name"] = "Evolve Vacation Rental"
                listing["market"] = market
                listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                results.append(listing)
        return results
# ---------------------------------------------------------------------------
# Public STR Registry Lookup Helper
# ---------------------------------------------------------------------------
class STRRegistryLookup:
    """
    Helper to search public Short-Term Rental permit registries.
    Many cities/counties publish STR permits as public records with owner contact info.
    """
    REGISTRIES = {
        "scottsdale, az": {
            "url": "https://eservices.scottsdaleaz.gov/bldgresources/Permits/ShortTermRental",
            "notes": "Scottsdale STR permit registry - searchable by address",
        },
        "phoenix, az": {
            "url": "https://www.phoenix.gov/pdd/short-term-rentals",
            "notes": "Phoenix STR registry",
        },
        "sedona, az": {
            "url": "https://www.sedonaaz.gov/departments/community-development/short-term-rentals",
            "notes": "Sedona STR registry",
        },
        "miami, fl": {
            "url": "https://www.miamidade.gov/global/economy/short-term-rentals.page",
            "notes": "Miami-Dade STR registry",
        },
        "orlando, fl": {
            "url": "https://www.orangecountyfl.net/PlanningDevelopment/ShortTermRentals.aspx",
            "notes": "Orange County STR registry",
        },
        "kissimmee, fl": {
            "url": "https://experience.arcgis.com/experience/osceola-str",
            "notes": "Osceola County (Kissimmee) STR map/registry",
        },
        "destin, fl": {
            "url": "https://myokaloosa.com/growth-management/short-term-rentals",
            "notes": "Okaloosa County STR registry",
        },
        "nashville, tn": {
            "url": "https://www.nashville.gov/departments/codes/short-term-rental-permits",
            "notes": "Nashville STR permits - searchable database",
        },
        "gatlinburg, tn": {
            "url": "https://www.gatlinburgtn.gov/short-term-rentals",
            "notes": "Gatlinburg STR registry",
        },
        "pigeon forge, tn": {
            "url": "https://www.cityofpigeonforge.com/short-term-rentals",
            "notes": "Pigeon Forge STR registry",
        },
        "denver, co": {
            "url": "https://www.denvergov.org/Government/Agencies-Departments-Offices/Short-Term-Rentals",
            "notes": "Denver STR license registry",
        },
        "breckenridge, co": {
            "url": "https://www.townofbreckenridge.com/government/departments/community-development/short-term-rentals",
            "notes": "Breckenridge STR registry",
        },
        "los angeles, ca": {
            "url": "https://planning.lacity.org/plans-policies/home-sharing",
            "notes": "LA home sharing registry",
        },
        "san diego, ca": {
            "url": "https://www.sandiego.gov/treasurer/short-term-residential-occupancy",
            "notes": "San Diego STRO registry",
        },
        "palm springs, ca": {
            "url": "https://www.palmspringsca.gov/government/departments/planning-services/vacation-rental-registration",
            "notes": "Palm Springs vacation rental registration",
        },
        "austin, tx": {
            "url": "https://www.austintexas.gov/str",
            "notes": "Austin STR license search",
        },
        "san antonio, tx": {
            "url": "https://www.sanantonio.gov/DSD/Short-Term-Rentals",
            "notes": "San Antonio STR registry",
        },
        "honolulu, hi": {
            "url": "https://www.honolulu.gov/dpp/short-term-rentals.html",
            "notes": "Honolulu short-term rental registry",
        },
        "maui, hi": {
            "url": "https://www.mauicounty.gov/1068/Short-Term-Rental-Homes",
            "notes": "Maui STR registry",
        },
        "las vegas, nv": {
            "url": "https://www.lasvegasnevada.gov/Residents/Short-Term-Rentals",
            "notes": "Las Vegas STR registry",
        },
        "charleston, sc": {
            "url": "https://www.charleston-sc.gov/str",
            "notes": "Charleston STR registry",
        },
        "asheville, nc": {
            "url": "https://www.ashevillenc.gov/department/development-services/short-term-rentals/",
            "notes": "Asheville STR registry",
        },
        "savannah, ga": {
            "url": "https://www.savannahga.gov/3229/Short-Term-Vacation-Rentals",
            "notes": "Savannah STVR registry",
        },
    }
    @classmethod
    def lookup(cls, market):
        """Find the STR registry for a given market."""
        market_lower = market.strip().lower()
        if market_lower in cls.REGISTRIES:
            return cls.REGISTRIES[market_lower]
        # Try partial match
        city = market_lower.split(",")[0].strip()
        for key, val in cls.REGISTRIES.items():
            if city in key:
                return val
        return None
    @classmethod
    def get_county_assessor_url(cls, market):
        """Get a Google search URL for the county assessor property search."""
        city = market.split(",")[0].strip()
        state = market.split(",")[1].strip() if "," in market else ""
        query = city + " " + state + " county assessor property search"
        return "https://www.google.com/search?q=" + urllib.parse.quote(query)
    @classmethod
    def print_registry_info(cls, market):
        """Print STR registry and county assessor info for a market."""
        registry = cls.lookup(market)
        if registry:
            log.info("STR Registry found for %s:", market)
            log.info("  URL: %s", registry["url"])
            log.info("  Notes: %s", registry["notes"])
        else:
            log.info("No known STR registry for %s - check your local city/county website", market)
        assessor_url = cls.get_county_assessor_url(market)
        log.info("County assessor search: %s", assessor_url)
# ---------------------------------------------------------------------------
# AirDNA CSV Merge
# ---------------------------------------------------------------------------
AIRDNA_COL_MAP = {
    "property name": "property_name", "title": "property_name",
    "listing title": "property_name", "listing name": "property_name",
    "airbnb listing url": "listing_url", "listing url": "listing_url",
    "url": "listing_url", "address": "address", "full address": "address",
    "city": "city", "state": "state", "zip": "zip_code", "zip code": "zip_code",
    "bedrooms": "bedrooms", "bathrooms": "bathrooms",
    "accommodates": "max_guests", "max guests": "max_guests",
    "annual revenue": "nightly_rate", "revenue": "nightly_rate",
    "average daily rate": "nightly_rate", "adr": "nightly_rate",
    "host name": "host_name", "hostname": "host_name",
    "property manager": "host_name", "management company": "management_company",
    "property type": "property_type", "rating": "rating",
    "review count": "review_count", "reviews": "review_count",
}
def read_airdna_csv(filepath):
    """Read an AirDNA export CSV and return normalized dicts."""
    rows = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        col_map = {}
        for idx, raw_col in enumerate(header):
            clean = raw_col.strip().lower()
            if clean in AIRDNA_COL_MAP:
                col_map[idx] = AIRDNA_COL_MAP[clean]
        log.info("Mapped %d / %d AirDNA columns", len(col_map), len(header))
        for row in reader:
            record = new_listing()
            for idx, val in enumerate(row):
                if idx in col_map:
                    record[col_map[idx]] = val.strip()
            record["source_platform"] = "AirDNA"
            record["scraped_at"] = datetime.now(timezone.utc).isoformat()
            rows.append(record)
    log.info("Read %d listings from AirDNA CSV: %s", len(rows), filepath)
    return rows
# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------
def deduplicate(listings):
    """Remove duplicate listings based on property name + city + source."""
    seen = set()
    unique = []
    for listing in listings:
        key = (
            listing.get("property_name", "").lower().strip(),
            listing.get("city", "").lower().strip(),
            listing.get("source_platform", "").lower(),
        )
        if key not in seen and key[0]:
            seen.add(key)
            unique.append(listing)
    removed = len(listings) - len(unique)
    if removed:
        log.info("Removed %d duplicate listings", removed)
    return unique
# ---------------------------------------------------------------------------
# Enrichment: Split names for Instantly.ai
# ---------------------------------------------------------------------------
def enrich_for_instantly(listings):
    """Add first_name, last_name, company_name fields for Instantly.ai import."""
    for listing in listings:
        host = listing.get("host_name", "")
        if host and not listing.get("first_name"):
            first, last = split_name(host)
            listing["first_name"] = first
            listing["last_name"] = last
        company = listing.get("management_company", "")
        if not listing.get("company_name"):
            listing["company_name"] = company or host
    return listings
# ---------------------------------------------------------------------------
# Hunter.io Email Enrichment
# ---------------------------------------------------------------------------
def hunter_domain_search(domain, api_key):
    """Use Hunter.io domain-search to find emails at a domain."""
    if not api_key or not domain:
        return []
    url = (
        "https://api.hunter.io/v2/domain-search"
        "?domain=" + urllib.parse.quote(domain) + "&api_key=" + api_key + "&limit=5"
    )
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return [
                {
                    "email": e.get("value", ""),
                    "confidence": str(e.get("confidence", "")),
                }
                for e in data.get("data", {}).get("emails", [])
            ]
    except Exception as e:
        log.warning("Hunter.io failed for %s: %s", domain, e)
    return []
def enrich_emails(listings, api_key):
    """Attempt to find emails via Hunter.io for listings with management companies."""
    if not api_key:
        return listings
    enriched_count = 0
    for listing in listings:
        company = listing.get("management_company", "") or listing.get("company_name", "")
        if not company or listing.get("contact_email"):
            continue
        # Try to build a domain from the company name
        slug = re.sub(r"[^a-zA-Z0-9]", "", company).lower()
        if len(slug) < 3:
            continue
        domain = slug + ".com"
        results = hunter_domain_search(domain, api_key)
        if results:
            listing["contact_email"] = results[0]["email"]
            enriched_count += 1
            log.info("  Found email for %s: %s", company, results[0]["email"])
    log.info("Hunter.io enriched %d / %d listings with emails", enriched_count, len(listings))
    return listings
# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def write_output_csv(rows, filepath):
    """Write enriched rows to a CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    log.info("Wrote %d rows to %s", len(rows), filepath)
# ---------------------------------------------------------------------------
# Registry: all available scrapers
# ---------------------------------------------------------------------------
SCRAPERS = {
    "houfy": HoufyScraper,
    "glampinghub": GlampingHubScraper,
    "hipcamp": HipcampScraper,
    "vacasa": VacasaScraper,
    "turnkey": TurnkeyScraper,
    "evolve": EvolveScraper,
}
def list_sources():
    return ", ".join(sorted(SCRAPERS.keys()))
# ---------------------------------------------------------------------------
# Parallel Execution
# ---------------------------------------------------------------------------
def run_parallel_scrape(market, sources, max_pages=3, workers=3):
    """Run multiple OTA scrapers in parallel using ThreadPoolExecutor."""
    all_listings = []
    valid_sources = []
    for src in sources:
        if src not in SCRAPERS:
            log.warning("Unknown source: %s (available: %s)", src, list_sources())
        else:
            valid_sources.append(src)
    if not valid_sources:
        log.error("No valid sources specified")
        return []
    log.info("Running %d scrapers in parallel (workers=%d)", len(valid_sources), workers)
    with ThreadPoolExecutor(max_workers=min(workers, len(valid_sources))) as executor:
        futures = {}
        for src_name in valid_sources:
            cls = SCRAPERS[src_name]
            scraper = cls()
            future = executor.submit(scraper.search, market, max_pages)
            futures[future] = src_name
        for future in as_completed(futures):
            src_name = futures[future]
            try:
                results = future.result()
                log.info("[%s] Returned %d listings", src_name, len(results))
                all_listings.extend(results)
            except Exception as e:
                log.error("[%s] Failed: %s", src_name, e)
    return all_listings
# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description=(
            "STR Multi-OTA Contact Scraper\n\n"
            "Search multiple OTAs for vacation rental listings and output a CSV\n"
            "for Clay.com enrichment + Instantly.ai outbound.\n\n"
            "PROVEN sources: houfy (best - returns host names), glampinghub,\n"
            "hipcamp, vacasa, turnkey, evolve"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--market", "-m", required=True,
        help="Market to search (e.g., 'Scottsdale, AZ')"
    )
    parser.add_argument(
        "--output", "-o", default="str_ota_contacts.csv",
        help="Output CSV file path (default: str_ota_contacts.csv)"
    )
    parser.add_argument(
        "--sources", "-s",
        default=",".join(sorted(SCRAPERS.keys())),
        help="Comma-separated OTA sources. Available: " + list_sources() + " (default: all)"
    )
    parser.add_argument(
        "--max-pages", type=int, default=3,
        help="Max pages to scrape per source (default: 3)"
    )
    parser.add_argument(
        "--workers", "-w", type=int, default=3,
        help="Number of parallel workers (default: 3)"
    )
    parser.add_argument(
        "--airdna-csv",
        help="Optional AirDNA CSV export to merge with scraped data"
    )
    parser.add_argument(
        "--hunter-api-key",
        default=os.environ.get("HUNTER_API_KEY", ""),
        help="Hunter.io API key for email enrichment (or set HUNTER_API_KEY env var)"
    )
    parser.add_argument(
        "--list-sources", action="store_true",
        help="List all available OTA sources and exit"
    )
    parser.add_argument(
        "--show-registry", action="store_true",
        help="Show public STR registry info for the market"
    )
    parser.add_argument(
        "--no-dedup", action="store_true",
        help="Skip deduplication"
    )
    parser.add_argument(
        "--delay-multiplier", type=float, default=1.0,
        help="Multiply all request delays by this factor (default: 1.0, use 2.0 to be more conservative)"
    )
    args = parser.parse_args()
    if args.list_sources:
        print("Available OTA sources (all tested and working):")
        print()
        for name in sorted(SCRAPERS.keys()):
            cls = SCRAPERS[name]
            scraper = cls()
            doc_line = cls.__doc__.strip().split("\n")[0] if cls.__doc__ else ""
            print("  {:15s}  delay={:.1f}s  {}".format(name, scraper.delay, doc_line))
        print()
        print("Recommended workflow:")
        print("  1. Run this script -> outputs CSV")
        print("  2. Upload CSV to Clay.com -> enrich with emails/phones/LinkedIn")
        print("  3. Export from Clay -> import into Instantly.ai for outbound")
        sys.exit(0)
    # Apply delay multiplier
    if args.delay_multiplier != 1.0:
        for cls in SCRAPERS.values():
            original = cls.delay
            cls.delay = original * args.delay_multiplier
    sources = [s.strip() for s in args.sources.split(",")]
    log.info("=" * 60)
    log.info("STR Multi-OTA Contact Scraper")
    log.info("=" * 60)
    log.info("Market:     %s", args.market)
    log.info("Sources:    %s", ", ".join(sources))
    log.info("Max pages:  %d per source", args.max_pages)
    log.info("Workers:    %d", args.workers)
    log.info("Output:     %s", args.output)
    log.info("Hunter.io:  %s", "ON" if args.hunter_api_key else "OFF")
    # Show STR registry info
    if args.show_registry:
        STRRegistryLookup.print_registry_info(args.market)
    # 1. Scrape OTAs in parallel
    all_listings = run_parallel_scrape(
        market=args.market,
        sources=sources,
        max_pages=args.max_pages,
        workers=args.workers,
    )
    # 2. Merge AirDNA CSV if provided
    if args.airdna_csv:
        if Path(args.airdna_csv).exists():
            airdna_rows = read_airdna_csv(args.airdna_csv)
            for row in airdna_rows:
                row["market"] = args.market
            all_listings.extend(airdna_rows)
        else:
            log.warning("AirDNA CSV not found: %s", args.airdna_csv)
    # 3. Deduplicate
    if not args.no_dedup:
        all_listings = deduplicate(all_listings)
    # 4. Enrich for Instantly.ai
    all_listings = enrich_for_instantly(all_listings)
    # 5. Hunter.io email enrichment
    if args.hunter_api_key:
        all_listings = enrich_emails(all_listings, args.hunter_api_key)
    # 6. Write output
    write_output_csv(all_listings, args.output)
    # 7. Summary
    by_source = {}
    for listing in all_listings:
        src = listing.get("source_platform", "Unknown")
        by_source[src] = by_source.get(src, 0) + 1
    log.info("=" * 60)
    log.info("SUMMARY")
    log.info("=" * 60)
    log.info("Total unique listings: %d", len(all_listings))
    for src, count in sorted(by_source.items()):
        log.info("  %-20s %d", src, count)
    with_host = sum(1 for r in all_listings if r.get("host_name"))
    with_email = sum(1 for r in all_listings if r.get("contact_email"))
    log.info("With host name:      %d", with_host)
    log.info("With email:          %d", with_email)
    log.info("Output saved to:     %s", args.output)
    # STR registry info
    registry = STRRegistryLookup.lookup(args.market)
    if registry:
        log.info("")
        log.info("PUBLIC STR REGISTRY for %s:", args.market)
        log.info("  %s", registry["url"])
        log.info("  %s", registry["notes"])
    log.info("")
    log.info("NEXT STEPS:")
    log.info("  1. Upload %s to Clay.com for email/phone/LinkedIn enrichment", args.output)
    log.info("     - Use 'Find Work Email' on the host_name + company_name columns")
    log.info("     - Use 'Find Phone Number' enrichment")
    log.info("     - Use 'Enrich Person' for LinkedIn profiles")
    log.info("  2. Export enriched CSV from Clay -> import into Instantly.ai")
    log.info("     - Map: first_name, last_name, company_name, contact_email")
    log.info("  3. For listings without emails, check the STR registry:")
    log.info("     %s", STRRegistryLookup.get_county_assessor_url(args.market))
if __name__ == "__main__":
    main()
