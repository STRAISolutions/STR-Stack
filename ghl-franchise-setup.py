#!/usr/bin/env python3
"""
STR Solutions — GHL Franchise Page Setup Script
Deploys to: /root/str-stack/ghl-franchise-setup.py on 134.209.11.87

Creates all required GHL resources for the franchise discovery funnel:
  1. Custom fields (11 dropdown fields)
  2. Calendars (ICP1 15min + ICP5 30min)
  3. Inbound webhook for workflow trigger
  4. Tags
  5. Prints CONFIG block for franchise-page.html

Usage:
  python3 ghl-franchise-setup.py           # dry-run (shows what would be created)
  python3 ghl-franchise-setup.py --execute # actually create resources
"""

import argparse
import json
import sys
import time
from datetime import datetime

import requests

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

API_BASE = "https://services.leadconnectorhq.com"
API_VERSION = "2021-07-28"

# Master subaccount
LOCATION_ID = "1OOZ4AKIgxO8QKKMnIcK"
API_KEY = "pit-8e3c20cd-0d7f-43a3-be9d-c087e925b3e7"

# Mike Adams user ID (will be looked up if not set)
ASSIGNED_USER_ID = None

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Version": API_VERSION,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOM FIELDS TO CREATE
# ═══════════════════════════════════════════════════════════════════════════════

CUSTOM_FIELDS = [
    {
        "name": "ICP Interest",
        "dataType": "TEXT",
        "fieldKey": "icp_interest",
        "placeholder": "icp1, icp5, or both",
    },
    {
        "name": "Property Count",
        "dataType": "TEXT",
        "fieldKey": "property_count",
        "placeholder": "1, 2-4, 5-10, 11+",
    },
    {
        "name": "Listing Platforms",
        "dataType": "TEXT",
        "fieldKey": "listing_platforms",
        "placeholder": "airbnb, vrbo, both, direct+otas, other",
    },
    {
        "name": "Owner Challenge",
        "dataType": "TEXT",
        "fieldKey": "owner_challenge",
        "placeholder": "guest-communication, pricing, cleaning, etc.",
    },
    {
        "name": "ICP5 Liquid Capital",
        "dataType": "TEXT",
        "fieldKey": "icp5_liquid_capital",
        "placeholder": "$250K+, $150K-$249K, etc.",
    },
    {
        "name": "ICP5 Funding Source",
        "dataType": "TEXT",
        "fieldKey": "icp5_funding_source",
        "placeholder": "cash, sba, heloc, visa, researching",
    },
    {
        "name": "ICP5 Timeline",
        "dataType": "TEXT",
        "fieldKey": "icp5_timeline",
        "placeholder": "30-days, 1-3-months, etc.",
    },
    {
        "name": "ICP5 Background",
        "dataType": "TEXT",
        "fieldKey": "icp5_background",
        "placeholder": "tech, owner, finance, realestate, sales, other",
    },
    {
        "name": "ICP5 Biz Experience",
        "dataType": "TEXT",
        "fieldKey": "icp5_biz_experience",
        "placeholder": "owner-250k, owner-small, pl-manager, none",
    },
    {
        "name": "ICP5 Target Market",
        "dataType": "TEXT",
        "fieldKey": "icp5_target_market",
        "placeholder": "southeast, texas-sw, mountain, etc.",
    },
    {
        "name": "ICP5 Motivation",
        "dataType": "TEXT",
        "fieldKey": "icp5_motivation",
        "placeholder": "asset, income, diversify, visa, curious",
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# CALENDARS TO CREATE
# ═══════════════════════════════════════════════════════════════════════════════

CALENDARS = [
    {
        "name": "Introductory Meeting — STR",
        "description": "ICP1 property owners — 15 minute intro call",
        "slug": "introductory-meeting-str",
        "slotDuration": 15,
        "slotInterval": 15,
        "slotBuffer": 10,
        "calendarType": "round_robin_optimize",
        "appoinmentPerSlot": 1,
        "openHours": [
            # Tuesday 12:00 PM ET
            {"daysOfTheWeek": [2], "hours": [{"openHour": 12, "openMinute": 0, "closeHour": 13, "closeMinute": 0}]},
            # Thursday 7:00 PM ET
            {"daysOfTheWeek": [4], "hours": [{"openHour": 19, "openMinute": 0, "closeHour": 20, "closeMinute": 0}]},
            # Saturday 11:00 AM ET
            {"daysOfTheWeek": [6], "hours": [{"openHour": 11, "openMinute": 0, "closeHour": 12, "closeMinute": 0}]},
        ],
        "timezone": "America/New_York",
    },
    {
        "name": "Franchise Discovery Call",
        "description": "ICP5 franchise candidates — 30 minute discovery call",
        "slug": "franchise-discovery-call",
        "slotDuration": 30,
        "slotInterval": 30,
        "slotBuffer": 15,
        "calendarType": "round_robin_optimize",
        "appoinmentPerSlot": 1,
        "openHours": [
            # Monday 12:00 PM ET
            {"daysOfTheWeek": [1], "hours": [{"openHour": 12, "openMinute": 0, "closeHour": 13, "closeMinute": 0}]},
            # Wednesday 7:00 PM ET
            {"daysOfTheWeek": [3], "hours": [{"openHour": 19, "openMinute": 0, "closeHour": 20, "closeMinute": 0}]},
            # Friday 3:00 PM ET
            {"daysOfTheWeek": [5], "hours": [{"openHour": 15, "openMinute": 0, "closeHour": 16, "closeMinute": 0}]},
        ],
        "timezone": "America/New_York",
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# TAGS TO CREATE
# ═══════════════════════════════════════════════════════════════════════════════

TAGS = [
    "discovery-form",
    "website-lead",
    "ICP1",
    "ICP5",
    "str-owner",
    "franchise-candidate",
    "dual-interest",
    "ICP5-fast-track",
    "ICP5-qualified",
    "ICP5-nurture",
    "ICP5-not-qualified",
    "capital-tier-A",
    "capital-tier-B",
    "capital-tier-C",
    "capital-tier-D",
    "timeline-hot",
    "timeline-warm",
    "timeline-cold",
    "experience-strong",
    "experience-developing",
]


# ═══════════════════════════════════════════════════════════════════════════════
# API HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

class GHLClient:
    def __init__(self, dry_run=True):
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.results = {
            "custom_fields": [],
            "calendars": [],
            "tags": [],
            "webhook": None,
            "user_id": None,
            "errors": [],
        }

    def _get(self, path, params=None):
        url = f"{API_BASE}{path}"
        try:
            r = self.session.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            self.results["errors"].append(f"GET {path}: {e}")
            return None

    def _post(self, path, payload):
        url = f"{API_BASE}{path}"
        if self.dry_run:
            print(f"  [DRY-RUN] POST {path}")
            print(f"            payload: {json.dumps(payload, indent=2)[:200]}...")
            return {"id": "dry-run-id", "dry_run": True}
        try:
            r = self.session.post(url, json=payload, timeout=15)
            if r.status_code in (200, 201):
                return r.json()
            else:
                body = r.text[:300]
                self.results["errors"].append(f"POST {path} → {r.status_code}: {body}")
                print(f"  [ERROR] {r.status_code}: {body}")
                return None
        except requests.RequestException as e:
            self.results["errors"].append(f"POST {path}: {e}")
            return None

    def _delete(self, path):
        url = f"{API_BASE}{path}"
        if self.dry_run:
            print(f"  [DRY-RUN] DELETE {path}")
            return True
        try:
            r = self.session.delete(url, timeout=15)
            return r.status_code in (200, 204)
        except requests.RequestException:
            return False

    # ── Lookup user ───────────────────────────────────────────
    def lookup_user(self):
        print("\n[1/5] Looking up users...")
        data = self._get(f"/users/", params={"locationId": LOCATION_ID})
        if data and "users" in data:
            for u in data["users"]:
                name = f"{u.get('firstName', '')} {u.get('lastName', '')}".strip()
                print(f"  Found: {name} ({u['id']})")
                if "mike" in name.lower() or "adams" in name.lower():
                    self.results["user_id"] = u["id"]
                    print(f"  → Selected: {name}")
            if not self.results["user_id"] and data["users"]:
                self.results["user_id"] = data["users"][0]["id"]
                print(f"  → Default to first user: {data['users'][0]['id']}")
        else:
            print("  [WARN] Could not list users")

    # ── Custom fields ─────────────────────────────────────────
    def get_existing_custom_fields(self):
        data = self._get(f"/locations/{LOCATION_ID}/customFields")
        if data and "customFields" in data:
            return {cf["name"]: cf for cf in data["customFields"]}
        return {}

    def create_custom_fields(self):
        print("\n[2/5] Creating custom fields...")
        existing = self.get_existing_custom_fields()
        created = 0
        skipped = 0
        for cf in CUSTOM_FIELDS:
            if cf["name"] in existing:
                print(f"  ✓ {cf['name']} — already exists (id: {existing[cf['name']].get('id', '?')})")
                self.results["custom_fields"].append({
                    "name": cf["name"],
                    "id": existing[cf["name"]].get("id"),
                    "status": "exists",
                })
                skipped += 1
                continue

            payload = {
                "name": cf["name"],
                "dataType": cf["dataType"],
                "placeholder": cf.get("placeholder", ""),
            }
            result = self._post(f"/locations/{LOCATION_ID}/customFields", payload)
            if result:
                cf_id = result.get("customField", {}).get("id") or result.get("id", "?")
                print(f"  + {cf['name']} — created (id: {cf_id})")
                self.results["custom_fields"].append({
                    "name": cf["name"],
                    "id": cf_id,
                    "status": "created",
                })
                created += 1
            else:
                print(f"  ✗ {cf['name']} — failed")
                self.results["custom_fields"].append({
                    "name": cf["name"],
                    "id": None,
                    "status": "failed",
                })
            time.sleep(0.3)  # rate limit

        print(f"  Summary: {created} created, {skipped} skipped (already exist)")

    # ── Calendars ─────────────────────────────────────────────
    def get_existing_calendars(self):
        data = self._get(f"/calendars/", params={"locationId": LOCATION_ID})
        if data and "calendars" in data:
            return {c["name"]: c for c in data["calendars"]}
        return {}

    def create_calendars(self):
        print("\n[3/5] Creating calendars...")
        existing = self.get_existing_calendars()
        for cal in CALENDARS:
            if cal["name"] in existing:
                existing_cal = existing[cal["name"]]
                cal_id = existing_cal.get("id", "?")
                print(f"  ✓ {cal['name']} — already exists (id: {cal_id})")
                self.results["calendars"].append({
                    "name": cal["name"],
                    "id": cal_id,
                    "slug": existing_cal.get("slug", cal["slug"]),
                    "status": "exists",
                })
                continue

            payload = {
                "locationId": LOCATION_ID,
                "name": cal["name"],
                "description": cal["description"],
                "slug": cal["slug"],
                "widgetSlug": cal["slug"],
                "calendarType": cal.get("calendarType", "round_robin_optimize"),
                "slotDuration": cal["slotDuration"],
                "slotInterval": cal["slotInterval"],
                "slotBuffer": cal.get("slotBuffer", 10),
                "appoinmentPerSlot": cal.get("appoinmentPerSlot", 1),
                "openHours": cal["openHours"],
                "timezone": cal.get("timezone", "America/New_York"),
                "enableRecurring": False,
                "autoConfirm": True,
            }

            # Assign to Mike if user found
            if self.results["user_id"]:
                payload["teamMembers"] = [
                    {"userId": self.results["user_id"], "priority": 0.5, "meetingLocationType": "custom", "meetingLocation": "Zoom link will be provided"}
                ]

            result = self._post("/calendars/", payload)
            if result:
                cal_data = result.get("calendar", result)
                cal_id = cal_data.get("id", "?")
                slug = cal_data.get("slug", cal["slug"])
                print(f"  + {cal['name']} — created (id: {cal_id}, slug: {slug})")
                self.results["calendars"].append({
                    "name": cal["name"],
                    "id": cal_id,
                    "slug": slug,
                    "status": "created",
                })
            else:
                print(f"  ✗ {cal['name']} — failed")
                self.results["calendars"].append({
                    "name": cal["name"],
                    "id": None,
                    "slug": cal["slug"],
                    "status": "failed",
                })
            time.sleep(0.5)

    # ── Tags ──────────────────────────────────────────────────
    def create_tags(self):
        print("\n[4/5] Creating tags...")
        # GHL doesn't have a dedicated "create tag" endpoint — tags are created
        # when first applied to a contact. We'll verify by listing existing tags.
        data = self._get(f"/locations/{LOCATION_ID}/tags")
        existing_tags = set()
        if data and "tags" in data:
            existing_tags = {t["name"].lower() for t in data["tags"]}

        new_tags = []
        existing_count = 0
        for tag in TAGS:
            if tag.lower() in existing_tags:
                existing_count += 1
            else:
                new_tags.append(tag)

        print(f"  {existing_count} tags already exist")
        if new_tags:
            print(f"  {len(new_tags)} new tags will be created on first contact assignment:")
            for t in new_tags:
                print(f"    · {t}")
        else:
            print("  All tags already exist")

        self.results["tags"] = {"existing": existing_count, "new": new_tags}

    # ── Webhook ───────────────────────────────────────────────
    def setup_webhook(self):
        print("\n[5/5] Checking webhook configuration...")
        # List existing webhooks
        data = self._get(f"/hooks/", params={"locationId": LOCATION_ID})
        webhook_url = None

        if data and "hooks" in data:
            for hook in data.get("hooks", []):
                if "discovery" in hook.get("name", "").lower() or "franchise" in hook.get("name", "").lower():
                    webhook_url = hook.get("targetUrl", "found but no URL")
                    print(f"  ✓ Found existing webhook: {hook['name']}")
                    print(f"    URL: {webhook_url}")
                    self.results["webhook"] = webhook_url
                    return

        # No matching webhook found — create one
        print("  No franchise webhook found. Creating...")
        payload = {
            "locationId": LOCATION_ID,
            "name": "Discovery Form — Franchise ICP Router",
            "url": f"https://services.leadconnectorhq.com/hooks/{LOCATION_ID}/franchise-discovery",
            "events": ["ContactCreate", "ContactUpdate"],
            "active": True,
        }

        if self.dry_run:
            print("  [DRY-RUN] Would create webhook for franchise discovery form")
            print("  Note: The actual webhook URL is generated by GHL when you create")
            print("  the workflow trigger. Use the GHL workflow's inbound webhook URL.")
            self.results["webhook"] = "CREATE_VIA_GHL_WORKFLOW_TRIGGER"
        else:
            # GHL inbound webhooks are created as workflow triggers, not via the hooks API.
            # The hooks API is for outbound webhooks. Print instructions.
            print("  Note: GHL inbound webhooks are generated inside workflows.")
            print("  Create the workflow first, add 'Inbound Webhook' trigger,")
            print("  then copy the generated URL into franchise-page.html CONFIG.")
            self.results["webhook"] = "CREATE_VIA_GHL_WORKFLOW_TRIGGER"

    # ── Run all ───────────────────────────────────────────────
    def run(self):
        mode = "DRY-RUN" if self.dry_run else "LIVE"
        print("=" * 65)
        print(f" STR Solutions — GHL Franchise Setup [{mode}]")
        print(f" Location: {LOCATION_ID}")
        print(f" Timestamp: {datetime.now().isoformat()}")
        print("=" * 65)

        # Validate API key first
        print("\n[0/5] Validating API key...")
        test = self._get(f"/locations/{LOCATION_ID}")
        if test is None:
            print("  ✗ API key validation failed. Check token and location ID.")
            print("  Aborting.")
            return self.results
        loc_name = test.get("location", {}).get("name") or test.get("name", "?")
        print(f"  ✓ Connected to: {loc_name}")

        self.lookup_user()
        self.create_custom_fields()
        self.create_calendars()
        self.create_tags()
        self.setup_webhook()

        self.print_summary()
        return self.results

    # ── Summary ───────────────────────────────────────────────
    def print_summary(self):
        print("\n" + "=" * 65)
        print(" SETUP SUMMARY")
        print("=" * 65)

        # Custom fields
        cf_created = sum(1 for cf in self.results["custom_fields"] if cf["status"] == "created")
        cf_exists = sum(1 for cf in self.results["custom_fields"] if cf["status"] == "exists")
        cf_failed = sum(1 for cf in self.results["custom_fields"] if cf["status"] == "failed")
        print(f"\n Custom Fields: {cf_created} created, {cf_exists} existed, {cf_failed} failed")
        for cf in self.results["custom_fields"]:
            icon = "✓" if cf["status"] in ("created", "exists") else "✗"
            print(f"   {icon} {cf['name']} → {cf['id']}")

        # Calendars
        print(f"\n Calendars:")
        for cal in self.results["calendars"]:
            icon = "✓" if cal["status"] in ("created", "exists") else "✗"
            print(f"   {icon} {cal['name']}")
            if cal["id"]:
                print(f"     ID: {cal['id']}")
                print(f"     Booking URL: https://api.leadconnectorhq.com/widget/booking/{cal['slug']}")

        # Tags
        tags = self.results.get("tags", {})
        print(f"\n Tags: {tags.get('existing', 0)} exist, {len(tags.get('new', []))} pending first use")

        # Webhook
        print(f"\n Webhook: {self.results.get('webhook', 'not configured')}")

        # Assigned user
        print(f"\n Assigned User: {self.results.get('user_id', 'not found')}")

        # Errors
        if self.results["errors"]:
            print(f"\n ERRORS ({len(self.results['errors'])}):")
            for err in self.results["errors"]:
                print(f"   ✗ {err}")

        # Config block for franchise-page.html
        print("\n" + "-" * 65)
        print(" CONFIG BLOCK — paste into franchise-page.html")
        print("-" * 65)

        icp1_slug = "introductory-meeting-str"
        icp5_slug = "franchise-discovery-call"
        for cal in self.results["calendars"]:
            if "introductory" in cal["name"].lower():
                icp1_slug = cal.get("slug", icp1_slug)
            if "franchise" in cal["name"].lower():
                icp5_slug = cal.get("slug", icp5_slug)

        webhook_url = self.results.get("webhook", "YOUR_WEBHOOK_ID")

        print(f"""
  const CONFIG = {{
    webhookUrl: '{webhook_url}',
    icp1CalendarUrl: 'https://api.leadconnectorhq.com/widget/booking/{icp1_slug}',
    icp5CalendarUrl: 'https://api.leadconnectorhq.com/widget/booking/{icp5_slug}'
  }};
""")

        # Field ID mapping for workflow
        print("-" * 65)
        print(" CUSTOM FIELD ID MAP — for workflow configuration")
        print("-" * 65)
        for cf in self.results["custom_fields"]:
            if cf["id"]:
                print(f"  {cf['name']}: {cf['id']}")

        print("\n" + "=" * 65)
        print(f" Done. {'Dry run — no changes made.' if self.dry_run else 'All resources created.'}")
        print("=" * 65)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="STR Solutions — GHL Franchise Page Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 ghl-franchise-setup.py              # dry-run (preview only)
  python3 ghl-franchise-setup.py --execute    # create all resources
  python3 ghl-franchise-setup.py --list       # list existing custom fields + calendars
        """,
    )
    parser.add_argument("--execute", action="store_true", help="Actually create resources (default is dry-run)")
    parser.add_argument("--list", action="store_true", help="List existing custom fields and calendars")
    args = parser.parse_args()

    if args.list:
        client = GHLClient(dry_run=True)
        print("=== Existing Custom Fields ===")
        fields = client.get_existing_custom_fields()
        for name, cf in sorted(fields.items()):
            print(f"  {name}: {cf.get('id', '?')} ({cf.get('dataType', '?')})")
        print(f"\n  Total: {len(fields)}")

        print("\n=== Existing Calendars ===")
        cals = client.get_existing_calendars()
        for name, cal in sorted(cals.items()):
            print(f"  {name}: {cal.get('id', '?')} (slug: {cal.get('slug', '?')})")
        print(f"\n  Total: {len(cals)}")
        return

    if not args.execute:
        print("=" * 65)
        print(" DRY-RUN MODE — no changes will be made")
        print(" Run with --execute to create resources")
        print("=" * 65)

    client = GHLClient(dry_run=not args.execute)
    client.run()


if __name__ == "__main__":
    main()
