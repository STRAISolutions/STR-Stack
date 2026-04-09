#!/usr/bin/env python3
"""
STR Mega Contact Scraper — 5000+ Listings
==========================================
Scrapes 12 OTA / channel partner platforms + industry association directories
across 50 top US STR markets. Outputs a single CSV ready for Clay.com + Instantly.ai.

Sources:
  OTAs / Channel Partners:
    houfy, glampinghub, hipcamp, vacasa, turnkey, evolve,
    furnishedfinder, redawning, itrip, hometogo, flipkey, misterbandb

  Industry / Association Directories:
    vrma      (VRMA find-a-property-manager directory)
    expscott  (Experience Scottsdale lodging member directory)

Usage:
    python str_mega_scraper.py
    python str_mega_scraper.py --markets "Scottsdale, AZ,Nashville, TN"
    python str_mega_scraper.py --sources houfy,furnishedfinder,redawning,itrip
    python str_mega_scraper.py --max-pages 10 --workers 6 --output big_list.csv
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("str_mega")

# ---------------------------------------------------------------------------
# Top 50 STR Markets
# ---------------------------------------------------------------------------
TOP_STR_MARKETS = [
    # Arizona
    "Scottsdale, AZ", "Phoenix, AZ", "Sedona, AZ", "Flagstaff, AZ", "Tucson, AZ",
    "Tempe, AZ", "Mesa, AZ", "Chandler, AZ", "Cave Creek, AZ", "Fountain Hills, AZ",
    "Paradise Valley, AZ", "Prescott, AZ", "Lake Havasu City, AZ", "Peoria, AZ", "Glendale, AZ",
    # Florida
    "Orlando, FL", "Miami, FL", "Destin, FL", "Tampa, FL", "Naples, FL",
    "Key West, FL", "Panama City Beach, FL", "Fort Lauderdale, FL", "Clearwater, FL",
    "St. Augustine, FL", "Pensacola Beach, FL", "Daytona Beach, FL", "Siesta Key, FL",
    "Anna Maria Island, FL", "Marco Island, FL", "Sanibel, FL", "Amelia Island, FL",
    "Cocoa Beach, FL", "30A, FL", "Cape Coral, FL", "Kissimmee, FL",
    # Tennessee
    "Nashville, TN", "Gatlinburg, TN", "Pigeon Forge, TN", "Chattanooga, TN",
    "Sevierville, TN", "Knoxville, TN",
    # Colorado
    "Denver, CO", "Breckenridge, CO", "Vail, CO", "Steamboat Springs, CO", "Telluride, CO",
    "Estes Park, CO", "Aspen, CO", "Durango, CO", "Manitou Springs, CO", "Colorado Springs, CO",
    # Texas
    "Austin, TX", "San Antonio, TX", "Galveston, TX", "South Padre Island, TX",
    "Houston, TX", "Dallas, TX", "New Braunfels, TX", "Fredericksburg, TX", "Wimberley, TX",
    # California
    "San Diego, CA", "Palm Springs, CA", "Los Angeles, CA", "Lake Tahoe, CA",
    "Santa Barbara, CA", "Napa, CA", "Sonoma, CA", "Carmel, CA", "Big Bear, CA",
    "Mammoth Lakes, CA", "Joshua Tree, CA", "Malibu, CA", "Laguna Beach, CA",
    "South Lake Tahoe, CA", "Healdsburg, CA",
    # Carolinas / Southeast
    "Asheville, NC", "Myrtle Beach, SC", "Charleston, SC", "Hilton Head, SC",
    "Outer Banks, NC", "Boone, NC", "Brevard, NC", "Bryson City, NC",
    "Savannah, GA", "Blue Ridge, GA", "Gulf Shores, AL", "Jekyll Island, GA",
    "St. Simons Island, GA", "Tybee Island, GA",
    # Northeast
    "Cape Cod, MA", "Ocean City, MD", "Nantucket, MA", "Martha's Vineyard, MA",
    "Bar Harbor, ME", "Newport, RI", "Hamptons, NY", "Catskills, NY",
    "Finger Lakes, NY", "Hudson Valley, NY", "Virginia Beach, VA", "Williamsburg, VA",
    # Mountain / West
    "Las Vegas, NV", "Park City, UT", "Bend, OR", "Bozeman, MT",
    "Jackson, WY", "Moab, UT", "Santa Fe, NM", "Taos, NM",
    "Sun Valley, ID", "Coeur d'Alene, ID", "Whitefish, MT", "Big Sky, MT",
    "St. George, UT", "Springdale, UT", "Incline Village, NV",
    # Pacific Northwest
    "Seattle, WA", "Portland, OR", "Cannon Beach, OR", "Tofino, BC",
    # Hawaii
    "Maui, HI", "Kauai, HI", "Waikiki, HI", "Kona, HI", "Hilo, HI",
    # Midwest
    "Traverse City, MI", "Door County, WI", "Branson, MO", "Lake of the Ozarks, MO",
    "Put-in-Bay, OH", "Holland, MI",
    # Mid-Atlantic
    "Rehoboth Beach, DE", "Chincoteague, VA", "Shenandoah, VA",
    # Mountain Southeast
    "Chattanooga, TN", "Hot Springs, AR", "Eureka Springs, AR",
    # Canada
    "Muskoka, ON", "Whistler, BC", "Banff, AB", "Toronto, ON", "Vancouver, BC",
    "Niagara-on-the-Lake, ON", "Victoria, BC", "Kelowna, BC", "Mont-Tremblant, QC",
    "Prince Edward Island, PE", "Halifax, NS", "Ottawa, ON", "Calgary, AB",
    "Canmore, AB", "Collingwood, ON", "Prince George, BC",
]

# ---------------------------------------------------------------------------
# User agents
# ---------------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
]

def make_request(url, headers=None, timeout=25):
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        log.debug("HTTP %d: %s", e.code, url)
        return None
    except Exception as e:
        log.debug("Request failed %s: %s", url, e)
        return None

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------
OUTPUT_COLUMNS = [
    "property_name", "listing_url", "source_platform",
    "address", "city", "state", "zip_code", "country",
    "property_type", "bedrooms", "bathrooms", "max_guests",
    "nightly_rate", "rating", "review_count",
    "host_name", "management_company", "host_profile_url", "host_username",
    "contact_email", "contact_phone", "website",
    "market", "scraped_at",
    "first_name", "last_name", "company_name",
]

def new_listing():
    return {col: "" for col in OUTPUT_COLUMNS}

def split_name(full_name):
    parts = full_name.strip().split(None, 1)
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")

# ---------------------------------------------------------------------------
# Market parsing helpers
# ---------------------------------------------------------------------------
STATE_ABBREV_TO_FULL = {
    # US states
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
    # Canadian provinces
    "on": "ontario", "bc": "british-columbia", "ab": "alberta", "qc": "quebec",
    "ns": "nova-scotia", "nb": "new-brunswick", "mb": "manitoba", "sk": "saskatchewan",
    "pe": "prince-edward-island", "nl": "newfoundland",
}

def parse_market(market):
    parts = [p.strip() for p in market.split(",")]
    city = parts[0] if parts else ""
    state_abbrev = parts[1].strip().lower() if len(parts) > 1 else ""
    state_full = STATE_ABBREV_TO_FULL.get(state_abbrev, state_abbrev)
    return city, state_abbrev, state_full

# ---------------------------------------------------------------------------
# Base scraper
# ---------------------------------------------------------------------------
class OTAScraper:
    name = "base"
    delay = 2.0

    def search(self, market, max_pages=3):
        raise NotImplementedError

    def _sleep(self):
        time.sleep(self.delay * random.uniform(0.6, 1.4))

    def _extract_ld_items(self, html, market, platform, pm_company=""):
        """Extract listings from JSON-LD ItemList or individual LodgingBusiness blocks."""
        results = []
        ld_blocks = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE
        )
        for raw in ld_blocks:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            ld_type = data.get("@type", "")
            if ld_type == "ItemList":
                for item in data.get("itemListElement", []):
                    it = item.get("item", item)
                    if not isinstance(it, dict):
                        continue
                    name = it.get("name", "")
                    if not name:
                        continue
                    listing = new_listing()
                    listing["property_name"] = name
                    listing["listing_url"] = it.get("url", "")
                    listing["source_platform"] = platform
                    listing["management_company"] = pm_company
                    listing["company_name"] = pm_company
                    listing["market"] = market
                    listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    addr = it.get("address", {})
                    if isinstance(addr, dict):
                        listing["address"] = addr.get("streetAddress", "")
                        listing["city"] = addr.get("addressLocality", "")
                        listing["state"] = addr.get("addressRegion", "")
                        listing["zip_code"] = addr.get("postalCode", "")
                    results.append(listing)
            elif ld_type in ("LodgingBusiness", "VacationRental", "House",
                             "Apartment", "Campground", "Hotel", "Resort"):
                name = data.get("name", "")
                if not name or name == platform:
                    continue
                listing = new_listing()
                listing["property_name"] = name
                listing["listing_url"] = data.get("url", "")
                listing["source_platform"] = platform
                listing["management_company"] = pm_company
                listing["company_name"] = pm_company
                listing["market"] = market
                listing["scraped_at"] = datetime.now(timezone.utc).isoformat()
                addr = data.get("address", {})
                if isinstance(addr, dict):
                    listing["address"] = addr.get("streetAddress", "")
                    listing["city"] = addr.get("addressLocality", "")
                    listing["state"] = addr.get("addressRegion", "")
                    listing["zip_code"] = addr.get("postalCode", "")
                rat = data.get("aggregateRating", {})
                if isinstance(rat, dict):
                    listing["rating"] = str(rat.get("ratingValue", ""))
                    listing["review_count"] = str(rat.get("reviewCount", ""))
                results.append(listing)
        return results

# ===========================================================================
# EXISTING PROVEN SCRAPERS
# ===========================================================================

class HoufyScraper(OTAScraper):
    """Houfy — best source, returns host first/last/username."""
    name = "houfy"
    delay = 2.0

    def search(self, market, max_pages=5):
        listings = []
        city, state_abbrev, _ = parse_market(market)
        slug = city.lower().replace(" ", "-") + "-" + state_abbrev
        for page in range(1, max_pages + 1):
            url = "https://www.houfy.com/vacation-rentals/" + slug
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                break
            found = self._parse(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not nd:
            return results
        try:
            data = json.loads(nd.group(1))
            raw = (data.get("props", {}).get("pageProps", {})
                   .get("data", {}).get("listings", []))
            for item in raw:
                if not isinstance(item, dict):
                    continue
                fname = item.get("fname", "")
                lname = item.get("lname", "")
                uname = item.get("uname", "")
                listing_id = item.get("ID", "")
                l = new_listing()
                l["property_name"] = item.get("TITLE", "")
                l["listing_url"] = "https://www.houfy.com/listing/" + str(listing_id) if listing_id else ""
                l["source_platform"] = "Houfy"
                l["market"] = market
                l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                l["first_name"] = fname
                l["last_name"] = lname
                l["host_name"] = (fname + " " + lname).strip()
                l["host_username"] = uname
                l["host_profile_url"] = "https://www.houfy.com/user/" + uname if uname else ""
                l["company_name"] = uname
                l["bedrooms"] = str(item.get("bedrooms", ""))
                l["bathrooms"] = str(item.get("bathrooms", ""))
                l["max_guests"] = str(item.get("guests", ""))
                l["nightly_rate"] = str(item.get("baseprice", ""))
                l["rating"] = str(item.get("rating_avg", ""))
                l["review_count"] = str(item.get("tot_reviews", ""))
                if l["property_name"]:
                    results.append(l)
        except Exception as e:
            log.debug("[Houfy] parse error: %s", e)
        return results


class GlampingHubScraper(OTAScraper):
    """Glamping Hub — JSON-LD ItemList."""
    name = "glampinghub"
    delay = 2.5
    STATE_REGIONS = {
        "az": "southwest", "nm": "southwest", "tx": "southwest", "ok": "southwest",
        "ca": "west", "nv": "west", "or": "west", "wa": "west", "co": "west",
        "ut": "west", "id": "west", "mt": "west", "wy": "west", "hi": "west", "ak": "west",
        "fl": "southeast", "ga": "southeast", "sc": "southeast", "nc": "southeast",
        "al": "southeast", "ms": "southeast", "tn": "southeast", "va": "southeast",
        "ny": "northeast", "nj": "northeast", "ma": "northeast", "ct": "northeast",
        "pa": "northeast", "me": "northeast", "nh": "northeast", "vt": "northeast",
        "ri": "northeast", "md": "northeast", "de": "northeast",
        "il": "midwest", "oh": "midwest", "mi": "midwest", "in": "midwest",
        "wi": "midwest", "mn": "midwest", "ia": "midwest", "mo": "midwest",
        "ky": "south", "wv": "south", "ar": "south", "la": "south",
    }

    def search(self, market, max_pages=5):
        listings = []
        city, state_abbrev, state_full = parse_market(market)
        region = self.STATE_REGIONS.get(state_abbrev, "")
        if not region:
            return []
        state_name = state_full.replace("-", "")
        city_slug = city.lower().replace(" ", "")
        for page in range(1, max_pages + 1):
            url = ("https://glampinghub.com/unitedstatesofamerica/" + region
                   + "/" + state_name + "/" + city_slug + "/")
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                break
            found = self._extract_ld_items(html, market, "Glamping Hub")
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings


class HipcampScraper(OTAScraper):
    """Hipcamp — JSON-LD Campground/LodgingBusiness."""
    name = "hipcamp"
    delay = 3.0

    def search(self, market, max_pages=3):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        url = "https://www.hipcamp.com/en-US/" + state_full + "/" + city_slug
        html = make_request(url)
        if not html:
            return []
        return self._extract_ld_items(html, market, "Hipcamp")


class VacasaScraper(OTAScraper):
    """Vacasa — major PM, JSON-LD."""
    name = "vacasa"
    delay = 3.0

    def search(self, market, max_pages=5):
        listings = []
        city, _, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        for page in range(1, max_pages + 1):
            url = "https://www.vacasa.com/usa/" + state_full + "/" + city_slug
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                break
            found = self._extract_ld_items(html, market, "Vacasa", "Vacasa")
            # fallback: unit-name spans
            if not found:
                titles = re.findall(r'class="[^"]*unit-name[^"]*"[^>]*>([^<]+)<', html, re.I)
                links = re.findall(r'href="(/unit/[^"]+)"', html)
                for i, t in enumerate(titles):
                    l = new_listing()
                    l["property_name"] = t.strip()
                    l["listing_url"] = "https://www.vacasa.com" + links[i] if i < len(links) else ""
                    l["source_platform"] = "Vacasa"
                    l["management_company"] = "Vacasa"
                    l["company_name"] = "Vacasa"
                    l["market"] = market
                    l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    found.append(l)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings


class TurnkeyScraper(OTAScraper):
    """TurnKey VR — JSON-LD."""
    name = "turnkey"
    delay = 3.0

    def search(self, market, max_pages=3):
        city, _, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        url = "https://www.turnkeyvr.com/vacation-rentals/" + state_full + "/" + city_slug
        html = make_request(url)
        if not html:
            return []
        return self._extract_ld_items(html, market, "TurnKey", "TurnKey Vacation Rentals")


class EvolveScraper(OTAScraper):
    """Evolve — __NEXT_DATA__ / Algolia."""
    name = "evolve"
    delay = 3.0

    def search(self, market, max_pages=3):
        city, state_abbrev, _ = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        url = "https://evolve.com/vacation-rentals/us/" + state_abbrev + "/" + city_slug
        html = make_request(url)
        if not html:
            return []
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                hits = (data.get("props", {}).get("pageProps", {})
                        .get("pageData", {}).get("initialSearch", {}).get("hits", []))
                for hit in hits:
                    l = new_listing()
                    l["property_name"] = hit.get("title", hit.get("name", ""))
                    slug = hit.get("slug", hit.get("objectID", ""))
                    l["listing_url"] = "https://evolve.com/vacation-rentals/" + slug if slug else ""
                    l["source_platform"] = "Evolve"
                    l["management_company"] = "Evolve Vacation Rental"
                    l["company_name"] = "Evolve Vacation Rental"
                    l["market"] = market
                    l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    l["bedrooms"] = str(hit.get("bedrooms", ""))
                    l["bathrooms"] = str(hit.get("bathrooms", ""))
                    l["city"] = hit.get("city", "")
                    l["state"] = hit.get("state", "")
                    if l["property_name"]:
                        results.append(l)
            except Exception:
                pass
        # fallback deep href pattern
        if not results:
            seen = set()
            for href in re.findall(r'href="(/vacation-rentals/us/[a-z]{2}/[a-z-]+/[^"]+)"', html):
                parts = href.strip("/").split("/")
                if len(parts) < 5 or href in seen:
                    continue
                seen.add(href)
                l = new_listing()
                l["property_name"] = parts[-1].replace("-", " ").title()
                l["listing_url"] = "https://evolve.com" + href
                l["source_platform"] = "Evolve"
                l["management_company"] = "Evolve Vacation Rental"
                l["company_name"] = "Evolve Vacation Rental"
                l["market"] = market
                l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                results.append(l)
        return results


# ===========================================================================
# NEW CHANNEL PARTNER SCRAPERS
# ===========================================================================

class FurnishedFinderScraper(OTAScraper):
    """FurnishedFinder — corporate / monthly rentals. Large dataset of individual landlords."""
    name = "furnishedfinder"
    delay = 2.5

    def search(self, market, max_pages=5):
        city, state_abbrev, _ = parse_market(market)
        city_slug = city.replace(" ", "_") + "_" + state_abbrev.upper()
        listings = []
        for page in range(1, max_pages + 1):
            url = "https://www.furnishedfinder.com/housing/" + city_slug
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                break
            found = self._parse(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse(self, html, market):
        results = []
        # Try JSON-LD first
        ld = self._extract_ld_items(html, market, "FurnishedFinder")
        if ld:
            return ld
        # Try __NEXT_DATA__
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                props = data.get("props", {}).get("pageProps", {})
                listings_raw = props.get("listings", props.get("properties", []))
                for item in listings_raw:
                    if not isinstance(item, dict):
                        continue
                    l = new_listing()
                    l["property_name"] = item.get("title", item.get("name", item.get("headline", "")))
                    slug = item.get("slug", item.get("id", ""))
                    l["listing_url"] = "https://www.furnishedfinder.com/housing/" + str(slug) if slug else ""
                    l["source_platform"] = "FurnishedFinder"
                    l["market"] = market
                    l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    l["bedrooms"] = str(item.get("bedrooms", item.get("beds", "")))
                    l["bathrooms"] = str(item.get("bathrooms", item.get("baths", "")))
                    host = item.get("landlord", item.get("host", item.get("owner", {})))
                    if isinstance(host, dict):
                        l["host_name"] = host.get("name", host.get("full_name", ""))
                        l["contact_email"] = host.get("email", "")
                        l["contact_phone"] = host.get("phone", "")
                    l["nightly_rate"] = str(item.get("price", item.get("monthly_rate", "")))
                    if l["property_name"]:
                        results.append(l)
            except Exception as e:
                log.debug("[FurnishedFinder] parse error: %s", e)
        # HTML fallback — listing cards
        if not results:
            # Title patterns from listing cards
            titles = re.findall(
                r'(?:class="[^"]*(?:listing-title|property-title|unit-title)[^"]*"[^>]*>|<h[23][^>]*>)\s*([^<]{5,80})\s*</',
                html, re.IGNORECASE
            )
            urls = re.findall(r'href="(https://www\.furnishedfinder\.com/housing/[^"]+)"', html)
            phones = re.findall(r'(\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4})', html)
            for i, title in enumerate(titles[:50]):
                l = new_listing()
                l["property_name"] = title.strip()
                l["listing_url"] = urls[i] if i < len(urls) else ""
                l["source_platform"] = "FurnishedFinder"
                l["market"] = market
                l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                if i < len(phones):
                    l["contact_phone"] = phones[i]
                results.append(l)
        return results


class RedAwningScraper(OTAScraper):
    """RedAwning — PM aggregator representing thousands of independent managers."""
    name = "redawning"
    delay = 2.5

    def search(self, market, max_pages=5):
        city, state_abbrev, _ = parse_market(market)
        city_slug = city.lower().replace(" ", "-") + "-" + state_abbrev.lower()
        listings = []
        for page in range(1, max_pages + 1):
            url = "https://redawning.com/vacation-rentals/" + city_slug
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                break
            found = self._parse(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse(self, html, market):
        results = self._extract_ld_items(html, market, "RedAwning")
        if results:
            return results
        # __NEXT_DATA__ fallback
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                pp = data.get("props", {}).get("pageProps", {})
                for key in ("listings", "properties", "units", "results"):
                    items = pp.get(key, [])
                    if items:
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            l = new_listing()
                            l["property_name"] = item.get("name", item.get("title", ""))
                            l["listing_url"] = item.get("url", item.get("listing_url", ""))
                            l["source_platform"] = "RedAwning"
                            l["market"] = market
                            l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                            l["bedrooms"] = str(item.get("bedrooms", ""))
                            l["bathrooms"] = str(item.get("bathrooms", ""))
                            pm = item.get("property_manager", item.get("manager", {}))
                            if isinstance(pm, dict):
                                l["management_company"] = pm.get("name", "")
                                l["company_name"] = pm.get("name", "")
                                l["website"] = pm.get("website", "")
                            if l["property_name"]:
                                results.append(l)
                        break
            except Exception as e:
                log.debug("[RedAwning] parse error: %s", e)
        # HTML fallback
        if not results:
            names = re.findall(
                r'(?:data-name|aria-label)="([^"]{5,80})"',
                html
            )
            links = re.findall(r'href="(https://redawning\.com/vacation-rentals/[^"]+)"', html)
            seen = set()
            for i, name in enumerate(names):
                if name in seen:
                    continue
                seen.add(name)
                l = new_listing()
                l["property_name"] = name.strip()
                l["listing_url"] = links[i] if i < len(links) else ""
                l["source_platform"] = "RedAwning"
                l["market"] = market
                l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                results.append(l)
        return results


class iTripScraper(OTAScraper):
    """iTrip Vacations — nationwide franchise PM network."""
    name = "itrip"
    delay = 2.5

    def search(self, market, max_pages=5):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        state_slug = state_full.replace("-", "")
        listings = []
        for page in range(1, max_pages + 1):
            url = "https://itrip.us/vacation-rentals/" + city_slug + "-" + state_abbrev.lower()
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                # Try alternate slug format
                url2 = "https://itrip.us/vacation-rentals/" + state_slug + "/" + city_slug
                html = make_request(url2)
            if not html:
                break
            found = self._parse(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse(self, html, market):
        results = self._extract_ld_items(html, market, "iTrip Vacations", "iTrip Vacations")
        if results:
            return results
        # Look for listing cards with data attributes
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                pp = data.get("props", {}).get("pageProps", {})
                for key in ("listings", "properties", "rentals", "units"):
                    items = pp.get(key, [])
                    if items:
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            l = new_listing()
                            l["property_name"] = item.get("name", item.get("title", ""))
                            l["listing_url"] = item.get("url", "")
                            l["source_platform"] = "iTrip Vacations"
                            l["management_company"] = "iTrip Vacations"
                            l["company_name"] = "iTrip Vacations"
                            l["market"] = market
                            l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                            if l["property_name"]:
                                results.append(l)
                        break
            except Exception as e:
                log.debug("[iTrip] parse error: %s", e)
        if not results:
            names = re.findall(r'<h[23][^>]*class="[^"]*(?:title|name)[^"]*"[^>]*>([^<]{5,80})</h[23]>', html, re.I)
            links = re.findall(r'href="(https://itrip\.us/[^"]+)"', html)
            seen = set()
            for i, name in enumerate(names):
                if name in seen:
                    continue
                seen.add(name)
                l = new_listing()
                l["property_name"] = name.strip()
                l["listing_url"] = links[i] if i < len(links) else ""
                l["source_platform"] = "iTrip Vacations"
                l["management_company"] = "iTrip Vacations"
                l["company_name"] = "iTrip Vacations"
                l["market"] = market
                l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                results.append(l)
        return results


class HomeToGoScraper(OTAScraper):
    """HomeToGo — vacation rental metasearch with JSON-LD + structured data."""
    name = "hometogo"
    delay = 3.0

    def search(self, market, max_pages=3):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        state_name = state_full.replace("-", "-")
        url = "https://www.hometogo.com/" + city_slug + "/"
        html = make_request(url)
        if not html:
            # Try alternate
            url = "https://www.hometogo.com/search/?q=" + urllib.parse.quote(market)
            html = make_request(url)
        if not html:
            return []
        results = self._extract_ld_items(html, market, "HomeToGo")
        if not results:
            results = self._parse_html(html, market)
        return results

    def _parse_html(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                # HomeToGo stores offers in a nested structure
                def find_offers(obj, depth=0):
                    if depth > 8 or not isinstance(obj, (dict, list)):
                        return []
                    found = []
                    if isinstance(obj, list):
                        for item in obj:
                            found.extend(find_offers(item, depth + 1))
                    elif isinstance(obj, dict):
                        name = obj.get("title", obj.get("name", ""))
                        url = obj.get("url", obj.get("detailsUrl", ""))
                        if name and len(name) > 4 and (url or obj.get("id")):
                            l = new_listing()
                            l["property_name"] = name
                            l["listing_url"] = url if url.startswith("http") else "https://www.hometogo.com" + url
                            l["source_platform"] = "HomeToGo"
                            l["market"] = market
                            l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                            l["bedrooms"] = str(obj.get("bedrooms", obj.get("rooms", "")))
                            l["nightly_rate"] = str(obj.get("price", obj.get("nightlyPrice", "")))
                            found.append(l)
                        else:
                            for v in obj.values():
                                found.extend(find_offers(v, depth + 1))
                    return found
                results = find_offers(data)[:100]
            except Exception as e:
                log.debug("[HomeToGo] parse error: %s", e)
        return results


class FlipKeyScraper(OTAScraper):
    """FlipKey (TripAdvisor Vacation Rentals) — JSON-LD ItemList."""
    name = "flipkey"
    delay = 3.0

    def search(self, market, max_pages=5):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        state_slug = state_full.replace("-", "-")
        listings = []
        for page in range(1, max_pages + 1):
            url = ("https://www.flipkey.com/" + city_slug + "-"
                   + state_slug.replace("-", "") + "-vacation-rentals/")
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                # Try TripAdvisor rentals URL
                url = ("https://www.tripadvisor.com/VacationRentals-g"
                       + city_slug + "-Vacation_Rentals.html")
                html = make_request(url)
            if not html:
                break
            found = self._parse(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse(self, html, market):
        results = self._extract_ld_items(html, market, "FlipKey")
        if not results:
            # Look for property cards via data attributes or JSON blobs
            blobs = re.findall(r'window\.__data\s*=\s*(\{.*?\});', html, re.DOTALL)
            for blob in blobs:
                try:
                    data = json.loads(blob)
                    def walk(obj, depth=0):
                        r = []
                        if depth > 6 or not isinstance(obj, (dict, list)):
                            return r
                        if isinstance(obj, list):
                            for x in obj:
                                r.extend(walk(x, depth + 1))
                        elif isinstance(obj, dict):
                            name = obj.get("name", obj.get("title", ""))
                            url = obj.get("url", obj.get("href", ""))
                            if name and len(name) > 4:
                                l = new_listing()
                                l["property_name"] = name
                                l["listing_url"] = url
                                l["source_platform"] = "FlipKey"
                                l["market"] = market
                                l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                                r.append(l)
                            for v in obj.values():
                                r.extend(walk(v, depth + 1))
                        return r
                    results.extend(walk(data))
                except Exception:
                    pass
        return results


class MisterbAndBScraper(OTAScraper):
    """Misterb&b — LGBTQ-friendly STR platform."""
    name = "misterbandb"
    delay = 3.0

    def search(self, market, max_pages=3):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        state_slug = state_full
        url = ("https://misterbandb.com/en/destinations/united-states/"
               + state_slug + "/" + city_slug)
        html = make_request(url)
        if not html:
            return []
        results = self._extract_ld_items(html, market, "Misterb&b")
        if not results:
            nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    items = (data.get("props", {}).get("pageProps", {})
                             .get("listings", data.get("props", {}).get("pageProps", {})
                                  .get("properties", [])))
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        l = new_listing()
                        l["property_name"] = item.get("title", item.get("name", ""))
                        l["listing_url"] = item.get("url", "")
                        l["source_platform"] = "Misterb&b"
                        l["market"] = market
                        l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        if l["property_name"]:
                            results.append(l)
                except Exception as e:
                    log.debug("[Misterb&b] parse error: %s", e)
        return results


# ===========================================================================
# INDUSTRY / ASSOCIATION DIRECTORY SCRAPERS
# ===========================================================================

class VRMADirectoryScraper(OTAScraper):
    """VRMA (Vacation Rental Management Association) — find-a-property-manager directory.
    Gives PM company names, locations, websites — prime contacts for STR outreach."""
    name = "vrma"
    delay = 3.0

    def search(self, market, max_pages=5):
        city, state_abbrev, state_full = parse_market(market)
        # VRMA directory: filter by state
        state_name = state_full.replace("-", " ").title()
        url = ("https://www.vrma.org/find-a-property-manager?"
               + urllib.parse.urlencode({"state": state_name}))
        html = make_request(url, headers={"Referer": "https://www.vrma.org/"})
        if not html:
            return []
        return self._parse(html, market, state_abbrev)

    def _parse(self, html, market, state_abbrev):
        results = []
        # VRMA lists companies — extract name, city, website, phone
        # Try structured data
        ld = self._extract_ld_items(html, market, "VRMA Directory")
        if ld:
            return ld
        # HTML patterns — member cards
        # Pattern: company name in h3/h4, city/state below, website link
        blocks = re.findall(
            r'(?:<div[^>]+class="[^"]*(?:member|company|listing|card)[^"]*"[^>]*>)(.*?)(?:</div>\s*</div>)',
            html, re.DOTALL | re.IGNORECASE
        )
        if not blocks:
            # Try generic name extraction
            names = re.findall(
                r'<(?:h3|h4|strong)[^>]*>\s*([A-Z][^<]{3,60})\s*</(?:h3|h4|strong)>',
                html
            )
            websites = re.findall(r'href="(https?://(?!vrma\.org)[^"]{5,60})"', html)
            phones = re.findall(r'(\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4})', html)
            for i, name in enumerate(names[:100]):
                l = new_listing()
                l["property_name"] = name.strip() + " (PM Company)"
                l["management_company"] = name.strip()
                l["company_name"] = name.strip()
                l["source_platform"] = "VRMA Directory"
                l["website"] = websites[i] if i < len(websites) else ""
                l["contact_phone"] = phones[i] if i < len(phones) else ""
                l["market"] = market
                l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                results.append(l)
        else:
            for block in blocks:
                name_m = re.search(r'<(?:h3|h4|strong)[^>]*>([^<]{3,80})</(?:h3|h4|strong)>', block)
                website_m = re.search(r'href="(https?://[^"]+)"', block)
                phone_m = re.search(r'(\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4})', block)
                if not name_m:
                    continue
                l = new_listing()
                l["property_name"] = name_m.group(1).strip() + " (PM Company)"
                l["management_company"] = name_m.group(1).strip()
                l["company_name"] = name_m.group(1).strip()
                l["source_platform"] = "VRMA Directory"
                l["website"] = website_m.group(1) if website_m else ""
                l["contact_phone"] = phone_m.group(1) if phone_m else ""
                l["market"] = market
                l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                results.append(l)
        return results


class AZTourismScraper(OTAScraper):
    """Arizona tourism / destination lodging directories.
    Scrapes Experience Scottsdale and Visit Arizona lodging member lists."""
    name = "aztourism"
    delay = 2.5

    DIRECTORIES = {
        "scottsdale, az": [
            "https://www.experiencescottsdale.com/hotels/vacation-rentals/",
            "https://www.experiencescottsdale.com/hotels/",
        ],
        "phoenix, az": [
            "https://www.visitphoenix.com/lodging/vacation-rentals/",
            "https://www.visitphoenix.com/lodging/",
        ],
        "sedona, az": [
            "https://visitsedona.com/lodging/vacation-rentals/",
        ],
        "flagstaff, az": [
            "https://www.flagstaffarizona.org/lodging/",
        ],
        "tucson, az": [
            "https://www.visittucson.org/plan-your-visit/lodging/",
        ],
        "tempe, az": [
            "https://www.tempetourism.com/hotels/",
        ],
        "mesa, az": [
            "https://www.visitmesa.com/lodging/",
        ],
    }

    def search(self, market, max_pages=3):
        market_key = market.lower()
        urls = self.DIRECTORIES.get(market_key, [])
        if not urls:
            return []
        results = []
        for url in urls:
            html = make_request(url)
            if not html:
                continue
            found = self._parse(html, market, url)
            results.extend(found)
            self._sleep()
        return results

    def _parse(self, html, market, source_url):
        results = self._extract_ld_items(html, market, "Tourism Directory")
        if results:
            return results
        # Extract business names and links from member directories
        names = re.findall(
            r'<(?:h[2-4]|strong|b)[^>]*>\s*([A-Z][^<]{3,80})\s*</(?:h[2-4]|strong|b)>',
            html
        )
        links = re.findall(r'href="(https?://[^"]{10,80})"', html)
        phones = re.findall(r'(\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4})', html)
        seen = set()
        for i, name in enumerate(names[:100]):
            clean = name.strip()
            if clean in seen or len(clean) < 4:
                continue
            # Filter out navigation noise
            if any(w in clean.lower() for w in ["home", "about", "contact", "menu", "blog", "search"]):
                continue
            seen.add(clean)
            l = new_listing()
            l["property_name"] = clean
            l["management_company"] = clean
            l["company_name"] = clean
            l["listing_url"] = links[i] if i < len(links) else ""
            l["website"] = links[i] if i < len(links) else ""
            l["contact_phone"] = phones[i] if i < len(phones) else ""
            l["source_platform"] = "Tourism Directory"
            l["market"] = market
            l["scraped_at"] = datetime.now(timezone.utc).isoformat()
            results.append(l)
        return results


class NationalPMDirectoryScraper(OTAScraper):
    """NAVRP / AllTheRooms / VRMintel PM directories — company-level contacts."""
    name = "pmdir"
    delay = 3.0

    URLS = [
        ("https://www.alltherooms.com/vacation-rentals/{city_slug}-{state_abbrev}", "AllTheRooms"),
        ("https://www.lodgify.com/vacation-rentals/{city_slug}-{state_full}/", "Lodgify"),
        ("https://hostfully.com/property-managers/?location={city}+{state_abbrev}", "Hostfully"),
    ]

    def search(self, market, max_pages=3):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        results = []
        for url_tpl, platform in self.URLS:
            url = url_tpl.format(
                city=urllib.parse.quote(city),
                city_slug=city_slug,
                state_abbrev=state_abbrev,
                state_full=state_full.replace("-", ""),
            )
            html = make_request(url)
            if not html:
                continue
            found = self._extract_ld_items(html, market, platform)
            results.extend(found)
            self._sleep()
        return results


# ===========================================================================
# CHANNEL PARTNER SCRAPERS (from Channel Partners CSV)
# ===========================================================================

class WhimstayScraper(OTAScraper):
    """Whimstay — last-minute vacation rentals, North America focus."""
    name = "whimstay"
    delay = 2.5

    def search(self, market, max_pages=5):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        listings = []
        for page in range(1, max_pages + 1):
            url = ("https://www.whimstay.com/results?"
                   + urllib.parse.urlencode({"location": city + ", " + state_abbrev.upper(), "page": page}))
            html = make_request(url)
            if not html:
                url2 = "https://www.whimstay.com/" + city_slug + "-" + state_abbrev.lower()
                html = make_request(url2)
            if not html:
                break
            found = self._extract_ld_items(html, market, "Whimstay")
            if not found:
                found = self._parse_next(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse_next(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not nd:
            return results
        try:
            data = json.loads(nd.group(1))
            pp = data.get("props", {}).get("pageProps", {})
            for key in ("listings", "properties", "rentals", "results", "hits"):
                items = pp.get(key, [])
                if not items and isinstance(pp.get("initialData"), dict):
                    items = pp["initialData"].get(key, [])
                for item in (items if isinstance(items, list) else []):
                    if not isinstance(item, dict):
                        continue
                    l = new_listing()
                    l["property_name"] = item.get("title", item.get("name", item.get("headline", "")))
                    slug = item.get("slug", item.get("id", item.get("propertyId", "")))
                    l["listing_url"] = "https://www.whimstay.com/listing/" + str(slug) if slug else ""
                    l["source_platform"] = "Whimstay"
                    l["market"] = market
                    l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    l["bedrooms"] = str(item.get("bedrooms", ""))
                    l["nightly_rate"] = str(item.get("price", item.get("nightlyRate", "")))
                    if l["property_name"]:
                        results.append(l)
                if results:
                    break
        except Exception as e:
            log.debug("[Whimstay] parse error: %s", e)
        return results


class FindRentalsScraper(OTAScraper):
    """FindRentals — US vacation rental marketplace."""
    name = "findrentals"
    delay = 2.5

    def search(self, market, max_pages=5):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        state_slug = state_full.replace("-", "")
        listings = []
        for page in range(1, max_pages + 1):
            url = "https://www.findrentals.com/vacation-rentals/" + city_slug + "/" + state_slug
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                url = "https://www.findrentals.com/search?" + urllib.parse.urlencode({"q": city + " " + state_abbrev.upper()})
                html = make_request(url)
            if not html:
                break
            found = self._extract_ld_items(html, market, "FindRentals")
            if not found:
                found = self._parse_html(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse_html(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                pp = data.get("props", {}).get("pageProps", {})
                for key in ("listings", "properties", "rentals", "results"):
                    for item in pp.get(key, []):
                        if not isinstance(item, dict):
                            continue
                        l = new_listing()
                        l["property_name"] = item.get("name", item.get("title", ""))
                        l["listing_url"] = item.get("url", item.get("link", ""))
                        l["source_platform"] = "FindRentals"
                        l["market"] = market
                        l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        l["bedrooms"] = str(item.get("bedrooms", ""))
                        if l["property_name"]:
                            results.append(l)
                    if results:
                        break
            except Exception as e:
                log.debug("[FindRentals] parse error: %s", e)
        if not results:
            names = re.findall(r'<h[23][^>]*>([^<]{8,80})</h[23]>', html)
            links = re.findall(r'href="(https://www\.findrentals\.com/[^"]+)"', html)
            seen = set()
            for i, name in enumerate(names[:60]):
                name = name.strip()
                if name in seen or len(name) < 5:
                    continue
                seen.add(name)
                l = new_listing()
                l["property_name"] = name
                l["listing_url"] = links[i] if i < len(links) else ""
                l["source_platform"] = "FindRentals"
                l["market"] = market
                l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                results.append(l)
        return results


class BnbFinderScraper(OTAScraper):
    """bnbfinder — direct booking platform for B&Bs and vacation rentals."""
    name = "bnbfinder"
    delay = 2.5

    def search(self, market, max_pages=5):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        state_slug = state_full.replace("-", "-")
        listings = []
        for page in range(1, max_pages + 1):
            url = "https://www.bnbfinder.com/vacation-rentals/" + state_slug + "/" + city_slug
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                break
            found = self._extract_ld_items(html, market, "bnbfinder")
            if not found:
                found = self._parse_html(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse_html(self, html, market):
        results = []
        # bnbfinder often has structured listing cards
        names = re.findall(
            r'(?:itemprop="name"|class="[^"]*(?:listing-name|property-name|inn-name)[^"]*")[^>]*>([^<]{4,80})<',
            html, re.IGNORECASE
        )
        links = re.findall(r'href="(https://www\.bnbfinder\.com/[^"]+)"', html)
        phones = re.findall(r'(\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4})', html)
        emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html)
        seen = set()
        for i, name in enumerate(names[:60]):
            name = name.strip()
            if name in seen or len(name) < 4:
                continue
            seen.add(name)
            l = new_listing()
            l["property_name"] = name
            l["listing_url"] = links[i] if i < len(links) else ""
            l["source_platform"] = "bnbfinder"
            l["contact_phone"] = phones[i] if i < len(phones) else ""
            l["contact_email"] = emails[i] if i < len(emails) else ""
            l["market"] = market
            l["scraped_at"] = datetime.now(timezone.utc).isoformat()
            results.append(l)
        return results


class AmericanSnowbirdScraper(OTAScraper):
    """AmericanSnowbird.com — monthly+ stays in southern US, great for snowbird host contacts."""
    name = "americansnowbird"
    delay = 2.5

    def search(self, market, max_pages=5):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        listings = []
        for page in range(1, max_pages + 1):
            url = "https://www.americansnowbird.com/rentals/" + city_slug + "-" + state_abbrev.lower()
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                url2 = ("https://www.americansnowbird.com/search?"
                        + urllib.parse.urlencode({"location": city + " " + state_abbrev.upper()}))
                html = make_request(url2)
            if not html:
                break
            found = self._extract_ld_items(html, market, "AmericanSnowbird")
            if not found:
                found = self._parse_html(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse_html(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                pp = data.get("props", {}).get("pageProps", {})
                for key in ("listings", "rentals", "properties"):
                    for item in pp.get(key, []):
                        if not isinstance(item, dict):
                            continue
                        l = new_listing()
                        l["property_name"] = item.get("title", item.get("name", ""))
                        l["listing_url"] = item.get("url", "")
                        l["source_platform"] = "AmericanSnowbird"
                        l["market"] = market
                        l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        owner = item.get("owner", item.get("host", {}))
                        if isinstance(owner, dict):
                            l["host_name"] = owner.get("name", "")
                            l["contact_phone"] = owner.get("phone", "")
                            l["contact_email"] = owner.get("email", "")
                        if l["property_name"]:
                            results.append(l)
                    if results:
                        break
            except Exception as e:
                log.debug("[AmericanSnowbird] parse error: %s", e)
        return results


class VacayMyWayScraper(OTAScraper):
    """VacayMyWay — no guest fee vacation rental OTA."""
    name = "vacaymyway"
    delay = 2.5

    def search(self, market, max_pages=5):
        city, state_abbrev, _ = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        listings = []
        for page in range(1, max_pages + 1):
            url = "https://www.vacaymyway.com/vacation-rentals/" + city_slug + "-" + state_abbrev.lower()
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                break
            found = self._extract_ld_items(html, market, "VacayMyWay")
            if not found:
                found = self._parse_html(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse_html(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                pp = data.get("props", {}).get("pageProps", {})
                for key in ("listings", "properties", "results"):
                    for item in pp.get(key, []):
                        if not isinstance(item, dict):
                            continue
                        l = new_listing()
                        l["property_name"] = item.get("name", item.get("title", ""))
                        l["listing_url"] = item.get("url", item.get("listingUrl", ""))
                        l["source_platform"] = "VacayMyWay"
                        l["market"] = market
                        l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        l["bedrooms"] = str(item.get("bedrooms", ""))
                        host = item.get("owner", item.get("host", {}))
                        if isinstance(host, dict):
                            l["host_name"] = host.get("name", "")
                        if l["property_name"]:
                            results.append(l)
                    if results:
                        break
            except Exception as e:
                log.debug("[VacayMyWay] parse error: %s", e)
        return results


class Got2GoScraper(OTAScraper):
    """Got2Go — US-based vacation rental platform."""
    name = "got2go"
    delay = 2.5

    def search(self, market, max_pages=5):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        state_slug = state_full.replace("-", "")
        listings = []
        for page in range(1, max_pages + 1):
            url = "https://www.got2go.us/vacation-rentals/" + city_slug + "-" + state_slug
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                url2 = "https://www.got2go.us/rentals/" + city_slug + "-" + state_abbrev.lower()
                html = make_request(url2)
            if not html:
                break
            found = self._extract_ld_items(html, market, "Got2Go")
            if not found:
                found = self._parse_html(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse_html(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                pp = data.get("props", {}).get("pageProps", {})
                for key in ("listings", "properties", "rentals", "results"):
                    for item in pp.get(key, []):
                        if not isinstance(item, dict):
                            continue
                        l = new_listing()
                        l["property_name"] = item.get("name", item.get("title", ""))
                        l["listing_url"] = item.get("url", "")
                        l["source_platform"] = "Got2Go"
                        l["market"] = market
                        l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        if l["property_name"]:
                            results.append(l)
                    if results:
                        break
            except Exception as e:
                log.debug("[Got2Go] parse error: %s", e)
        return results


class CuddlyNestScraper(OTAScraper):
    """CuddlyNest — global vacation rental OTA."""
    name = "cuddlynest"
    delay = 3.0

    def search(self, market, max_pages=5):
        city, state_abbrev, _ = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        listings = []
        for page in range(1, max_pages + 1):
            url = "https://www.cuddlynest.com/vacation-rentals/" + city_slug + "-" + state_abbrev.lower()
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                break
            found = self._extract_ld_items(html, market, "CuddlyNest")
            if not found:
                found = self._parse_html(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse_html(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                pp = data.get("props", {}).get("pageProps", {})
                for key in ("listings", "properties", "rentals", "results", "data"):
                    items = pp.get(key, [])
                    if isinstance(items, dict):
                        items = items.get("listings", items.get("items", []))
                    for item in (items if isinstance(items, list) else []):
                        if not isinstance(item, dict):
                            continue
                        l = new_listing()
                        l["property_name"] = item.get("title", item.get("name", ""))
                        slug = item.get("slug", item.get("id", ""))
                        l["listing_url"] = "https://www.cuddlynest.com/p/" + str(slug) if slug else ""
                        l["source_platform"] = "CuddlyNest"
                        l["market"] = market
                        l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        l["bedrooms"] = str(item.get("bedrooms", ""))
                        l["nightly_rate"] = str(item.get("price", item.get("pricePerNight", "")))
                        if l["property_name"]:
                            results.append(l)
                    if results:
                        break
            except Exception as e:
                log.debug("[CuddlyNest] parse error: %s", e)
        return results


class VacationRenterScraper(OTAScraper):
    """VacationRenter — best-of vacation rentals meta search."""
    name = "vacationrenter"
    delay = 2.5

    def search(self, market, max_pages=5):
        city, state_abbrev, _ = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        listings = []
        for page in range(1, max_pages + 1):
            url = "https://www.vacationrenter.com/vacation-rentals/" + city_slug + "-" + state_abbrev.lower() + ".html"
            if page > 1:
                url = url.replace(".html", "?page=" + str(page) + ".html")
            html = make_request(url)
            if not html:
                break
            found = self._extract_ld_items(html, market, "VacationRenter")
            if not found:
                found = self._parse_html(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse_html(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                pp = data.get("props", {}).get("pageProps", {})
                for key in ("listings", "properties", "rentals", "results"):
                    for item in pp.get(key, []):
                        if not isinstance(item, dict):
                            continue
                        l = new_listing()
                        l["property_name"] = item.get("name", item.get("title", ""))
                        l["listing_url"] = item.get("url", item.get("link", ""))
                        l["source_platform"] = "VacationRenter"
                        l["market"] = market
                        l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        if l["property_name"]:
                            results.append(l)
                    if results:
                        break
            except Exception as e:
                log.debug("[VacationRenter] parse error: %s", e)
        return results


class MarriottVillasScraper(OTAScraper):
    """Homes & Villas by Marriott Bonvoy — luxury vacation rental service."""
    name = "marriottvillas"
    delay = 3.0

    def search(self, market, max_pages=3):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        state_slug = state_full.replace("-", "-")
        listings = []
        for page in range(1, max_pages + 1):
            url = ("https://homes-and-villas.marriott.com/en/vacation-rentals/united-states/"
                   + state_slug + "/" + city_slug)
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url, headers={"Referer": "https://homes-and-villas.marriott.com/"})
            if not html:
                break
            found = self._extract_ld_items(html, market, "Marriott Villas", "Homes & Villas by Marriott")
            if not found:
                found = self._parse_html(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse_html(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                pp = data.get("props", {}).get("pageProps", {})
                for key in ("listings", "properties", "homes", "villas"):
                    for item in pp.get(key, []):
                        if not isinstance(item, dict):
                            continue
                        l = new_listing()
                        l["property_name"] = item.get("name", item.get("title", ""))
                        l["listing_url"] = item.get("url", "")
                        l["source_platform"] = "Marriott Villas"
                        l["management_company"] = "Homes & Villas by Marriott"
                        l["company_name"] = "Homes & Villas by Marriott"
                        l["market"] = market
                        l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        l["bedrooms"] = str(item.get("bedrooms", ""))
                        if l["property_name"]:
                            results.append(l)
                    if results:
                        break
            except Exception as e:
                log.debug("[MarriottVillas] parse error: %s", e)
        return results


class PlumGuideScraper(OTAScraper):
    """Plum Guide — curated luxury vacation rental platform."""
    name = "plumguide"
    delay = 3.0

    def search(self, market, max_pages=5):
        city, state_abbrev, state_full = parse_market(market)
        city_slug = city.lower().replace(" ", "-")
        state_slug = state_full.replace("-", "-")
        listings = []
        for page in range(1, max_pages + 1):
            url = "https://www.plumguide.com/homes/usa/" + state_slug + "/" + city_slug
            if page > 1:
                url += "?page=" + str(page)
            html = make_request(url)
            if not html:
                break
            found = self._extract_ld_items(html, market, "Plum Guide")
            if not found:
                found = self._parse_html(html, market)
            if not found:
                break
            listings.extend(found)
            self._sleep()
        return listings

    def _parse_html(self, html, market):
        results = []
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd:
            try:
                data = json.loads(nd.group(1))
                pp = data.get("props", {}).get("pageProps", {})
                for key in ("homes", "listings", "properties", "results"):
                    items = pp.get(key, [])
                    if isinstance(items, dict):
                        items = list(items.values()) if items else []
                    for item in (items if isinstance(items, list) else []):
                        if not isinstance(item, dict):
                            continue
                        l = new_listing()
                        l["property_name"] = item.get("name", item.get("title", item.get("headline", "")))
                        slug = item.get("slug", item.get("id", ""))
                        l["listing_url"] = "https://www.plumguide.com/homes/" + str(slug) if slug else ""
                        l["source_platform"] = "Plum Guide"
                        l["market"] = market
                        l["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        l["bedrooms"] = str(item.get("bedrooms", item.get("bedroom_count", "")))
                        if l["property_name"]:
                            results.append(l)
                    if results:
                        break
            except Exception as e:
                log.debug("[PlumGuide] parse error: %s", e)
        return results


# ===========================================================================
# SCRAPER REGISTRY
# ===========================================================================
SCRAPERS = {
    # Original proven
    "houfy":            HoufyScraper,
    "glampinghub":      GlampingHubScraper,
    "hipcamp":          HipcampScraper,
    "vacasa":           VacasaScraper,
    "turnkey":          TurnkeyScraper,
    "evolve":           EvolveScraper,
    # Channel partners (from CSV)
    "whimstay":         WhimstayScraper,
    "findrentals":      FindRentalsScraper,
    "bnbfinder":        BnbFinderScraper,
    "americansnowbird": AmericanSnowbirdScraper,
    "vacaymyway":       VacayMyWayScraper,
    "got2go":           Got2GoScraper,
    "cuddlynest":       CuddlyNestScraper,
    "vacationrenter":   VacationRenterScraper,
    "marriottvillas":   MarriottVillasScraper,
    "plumguide":        PlumGuideScraper,
    # Previously added
    "furnishedfinder":  FurnishedFinderScraper,
    "redawning":        RedAwningScraper,
    "itrip":            iTripScraper,
    "hometogo":         HomeToGoScraper,
    "flipkey":          FlipKeyScraper,
    "misterbandb":      MisterbAndBScraper,
    # Directories / registries
    "vrma":             VRMADirectoryScraper,
    "aztourism":        AZTourismScraper,
    "pmdir":            NationalPMDirectoryScraper,
}

# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------
def deduplicate(listings):
    seen = set()
    out = []
    for l in listings:
        key = (
            l.get("property_name", "").lower().strip(),
            l.get("listing_url", "").lower().strip(),
            l.get("source_platform", "").lower(),
        )
        if key[0] and key not in seen:
            seen.add(key)
            out.append(l)
    removed = len(listings) - len(out)
    if removed:
        log.info("Removed %d duplicates", removed)
    return out


def enrich_names(listings):
    for l in listings:
        host = l.get("host_name", "")
        if host and not l.get("first_name"):
            f, la = split_name(host)
            l["first_name"] = f
            l["last_name"] = la
        if not l.get("company_name"):
            l["company_name"] = l.get("management_company", "") or host
    return listings


def write_csv(rows, filepath):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    log.info("Wrote %d rows -> %s", len(rows), filepath)


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------
def scrape_one(args):
    """Worker function: (scraper_name, market, max_pages) -> list."""
    scraper_name, market, max_pages = args
    cls = SCRAPERS[scraper_name]
    try:
        scraper = cls()
        results = scraper.search(market, max_pages)
        log.info("  [%s / %s] %d listings", scraper_name, market, len(results))
        return results
    except Exception as e:
        log.warning("  [%s / %s] FAILED: %s", scraper_name, market, e)
        return []


def run_mega_scrape(markets, sources, max_pages=5, workers=6):
    tasks = [(src, mkt, max_pages) for mkt in markets for src in sources]
    log.info("Total tasks: %d (%d sources × %d markets)", len(tasks), len(sources), len(markets))
    all_listings = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(scrape_one, t): t for t in tasks}
        for fut in as_completed(futures):
            results = fut.result()
            all_listings.extend(results)
    return all_listings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="STR Mega Scraper — 15 sources × 50 markets = 5000+ listings"
    )
    parser.add_argument("--markets", default="",
        help="Comma-separated markets (default: all 50 top STR markets)")
    parser.add_argument("--sources", default=",".join(sorted(SCRAPERS.keys())),
        help="Comma-separated sources (default: all)")
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--output", default="str_mega_contacts.csv")
    parser.add_argument("--no-dedup", action="store_true")
    args = parser.parse_args()

    markets = [m.strip() for m in args.markets.split(",")] if args.markets else TOP_STR_MARKETS
    sources = [s.strip() for s in args.sources.split(",") if s.strip() in SCRAPERS]
    invalid = [s.strip() for s in args.sources.split(",") if s.strip() and s.strip() not in SCRAPERS]
    if invalid:
        log.warning("Unknown sources ignored: %s", invalid)

    log.info("=" * 65)
    log.info("STR MEGA SCRAPER")
    log.info("=" * 65)
    log.info("Markets:   %d", len(markets))
    log.info("Sources:   %s", ", ".join(sources))
    log.info("Max pages: %d", args.max_pages)
    log.info("Workers:   %d", args.workers)
    log.info("Output:    %s", args.output)
    log.info("=" * 65)

    all_listings = run_mega_scrape(markets, sources, args.max_pages, args.workers)

    if not args.no_dedup:
        all_listings = deduplicate(all_listings)

    all_listings = enrich_names(all_listings)
    write_csv(all_listings, args.output)

    # Summary
    by_source = {}
    by_market = {}
    for l in all_listings:
        src = l.get("source_platform", "Unknown")
        mkt = l.get("market", "Unknown")
        by_source[src] = by_source.get(src, 0) + 1
        by_market[mkt] = by_market.get(mkt, 0) + 1

    log.info("=" * 65)
    log.info("SUMMARY — %d total unique listings", len(all_listings))
    log.info("=" * 65)
    log.info("By source:")
    for src, ct in sorted(by_source.items(), key=lambda x: -x[1]):
        log.info("  %-25s %d", src, ct)
    log.info("By market (top 15):")
    for mkt, ct in sorted(by_market.items(), key=lambda x: -x[1])[:15]:
        log.info("  %-30s %d", mkt, ct)
    with_host = sum(1 for r in all_listings if r.get("host_name"))
    with_email = sum(1 for r in all_listings if r.get("contact_email"))
    with_phone = sum(1 for r in all_listings if r.get("contact_phone"))
    log.info("With host name: %d", with_host)
    log.info("With email:     %d", with_email)
    log.info("With phone:     %d", with_phone)
    log.info("Output saved:   %s", args.output)
    log.info("")
    log.info("NEXT STEPS:")
    log.info("  1. Upload %s to Clay.com", args.output)
    log.info("     - Find Work Email (host_name + company_name columns)")
    log.info("     - Find Phone Number")
    log.info("     - Enrich Person -> LinkedIn")
    log.info("  2. Export enriched list -> Instantly.ai")
    log.info("     - Map: first_name, last_name, company_name, contact_email")


if __name__ == "__main__":
    main()
