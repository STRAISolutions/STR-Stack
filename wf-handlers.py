#!/usr/bin/env python3
"""
STR Solutions — Workflow Handlers (WF2 + WF3)
Standalone webhook handlers that replace broken GHL workflows.
Runs on the droplet, processes webhooks, and executes all logic via GHL API.

WF2: Hostfully GHL Integration — booking events, contact routing, pipeline mgmt
WF3: Discovery Form — ICP Router + Qualification

Usage:
  python3 wf-handlers.py                # Start server on port 8500
  python3 wf-handlers.py --port 8501    # Custom port
  python3 wf-handlers.py --test wf2     # Test WF2 with sample payload
  python3 wf-handlers.py --test wf3     # Test WF3 with sample payload
"""

import json
import time
import sys
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

# ── Config ────────────────────────────────────────────────────
GHL_API = "https://services.leadconnectorhq.com"
GHL_TOKEN = "pit-8e3c20cd-0d7f-43a3-be9d-c087e925b3e7"
GHL_LOCATION = "1OOZ4AKIgxO8QKKMnIcK"
MIKE_USER_ID = "Lc2bBJfpmmCueklVfR1B"
GHL_HEADERS = {
    "Authorization": f"Bearer {GHL_TOKEN}",
    "Version": "2021-07-28",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "STR-WF-Handlers/1.0",
}

# Pipeline IDs
PIPE_B1 = "U42jfbNKw6ohzKL5vbye"  # B1) Traveler Inquiries
PIPE_B2 = "yX9EO3xdysFjiNTA2w5F"  # B2) Property Bookings
PIPE_A1 = "UbDCcfmiPEClDemNKo1A"  # A1) Master Pipeline

# B1 Stages
B1_NEW_INQUIRY = "14672a8d-372a-40a6-9c9e-d2f7c532017d"
B1_CONFIRMED = "bd6b1961-184d-4ba7-b4e4-4ac582d63e5c"
B1_CANCELLED = "c4263d0a-ee7d-4b33-afa1-bb8d4674ae87"

# B2 Stages
B2_CONFIRMED = "7fb40f14-b6bf-47be-b61a-165f8de52b1c"
B2_CHECKIN = "f17d9e87-6874-43c1-b2f3-8ebbcb12f8d7"
B2_CHECKOUT = "251af025-f99a-4cc3-8168-dbeb8f52e3d8"
B2_REVIEW = "1a75bdb8-1260-4ff6-a026-c0663d9629ca"
B2_CANCELLED = "c825b646-36ab-47d0-b6bd-6b916aea145c"

# A1 Master Pipeline Stages
A1_NEW_LEAD = "1e27c19c-8b7f-4379-b88f-dcdedfcc10ea"           # 🧲 New Lead (Captured)
A1_CAPITAL_QUALIFIED = "fb056da9-7614-4f4d-acee-bacea935e095"   # 🟩❌ Qualified - Not Booked
A1_VETTING = "1e27c19c-8b7f-4379-b88f-dcdedfcc10ea"            # 🧲 New Lead (Captured)
A1_NURTURE = "cda9f83d-324b-4d5f-a449-180b1472686c"            # 🧊 Lost/Nurture
A1_CLOSED_LOST = "d7a563cb-3311-4b7f-8a23-707d035c583a"        # 🚫 Closed - Lost

# Calendar URLs
CAL_ICP1 = "https://api.leadconnectorhq.com/widget/booking/introductory-meeting-str"
CAL_ICP5 = "https://api.leadconnectorhq.com/widget/booking/str-franchise-discovery-call"

PORT = 8500

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/root/str-stack/wf-handlers.log"),
    ],
)
log = logging.getLogger("wf-handlers")


# ── GHL API Helpers ───────────────────────────────────────────
def ghl_request(method, path, data=None, params=None):
    """Make a GHL API request."""
    url = f"{GHL_API}{path}"
    if params:
        url += "?" + urlencode(params)
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=GHL_HEADERS, method=method)
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        log.error(f"GHL {method} {path} → {e.code}: {err_body[:300]}")
        return {"error": e.code, "message": err_body[:300]}


def find_contact(email):
    """Find contact by email."""
    r = ghl_request("GET", "/contacts/", params={
        "locationId": GHL_LOCATION,
        "query": email,
        "limit": 1,
    })
    contacts = r.get("contacts", [])
    if contacts:
        for c in contacts:
            if c.get("email", "").lower() == email.lower():
                return c
    return None


def create_contact(fields):
    """Create a new contact."""
    fields["locationId"] = GHL_LOCATION
    fields["source"] = fields.get("source", "Hostfully")
    return ghl_request("POST", "/contacts/", data=fields)


def update_contact(contact_id, fields):
    """Update contact fields."""
    return ghl_request("PUT", f"/contacts/{contact_id}", data=fields)


def add_tags(contact_id, tags):
    """Add tags to contact."""
    return ghl_request("POST", f"/contacts/{contact_id}/tags", data={"tags": tags})


def remove_tags(contact_id, tags):
    """Remove tags from contact."""
    return ghl_request("DELETE", f"/contacts/{contact_id}/tags", data={"tags": tags})


def add_note(contact_id, body):
    """Add a note to contact."""
    return ghl_request("POST", f"/contacts/{contact_id}/notes", data={
        "body": body,
        "userId": MIKE_USER_ID,
    })


def create_opportunity(pipeline_id, stage_id, contact_id, name, status="open"):
    """Create opportunity in pipeline."""
    return ghl_request("POST", "/opportunities/", data={
        "pipelineId": pipeline_id,
        "pipelineStageId": stage_id,
        "contactId": contact_id,
        "name": name,
        "status": status,
        "locationId": GHL_LOCATION,
        "assignedTo": MIKE_USER_ID,
    })


def update_opportunity_stage(pipeline_id, contact_id, stage_id):
    """Find and update opportunity stage for a contact in a pipeline."""
    r = ghl_request("GET", "/opportunities/search", params={
        "location_id": GHL_LOCATION,
        "pipeline_id": pipeline_id,
        "contact_id": contact_id,
        "limit": 1,
    })
    opps = r.get("opportunities", [])
    if opps:
        opp_id = opps[0]["id"]
        return ghl_request("PUT", f"/opportunities/{opp_id}", data={
            "pipelineStageId": stage_id,
        })
    return None


def assign_contact(contact_id):
    """Assign contact to Mike Adams."""
    return update_contact(contact_id, {"assignedTo": MIKE_USER_ID})


def send_email(contact_id, subject, body_html):
    """Send email via GHL conversations API."""
    return ghl_request("POST", "/conversations/messages", data={
        "type": "Email",
        "contactId": contact_id,
        "subject": subject,
        "html": body_html,
        "emailFrom": "mike@strincsolutions.com",
    })


def send_sms(contact_id, message):
    """Send SMS via GHL conversations."""
    return ghl_request("POST", "/conversations/messages", data={
        "type": "SMS",
        "contactId": contact_id,
        "message": message,
    })


# ── WF2: Hostfully GHL Integration ───────────────────────────
def handle_wf2(payload):
    """Process Hostfully webhook event."""
    email = payload.get("guest_email", "").strip()
    if not email:
        return {"error": "No guest_email in payload"}

    event_type = payload.get("event_type", "unknown")
    first_name = payload.get("guest_first_name", "")
    last_name = payload.get("guest_last_name", "")
    phone = payload.get("guest_phone", "")
    property_name = payload.get("property_name", "")
    check_in = payload.get("check_in_date", "")
    check_out = payload.get("check_out_date", "")
    booking_status = payload.get("booking_status", "")
    booking_channel = payload.get("booking_channel", "")
    guest_count = payload.get("guest_count", "")
    booking_revenue = payload.get("booking_revenue", "")
    lead_uid = payload.get("hostfully_lead_uid", "")
    prop_uid = payload.get("hostfully_property_uid", "")

    log.info(f"WF2: {event_type} | {email} | {property_name}")

    # Custom field values
    custom_fields = {
        "Booking Channel": booking_channel,
        "Property Name": property_name,
        "Guest Count": str(guest_count),
        "Booking Revenue": str(booking_revenue),
        "Check-In Date": check_in,
        "Check-Out Date": check_out,
        "Hostfully Booking Status": booking_status,
        "Hostfully Lead UID": lead_uid,
        "Hostfully Property UID": prop_uid,
    }

    # Step 1: Find or create contact
    contact = find_contact(email)
    is_existing = contact is not None

    if not is_existing:
        log.info(f"  Creating new contact: {first_name} {last_name} <{email}>")
        result = create_contact({
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "phone": phone,
            "customFields": [{"key": k, "value": v} for k, v in custom_fields.items() if v],
        })
        contact_id = result.get("contact", {}).get("id")
        if not contact_id:
            return {"error": "Failed to create contact", "detail": result}

        add_tags(contact_id, ["#hostfully", "traveler", "guest-active"])
        add_note(contact_id, f"New guest via Hostfully ({booking_channel}). Property: {property_name}. Check-in: {check_in}. Check-out: {check_out}. Status: {booking_status}.")
    else:
        contact_id = contact["id"]
        log.info(f"  Found existing contact: {contact_id}")
        update_contact(contact_id, {
            "customFields": [{"key": k, "value": v} for k, v in custom_fields.items() if v],
        })
        add_note(contact_id, f"Hostfully update ({event_type}): {booking_status} | Property: {property_name} | Check-in: {check_in} | Check-out: {check_out} | Channel: {booking_channel}")

    # Step 2: Route by event_type
    if event_type == "booking_created":
        log.info("  → booking_created branch")
        name = f"{first_name} {last_name}"
        create_opportunity(PIPE_B1, B1_CONFIRMED, contact_id, f"{name} - Booking")
        create_opportunity(PIPE_B2, B2_CONFIRMED, contact_id, f"{name} - {property_name}")
        add_tags(contact_id, ["guest-active"])
        if is_existing:
            add_tags(contact_id, ["repeat-guest"])
        add_note(contact_id, f"Booking created via {booking_channel}: {property_name}, {check_in} to {check_out}")

    elif event_type == "message_received":
        log.info("  → message_received branch")
        if not is_existing:
            create_opportunity(PIPE_B1, B1_NEW_INQUIRY, contact_id, f"{first_name} {last_name} - Inquiry")
        add_tags(contact_id, ["hostfully:follow-up"])
        add_note(contact_id, "Message received via Hostfully")

    elif event_type == "booking_cancelled":
        log.info("  → booking_cancelled branch")
        update_opportunity_stage(PIPE_B2, contact_id, B2_CANCELLED)
        update_opportunity_stage(PIPE_B1, contact_id, B1_CANCELLED)
        add_tags(contact_id, ["guest-cancelled"])
        remove_tags(contact_id, ["guest-active"])
        add_note(contact_id, "Booking cancelled")

    elif event_type == "guest_checkin":
        log.info("  → guest_checkin branch")
        update_opportunity_stage(PIPE_B2, contact_id, B2_CHECKIN)
        remove_tags(contact_id, ["guest-active"])
        add_tags(contact_id, ["guest-checked-in"])
        add_note(contact_id, f"Guest checked in at {property_name} on {check_in}")

    elif event_type == "guest_checkout":
        log.info("  → guest_checkout branch")
        update_opportunity_stage(PIPE_B2, contact_id, B2_CHECKOUT)
        remove_tags(contact_id, ["guest-checked-in"])
        add_tags(contact_id, ["guest-checkout"])
        add_note(contact_id, f"Guest checked out of {property_name} on {check_out}")

        # Schedule review request after 24 hours
        def delayed_review():
            time.sleep(86400)  # 24 hours
            log.info(f"  → 24h review trigger for {contact_id}")
            add_tags(contact_id, ["review-request-pending"])
            update_opportunity_stage(PIPE_B2, contact_id, B2_REVIEW)

        t = threading.Thread(target=delayed_review, daemon=True)
        t.start()
        log.info("  → Scheduled 24h review request")

    else:
        log.info(f"  → default branch (event: {event_type})")
        add_note(contact_id, f"Hostfully event received: {event_type} for {property_name}")

    # Final: Assign to Mike Adams
    assign_contact(contact_id)

    return {"status": "ok", "workflow": "WF2", "event": event_type, "contact_id": contact_id, "is_new": not is_existing}


# ── WF3: Discovery Form — ICP Router + Qualification ─────────
def handle_wf3(payload):
    """Process Discovery Form webhook."""
    email = payload.get("email", "").strip()
    if not email:
        return {"error": "No email in payload"}

    first_name = payload.get("first_name", "")
    last_name = payload.get("last_name", "")
    phone = payload.get("phone", "")
    city_state = payload.get("city_state", "")
    icp_interest = payload.get("icp_interest", "")
    property_count = payload.get("property_count", "")
    listing_platforms = payload.get("listing_platforms", "")
    owner_challenge = payload.get("owner_challenge", "")
    icp5_liquid_capital = payload.get("icp5_liquid_capital", "")
    icp5_funding_source = payload.get("icp5_funding_source", "")
    icp5_timeline = payload.get("icp5_timeline", "")
    icp5_background = payload.get("icp5_background", "")
    icp5_biz_experience = payload.get("icp5_biz_experience", "")
    icp5_target_market = payload.get("icp5_target_market", "")
    icp5_motivation = payload.get("icp5_motivation", "")
    icp5_score = payload.get("icp5_qualification_score", "")
    icp5_tier = payload.get("icp5_qualification_tier", "")

    log.info(f"WF3: {icp_interest} | {email} | tier={icp5_tier}")

    # Step 1: Find or create contact
    contact = find_contact(email)
    if contact:
        contact_id = contact["id"]
        update_contact(contact_id, {
            "firstName": first_name,
            "lastName": last_name,
            "phone": phone,
        })
    else:
        result = create_contact({
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "phone": phone,
            "source": "Website",
        })
        contact_id = result.get("contact", {}).get("id")
        if not contact_id:
            return {"error": "Failed to create contact", "detail": result}

    # Step 2: Update custom fields
    custom_fields = {
        "ICP Interest": icp_interest,
        "Property Count": property_count,
        "Listing Platforms": listing_platforms,
        "Owner Challenge": owner_challenge,
        "ICP5 Liquid Capital": icp5_liquid_capital,
        "ICP5 Funding Source": icp5_funding_source,
        "ICP5 Timeline": icp5_timeline,
        "ICP5 Background": icp5_background,
        "ICP5 Biz Experience": icp5_biz_experience,
        "ICP5 Target Market": icp5_target_market,
        "ICP5 Motivation": icp5_motivation,
    }
    update_contact(contact_id, {
        "customFields": [{"key": k, "value": v} for k, v in custom_fields.items() if v],
    })

    # Step 3: Base tags + note
    add_tags(contact_id, ["#discovery-form", "website-lead"])
    add_note(contact_id, f"Discovery form submitted. Interest: {icp_interest}. Score: {icp5_score}. Tier: {icp5_tier}.")

    name = f"{first_name} {last_name}"

    # Step 4: Route by ICP interest
    if icp_interest == "icp1":
        log.info("  → ICP1 branch (property owner)")
        add_tags(contact_id, ["ICP1", "str-owner"])
        create_opportunity(PIPE_A1, A1_NEW_LEAD, contact_id, f"{name} — STR Owner")

        send_email(contact_id,
            f"{first_name}, Your STR Solutions Intro Call",
            f"""<p>Hi {first_name},</p>
<p>Thank you for your interest in STR Solutions property management services.</p>
<p>We'd love to learn more about your properties and show you how our technology and systems can help increase your revenue and reduce your workload.</p>
<p>We've reserved a 15-minute introductory call slot for you:</p>
<p><a href="{CAL_ICP1}" style="background:#C8A456;color:#0D0D0D;padding:12px 24px;text-decoration:none;border-radius:4px;font-weight:bold;">BOOK YOUR 15-MIN INTRO CALL</a></p>
<p>Looking forward to connecting,<br>Mike Adams<br>STR Solutions USA</p>"""
        )
        send_sms(contact_id, f"Hi {first_name}, thanks for your interest in STR Solutions! Book a quick 15-min intro call here: {CAL_ICP1} — Mike, STR Solutions")
        add_note(contact_id, f"ICP1 property owner. Properties: {property_count}. Platforms: {listing_platforms}. Challenge: {owner_challenge}.")

    elif icp_interest == "icp5":
        log.info("  → ICP5 branch (franchise candidate)")
        add_tags(contact_id, ["ICP5", "franchise-candidate"])
        _route_icp5(contact_id, name, first_name, icp5_tier, icp5_score, icp5_liquid_capital, icp5_timeline, icp5_background, icp5_biz_experience, icp5_motivation)
        add_note(contact_id, f"ICP5 franchise candidate. Capital: {icp5_liquid_capital}. Timeline: {icp5_timeline}. Background: {icp5_background}. Experience: {icp5_biz_experience}. Motivation: {icp5_motivation}. Score: {icp5_score}. Tier: {icp5_tier}.")

    elif icp_interest == "both":
        log.info("  → BOTH branch (dual interest)")
        add_tags(contact_id, ["ICP1", "ICP5", "str-owner", "franchise-candidate", "dual-interest"])
        create_opportunity(PIPE_A1, A1_NEW_LEAD, contact_id, f"{name} — Dual Interest")
        _route_icp5_dual(contact_id, name, first_name, icp5_tier, icp5_score, property_count)
        add_note(contact_id, f"Dual interest (ICP1 + ICP5). Properties: {property_count}. Franchise score: {icp5_score} ({icp5_tier}).")

    else:
        log.info(f"  → Unknown ICP interest: {icp_interest}")
        add_note(contact_id, f"Unknown ICP interest value: {icp_interest}")

    # Final: Assign to Mike Adams
    assign_contact(contact_id)

    return {"status": "ok", "workflow": "WF3", "icp": icp_interest, "tier": icp5_tier, "contact_id": contact_id}


def _route_icp5(contact_id, name, first_name, tier, score, capital, timeline, background, experience, motivation):
    """ICP5 qualification tier routing."""
    if tier == "fast-track":
        add_tags(contact_id, ["ICP5-fast-track", "capital-tier-A", "timeline-hot"])
        create_opportunity(PIPE_A1, A1_CAPITAL_QUALIFIED, contact_id, f"{name} — Franchise Fast Track")
        send_email(contact_id,
            f"{first_name}, You're Pre-Qualified — Book Your Discovery Call",
            f"""<p>Hi {first_name},</p>
<p>Great news — based on your responses, you are pre-qualified for an STR Solutions franchise territory.</p>
<p>Click below to book your 30-minute Franchise Discovery Call:</p>
<p><a href="{CAL_ICP5}" style="background:#C8A456;color:#0D0D0D;padding:12px 24px;text-decoration:none;border-radius:4px;font-weight:bold;">BOOK YOUR DISCOVERY CALL NOW</a></p>
<p>We're excited about the potential fit.</p>
<p>Best,<br>Mike Adams<br>Founder, STR Solutions USA</p>"""
        )
        send_sms(contact_id, f"Great news {first_name}! You're pre-qualified for an STR Solutions franchise territory. Book your 30-min discovery call: {CAL_ICP5} — Mike, STR Solutions")

    elif tier == "qualified":
        add_tags(contact_id, ["ICP5-qualified"])
        create_opportunity(PIPE_A1, A1_VETTING, contact_id, f"{name} — Franchise Qualified")
        send_email(contact_id,
            f"{first_name}, Your STR Solutions Franchise Overview",
            f"""<p>Hi {first_name},</p>
<p>Thank you for your interest in owning an STR Solutions franchise territory.</p>
<p>Your profile aligns well with what we look for in franchise partners. We'd like to schedule a 30-minute Discovery Call.</p>
<p><a href="{CAL_ICP5}" style="background:#C8A456;color:#0D0D0D;padding:12px 24px;text-decoration:none;border-radius:4px;font-weight:bold;">SCHEDULE YOUR DISCOVERY CALL</a></p>
<p>Best,<br>Mike Adams<br>Founder, STR Solutions USA</p>"""
        )
        send_sms(contact_id, f"Hi {first_name}, thanks for your interest in STR Solutions franchising! Book a call when ready: {CAL_ICP5} — Mike")

    elif tier == "nurture":
        add_tags(contact_id, ["ICP5-nurture", "timeline-warm"])
        create_opportunity(PIPE_A1, A1_NURTURE, contact_id, f"{name} — Franchise Nurture")
        send_email(contact_id,
            "STR Solutions Franchise — What You Need to Know",
            f"""<p>Hi {first_name},</p>
<p>Thank you for exploring franchise opportunities with STR Solutions USA.</p>
<p>Based on your responses, we think you'd benefit from learning more about our model before scheduling a formal discovery call.</p>
<p><strong>Investment overview:</strong></p>
<ul>
<li>Franchise fee: competitive with industry standards</li>
<li>Liquid capital requirement: $100K minimum recommended</li>
<li>ROI timeline: most territories reach profitability within 12-18 months</li>
</ul>
<p>When you're ready to take the next step, simply reply to this email.</p>
<p>Best,<br>Mike Adams<br>Founder, STR Solutions USA</p>"""
        )
        # NO calendar link for nurture

    else:  # not-qualified or unknown
        add_tags(contact_id, ["ICP5-not-qualified"])
        create_opportunity(PIPE_A1, A1_CLOSED_LOST, contact_id, f"{name} — Franchise DQ", status="lost")
        send_email(contact_id,
            "Thank You for Your Interest — STR Solutions",
            f"""<p>Hi {first_name},</p>
<p>Thank you for completing our franchise discovery questionnaire.</p>
<p>After reviewing your responses, our franchise model may not be the ideal fit at this time. We'll keep your information on file and reach out if circumstances change.</p>
<p>Wishing you the best,<br>Mike Adams<br>Founder, STR Solutions USA</p>"""
        )
        # NO calendar link


def _route_icp5_dual(contact_id, name, first_name, tier, score, property_count):
    """Dual interest routing — send both calendar links for qualified tiers."""
    if tier in ("fast-track", "qualified"):
        tags = ["ICP5-fast-track", "capital-tier-A", "timeline-hot"] if tier == "fast-track" else ["ICP5-qualified"]
        add_tags(contact_id, tags)
        stage = A1_CAPITAL_QUALIFIED if tier == "fast-track" else A1_VETTING
        # Don't create duplicate opportunity — already created in the "both" branch
        send_email(contact_id,
            f"{first_name}, Two Paths at STR Solutions",
            f"""<p>Hi {first_name},</p>
<p>Thank you for your interest in both STR Solutions property management and our franchise opportunity.</p>
<p><strong>For your existing properties:</strong></p>
<p><a href="{CAL_ICP1}" style="background:#C8A456;color:#0D0D0D;padding:12px 24px;text-decoration:none;border-radius:4px;font-weight:bold;">BOOK 15-MIN INTRO CALL</a></p>
<p><strong>For franchise ownership:</strong></p>
<p><a href="{CAL_ICP5}" style="background:#C8A456;color:#0D0D0D;padding:12px 24px;text-decoration:none;border-radius:4px;font-weight:bold;">BOOK 30-MIN DISCOVERY CALL</a></p>
<p>You can book one or both — whichever fits your priority right now.</p>
<p>Best,<br>Mike Adams<br>Founder, STR Solutions USA</p>"""
        )
        send_sms(contact_id, f"Hi {first_name}! You qualify for both STR property management and franchising. Book your calls: Intro: {CAL_ICP1} | Franchise: {CAL_ICP5} — Mike")
    else:
        # Nurture/not-qualified for franchise, but still valid ICP1
        if tier == "nurture":
            add_tags(contact_id, ["ICP5-nurture", "timeline-warm"])
        else:
            add_tags(contact_id, ["ICP5-not-qualified"])
        # Send only ICP1 calendar
        send_email(contact_id,
            f"{first_name}, Your STR Solutions Intro Call",
            f"""<p>Hi {first_name},</p>
<p>Thank you for your interest in STR Solutions. We'd love to learn more about your properties.</p>
<p><a href="{CAL_ICP1}" style="background:#C8A456;color:#0D0D0D;padding:12px 24px;text-decoration:none;border-radius:4px;font-weight:bold;">BOOK YOUR 15-MIN INTRO CALL</a></p>
<p>Best,<br>Mike Adams<br>Founder, STR Solutions USA</p>"""
        )
        send_sms(contact_id, f"Hi {first_name}, thanks for your interest in STR Solutions! Book a quick intro call: {CAL_ICP1} — Mike")


# ── HTTP Server ───────────────────────────────────────────────
class WFHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode() if length > 0 else "{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.respond(400, {"error": "Invalid JSON"})
            return

        if self.path == "/wf2" or self.path == "/wf2/hostfully":
            result = handle_wf2(payload)
        elif self.path == "/wf3" or self.path == "/wf3/discovery":
            result = handle_wf3(payload)
        elif self.path == "/health":
            result = {"status": "ok", "handlers": ["wf2", "wf3"]}
        else:
            self.respond(404, {"error": f"Unknown path: {self.path}"})
            return

        status = 200 if "error" not in result else 400
        self.respond(status, result)

    def do_GET(self):
        if self.path == "/health":
            self.respond(200, {"status": "ok", "handlers": ["wf2", "wf3"], "port": PORT})
        else:
            self.respond(200, {"info": "STR WF Handlers", "endpoints": ["/wf2", "/wf3", "/health"]})

    def respond(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def log_message(self, fmt, *args):
        log.info(f"HTTP {args[0]}")


# ── Test Mode ─────────────────────────────────────────────────
def run_test(wf):
    if wf == "wf2":
        payload = {
            "guest_email": "test@example.com",
            "guest_first_name": "Test",
            "guest_last_name": "Guest",
            "guest_phone": "+15555551234",
            "property_name": "Clifton Hill Hideaway 4A",
            "check_in_date": "2026-04-20",
            "check_out_date": "2026-04-25",
            "booking_status": "BOOKED",
            "booking_channel": "AIRBNB",
            "guest_count": 4,
            "booking_revenue": 1250.00,
            "hostfully_lead_uid": "test-lead-001",
            "hostfully_property_uid": "test-prop-001",
            "event_type": "booking_created",
        }
        print("Testing WF2 with booking_created event...")
        result = handle_wf2(payload)
    elif wf == "wf3":
        payload = {
            "first_name": "Test",
            "last_name": "Franchise",
            "email": "testfranchise@example.com",
            "phone": "+15555559876",
            "city_state": "Toronto, ON",
            "icp_interest": "icp5",
            "property_count": "",
            "listing_platforms": "",
            "owner_challenge": "",
            "icp5_liquid_capital": "$150K-$250K",
            "icp5_funding_source": "Personal savings",
            "icp5_timeline": "Within 3 months",
            "icp5_background": "Hospitality",
            "icp5_biz_experience": "5+ years",
            "icp5_target_market": "Niagara Falls",
            "icp5_motivation": "Passive income + growth",
            "icp5_qualification_score": "48",
            "icp5_qualification_tier": "fast-track",
        }
        print("Testing WF3 with ICP5 fast-track...")
        result = handle_wf3(payload)
    else:
        print(f"Unknown workflow: {wf}. Use 'wf2' or 'wf3'.")
        return

    print(json.dumps(result, indent=2))


# ── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    if "--test" in sys.argv:
        idx = sys.argv.index("--test")
        wf = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "wf2"
        run_test(wf)
    else:
        if "--port" in sys.argv:
            idx = sys.argv.index("--port")
            PORT = int(sys.argv[idx + 1])

        print(f"=" * 50)
        print(f"STR WF Handlers — Starting on port {PORT}")
        print(f"  WF2 (Hostfully): POST http://0.0.0.0:{PORT}/wf2")
        print(f"  WF3 (Discovery): POST http://0.0.0.0:{PORT}/wf3")
        print(f"  Health:          GET  http://0.0.0.0:{PORT}/health")
        print(f"=" * 50)

        server = HTTPServer(("0.0.0.0", PORT), WFHandler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            server.shutdown()
