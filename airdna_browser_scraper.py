#!/usr/bin/env python3
"""
AirDNA Browser Scraper — logs in via Selenium, searches markets,
extracts STR property data matching filters, pushes to Instantly.

Filters:
  - 4-6 bedrooms
  - Annual revenue > $40,000 USD  OR  listed in 2026
  - Outbound score >= 40
"""

import os, json, time, logging, base64, requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from openai import OpenAI

load_dotenv("/root/str-stack/.env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Credentials ──────────────────────────────────────────────────────────────
AIRDNA_EMAIL      = os.environ["AIRDNA_EMAIL"]
AIRDNA_PASSWORD   = os.environ["AIRDNA_PASSWORD"]
INSTANTLY_KEY_B64 = os.environ["INSTANTLY_API_KEY_V2"]
OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]

CAMPAIGNS = {
    1: os.environ.get("INSTANTLY_CAMPAIGN_SIDE_HUSTLE", "72d96a63-ab0c-4a93-a181-5d4a96497446"),
    2: os.environ.get("INSTANTLY_CAMPAIGN_LOCAL_PM", ""),
    3: os.environ.get("INSTANTLY_CAMPAIGN_MULTI_UNIT", ""),
    4: os.environ.get("INSTANTLY_CAMPAIGN_BOUTIQUE_HOTEL", ""),
}

# ── Filters ──────────────────────────────────────────────────────────────────
MIN_BEDROOMS   = 4
MAX_BEDROOMS   = 6
MIN_REVENUE    = 40000
NEW_YEAR       = 2026
CAD_TO_USD     = 0.74
DRY_RUN        = os.environ.get("DRY_RUN", "false").lower() == "true"

# ── Markets ──────────────────────────────────────────────────────────────────
MARKETS = [
    # Ontario
    {"q": "Muskoka, Ontario",             "currency": "CAD"},
    {"q": "Prince Edward County, Ontario","currency": "CAD"},
    {"q": "Blue Mountains, Ontario",      "currency": "CAD"},
    {"q": "Kawartha Lakes, Ontario",      "currency": "CAD"},
    {"q": "Haliburton, Ontario",          "currency": "CAD"},
    {"q": "Parry Sound, Ontario",         "currency": "CAD"},
    {"q": "Niagara-on-the-Lake, Ontario", "currency": "CAD"},
    {"q": "Wasaga Beach, Ontario",        "currency": "CAD"},
    {"q": "Collingwood, Ontario",         "currency": "CAD"},
    {"q": "Huntsville, Ontario",          "currency": "CAD"},
    # Texas
    {"q": "Fredericksburg, Texas",        "currency": "USD"},
    {"q": "Wimberley, Texas",             "currency": "USD"},
    {"q": "South Padre Island, Texas",    "currency": "USD"},
    {"q": "New Braunfels, Texas",         "currency": "USD"},
    {"q": "Galveston, Texas",             "currency": "USD"},
    {"q": "Port Aransas, Texas",          "currency": "USD"},
    {"q": "Marble Falls, Texas",          "currency": "USD"},
    # Arizona
    {"q": "Sedona, Arizona",              "currency": "USD"},
    {"q": "Scottsdale, Arizona",          "currency": "USD"},
    {"q": "Flagstaff, Arizona",           "currency": "USD"},
    {"q": "Prescott, Arizona",            "currency": "USD"},
    # Colorado
    {"q": "Breckenridge, Colorado",       "currency": "USD"},
    {"q": "Telluride, Colorado",          "currency": "USD"},
    {"q": "Steamboat Springs, Colorado",  "currency": "USD"},
    {"q": "Estes Park, Colorado",         "currency": "USD"},
    {"q": "Aspen, Colorado",              "currency": "USD"},
    {"q": "Vail, Colorado",               "currency": "USD"},
    {"q": "Durango, Colorado",            "currency": "USD"},
    {"q": "Crested Butte, Colorado",      "currency": "USD"},
]

# ── ICP Prompts ──────────────────────────────────────────────────────────────
ICP_PROMPT = """Classify this STR property into one ICP type:
1 = Side-Hustle Host (1-2 units)
2 = Local Property Manager (3-20 units)
3 = Multi-Unit Pro (6-50+ units)
4 = Boutique Hotel (<100 rooms)
5 = Unknown

Data: {data}
Return ONLY valid JSON: {{"icp_type": <1-5>, "confidence": <0-100>}}"""

SCORE_PROMPT = """Score this STR lead 0-100 for cold outbound email campaigns.
Higher score if: revenue > $40k, 4-6 bedrooms, no big PM firm, 2026 listing, strong market.
Lower score if: large chain/PM, outside North America, low revenue.

Data: {data}
Return ONLY valid JSON: {{"score": <0-100>, "reason": "<one line>"}}"""


def make_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--log-level=3")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def login(driver: webdriver.Chrome) -> bool:
    """Log into AirDNA — handles the OAuth modal flow."""
    logger.info("Logging into AirDNA...")
    # Load a market page which triggers the login modal
    driver.get("https://app.airdna.co/data/market?location=Sedona,AZ")
    wait = WebDriverWait(driver, 25)
    time.sleep(4)

    try:
        # Screenshot current state
        driver.save_screenshot("/root/str-stack/airdna_step1.png")

        # Step 1: Click "Already have an account? Log In" link in the modal
        login_link = wait.until(EC.element_to_be_clickable((By.XPATH,
            "//*[contains(text(),'Log In') or contains(text(),'Log in') or contains(text(),'Sign in') or contains(text(),'login')]"
        )))
        logger.info(f"  Found login link: '{login_link.text}' — clicking")
        login_link.click()
        time.sleep(3)
        driver.save_screenshot("/root/str-stack/airdna_step2.png")

        # Step 2: Fill email — use actual send_keys so React state updates properly
        email_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
            "input[type='email'], input[name='email'], input[placeholder*='email' i], input[id*='email' i]"
        )))
        email_field.click()
        email_field.clear()
        email_field.send_keys(AIRDNA_EMAIL)
        time.sleep(0.5)

        # Step 3: Fill password with send_keys
        pw_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
            "input[type='password'], input[name='password'], input[id*='password' i]"
        )))
        pw_field.click()
        pw_field.clear()
        pw_field.send_keys(AIRDNA_PASSWORD)
        time.sleep(1)

        # Step 4: Submit — wait for button to be enabled then click
        driver.save_screenshot("/root/str-stack/airdna_prefill.png")
        # Find any button in the modal
        all_btns = driver.find_elements(By.TAG_NAME, "button")
        logger.info(f"  Buttons found: {[b.text for b in all_btns]}")
        submit = None
        for btn in all_btns:
            txt = btn.text.lower()
            if any(w in txt for w in ("log in", "sign in", "submit", "continue", "login")):
                submit = btn
                break
        if not submit and all_btns:
            submit = all_btns[-1]  # last button is usually submit
        if submit:
            driver.execute_script("arguments[0].removeAttribute('disabled');", submit)
            driver.execute_script("arguments[0].click();", submit)
        else:
            # Last resort: press Enter
            from selenium.webdriver.common.keys import Keys
            pw_field.send_keys(Keys.RETURN)
        time.sleep(6)
        driver.save_screenshot("/root/str-stack/airdna_step3.png")

        # Success check — should be back on app.airdna.co
        if "auth.airdna.co" not in driver.current_url and "login" not in driver.current_url.lower():
            logger.info(f"Login successful — at {driver.current_url}")
            return True

        logger.error(f"Login may have failed — URL: {driver.current_url}")
        return False

    except Exception as e:
        logger.error(f"Login error: {e}")
        driver.save_screenshot("/root/str-stack/airdna_login_debug.png")
        return False


def intercept_api_data(driver: webdriver.Chrome, market_q: str) -> list:
    """
    Navigate to AirDNA market explorer for a location and extract
    property data from the page or intercepted network requests.
    """
    props = []
    wait = WebDriverWait(driver, 30)

    # Enable CDP network interception to capture API responses
    driver.execute_cdp_cmd("Network.enable", {})

    # Navigate to the market explorer
    search_url = f"https://app.airdna.co/data/market?location={market_q.replace(' ', '+')}"
    logger.info(f"  Navigating to: {search_url}")
    driver.get(search_url)
    time.sleep(4)

    # Try to extract data via JavaScript from the page's React/Redux store
    try:
        raw = driver.execute_script("""
            // Try window.__NEXT_DATA__ (Next.js)
            if (window.__NEXT_DATA__) return JSON.stringify(window.__NEXT_DATA__);
            // Try Redux store
            if (window.__REDUX_STATE__) return JSON.stringify(window.__REDUX_STATE__);
            // Try React fiber
            const root = document.getElementById('__next') || document.getElementById('root');
            if (root && root._reactRootContainer) {
                try {
                    return JSON.stringify(root._reactRootContainer._internalRoot.current.memoizedState);
                } catch(e) {}
            }
            return null;
        """)
        if raw:
            data = json.loads(raw)
            props = extract_from_page_data(data, market_q)
            logger.info(f"  Extracted {len(props)} properties from page data")
    except Exception as e:
        logger.warning(f"  Page data extraction failed: {e}")

    # Fallback: scrape visible listing cards from DOM
    if not props:
        props = scrape_listing_cards(driver, market_q)

    return props


def scrape_listing_cards(driver: webdriver.Chrome, location: str) -> list:
    """Scrape visible property cards from AirDNA market explorer DOM."""
    props = []
    try:
        time.sleep(3)
        # Common AirDNA card selectors
        cards = driver.find_elements(By.CSS_SELECTOR,
            "[class*='rental-card'], [class*='property-card'], [class*='listing-item'], [data-testid*='rental']"
        )
        logger.info(f"  Found {len(cards)} listing cards in DOM")

        for card in cards[:50]:
            try:
                text = card.text
                prop = parse_card_text(text, location)
                if prop:
                    props.append(prop)
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"  Card scraping failed: {e}")
    return props


def parse_card_text(text: str, location: str) -> dict | None:
    """Parse raw card text into a property dict."""
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return None

    prop = {"location": location, "source": "AirDNA"}
    prop["property_name"] = lines[0] if lines else ""

    for line in lines:
        ll = line.lower()
        if "bed" in ll:
            try:
                prop["bedrooms"] = int(''.join(filter(str.isdigit, line.split()[0])))
            except Exception:
                pass
        if "$" in line or "revenue" in ll:
            try:
                digits = ''.join(filter(str.isdigit, line.replace(",", "")))
                if digits:
                    prop["annual_revenue"] = int(digits)
            except Exception:
                pass

    return prop if prop.get("property_name") else None


def extract_from_page_data(data: dict, location: str) -> list:
    """Recursively search page data JSON for rental listings."""
    props = []

    def walk(obj, depth=0):
        if depth > 8:
            return
        if isinstance(obj, dict):
            if any(k in obj for k in ("bedrooms", "annual_revenue", "listing_id", "rentalId")):
                props.append({**obj, "location": location, "source": "AirDNA"})
                return
            for v in obj.values():
                walk(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj[:200]:
                walk(item, depth + 1)

    walk(data)
    return props


def passes_filter(prop: dict, currency: str) -> bool:
    revenue = prop.get("annual_revenue", prop.get("revenue", 0)) or 0
    if currency == "CAD":
        revenue = revenue * CAD_TO_USD
    prop["annual_revenue_usd"] = revenue

    beds = prop.get("bedrooms", 0) or 0
    year = prop.get("listed_year", prop.get("year_listed", 0)) or 0

    in_bedroom_range = MIN_BEDROOMS <= int(beds) <= MAX_BEDROOMS if beds else False
    high_revenue     = revenue >= MIN_REVENUE
    new_listing      = int(year) >= NEW_YEAR if year else False

    return in_bedroom_range and (high_revenue or new_listing)


def ai_classify(prop: dict) -> tuple[dict, dict]:
    client = OpenAI(api_key=OPENAI_API_KEY)
    summary = json.dumps({
        k: prop.get(k) for k in
        ("property_name", "bedrooms", "annual_revenue_usd", "listed_year",
         "location", "num_listings", "host_name")
        if prop.get(k)
    }, indent=2)

    icp = {"icp_type": 1, "confidence": 50}
    score = {"score": 50, "reason": "default"}

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": ICP_PROMPT.format(data=summary)}],
            temperature=0, max_tokens=80,
        )
        icp = json.loads(r.choices[0].message.content)
    except Exception as e:
        logger.warning(f"ICP classify error: {e}")

    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": SCORE_PROMPT.format(data=summary)}],
            temperature=0, max_tokens=100,
        )
        score = json.loads(r.choices[0].message.content)
    except Exception as e:
        logger.warning(f"Score error: {e}")

    return icp, score


def build_lead(prop: dict, icp: dict, score: dict) -> dict:
    name  = prop.get("host_name", prop.get("owner_name", "")).strip()
    parts = name.split(" ", 1)
    return {
        "email":        prop.get("host_email", prop.get("email", "")).strip(),
        "first_name":   parts[0] if parts else "",
        "last_name":    parts[1] if len(parts) > 1 else "",
        "company_name": prop.get("property_name", ""),
        "website":      prop.get("listing_url", prop.get("url", "")),
        "phone":        prop.get("host_phone", ""),
        "custom_variables": {
            "bedrooms":       str(prop.get("bedrooms", "")),
            "annual_revenue": f"${prop.get('annual_revenue_usd', 0):,.0f} USD",
            "location":       prop.get("location", ""),
            "listed_year":    str(prop.get("listed_year", "")),
            "icp_type":       str(icp.get("icp_type", "")),
            "outbound_score": str(score.get("score", "")),
            "score_reason":   score.get("reason", ""),
            "source":         "AirDNA",
        },
    }


def push_to_instantly(leads: list, campaign_id: str) -> tuple[int, int]:
    if not campaign_id or DRY_RUN:
        action = "DRY RUN — would push" if DRY_RUN else "No campaign ID"
        logger.info(f"  {action} {len(leads)} leads")
        return len(leads) if DRY_RUN else 0, 0

    try:
        api_key = base64.b64decode(INSTANTLY_KEY_B64).decode("utf-8")
    except Exception:
        api_key = INSTANTLY_KEY_B64

    ok = fail = 0
    for i in range(0, len(leads), 100):
        batch   = leads[i:i + 100]
        payload = {"campaign_id": campaign_id, "leads": batch,
                   "skip_if_in_workspace": True, "skip_if_in_campaign": True}
        try:
            resp = requests.post(
                "https://api.instantly.ai/api/v2/leads",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload, timeout=30,
            )
            if resp.status_code in (200, 201):
                ok += len(batch)
            else:
                fail += len(batch)
                logger.error(f"  Instantly {resp.status_code}: {resp.text[:150]}")
        except Exception as e:
            fail += len(batch)
            logger.error(f"  Push failed: {e}")
        time.sleep(1)
    return ok, fail


def run():
    logger.info(f"{'='*50}")
    logger.info(f"AirDNA Browser Scraper — {'DRY RUN' if DRY_RUN else 'LIVE'}")
    logger.info(f"Markets: {len(MARKETS)} | Filters: {MIN_BEDROOMS}-{MAX_BEDROOMS}bd, >${MIN_REVENUE:,}/yr or >={NEW_YEAR}")
    logger.info(f"{'='*50}")

    driver = make_driver()
    try:
        if not login(driver):
            logger.error("Login failed — check credentials or screenshot at /root/str-stack/airdna_login_debug.png")
            return

        leads_by_icp: dict[int, list] = {1: [], 2: [], 3: [], 4: []}
        total_scanned = total_qualified = 0

        # DRY RUN: only test first 2 markets
        markets_to_run = MARKETS[:2] if DRY_RUN else MARKETS

        for market in markets_to_run:
            logger.info(f"\n── {market['q']} ──")
            props = intercept_api_data(driver, market["q"])
            total_scanned += len(props)

            qualified = [p for p in props if passes_filter(p, market["currency"])]
            total_qualified += len(qualified)
            logger.info(f"  {len(props)} found → {len(qualified)} pass filters")

            for prop in qualified:
                icp, score = ai_classify(prop)
                s = score.get("score", 0)
                t = icp.get("icp_type", 5)
                logger.info(f"  [{s:>3}/100] ICP-{t} | {prop.get('property_name','?')} | ${prop.get('annual_revenue_usd',0):,.0f}/yr")

                if s >= 40 and prop.get("host_email") or prop.get("email"):
                    lead = build_lead(prop, icp, score)
                    if lead.get("email") and t in leads_by_icp:
                        leads_by_icp[t].append(lead)

            time.sleep(2)

    finally:
        driver.quit()

    # Push to Instantly
    total_pushed = total_failed = 0
    logger.info("\n── Pushing to Instantly ──")
    for icp_type, leads in leads_by_icp.items():
        if not leads:
            continue
        cid = CAMPAIGNS.get(icp_type, "")
        logger.info(f"  ICP-{icp_type}: {len(leads)} leads → campaign {cid or 'NOT SET'}")
        ok, fail = push_to_instantly(leads, cid)
        total_pushed += ok
        total_failed += fail

    logger.info(f"""
{'='*50}
  Pipeline {'DRY RUN ' if DRY_RUN else ''}Complete
  Markets scanned:     {len(markets_to_run)}
  Properties found:    {total_scanned}
  Passed filters:      {total_qualified}
  Pushed to Instantly: {total_pushed}
  Failed:              {total_failed}
{'='*50}""")


if __name__ == "__main__":
    run()
