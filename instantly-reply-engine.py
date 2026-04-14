#!/usr/bin/env python3
"""
STR Solutions — Instantly LLM Reply Engine
Receives reply_received webhooks from Instantly, classifies with GPT,
generates custom replies, sends back via Instantly API, tags in GHL.

Runs as systemd service on port 8502.
Nginx proxies /api/instantly-reply → localhost:8502
"""

import http.server
import json
import urllib.request
import os
import time
import threading
import traceback
from datetime import datetime

PORT = 8502

# ── API Keys ──
INSTANTLY_API_KEY = "NDI1M2E0YTQtNGY0Mi00M2I3LWEyMTUtZDZjMTJlY2RkNGNkOlFkSmlxZFpaY21lZg=="
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_DEFAULT_MODEL", "gpt-4o-mini")
GHL_MASTER_TOKEN = "pit-8e3c20cd-0d7f-43a3-be9d-c087e925b3e7"
GHL_CC_TOKEN = "pit-48465a41-26c9-4115-8195-b0a557dbdb6d"
GHL_MASTER_LOC = "1OOZ4AKIgxO8QKKMnIcK"
GHL_CC_LOC = "7hTDBClatcBgmUv36bZX"

# ── STR Franchise Context for LLM ──
SYSTEM_PROMPT = """You are the AI sales assistant for STR Solutions USA, a short-term rental franchise company. You respond to email replies from leads who received our outreach about the STR franchise opportunity.

COMPANY CONTEXT:
- STR Solutions USA offers a franchise model for short-term rental (Airbnb-style) property management
- Franchisees get exclusive territory, centralized AI-powered operations, revenue management, and guest communication
- We handle the tech stack, booking optimization, and operational support
- Franchise questionnaire (2 min assessment): https://strsolutionsusa.com/franchise
- Discovery call booking: https://api.leadconnectorhq.com/widget/booking/str-franchise-discovery-call

YOUR TASK:
1. Read the lead's reply email
2. Classify it as one of: interested, question, not_interested, auto_reply, spam
3. If interested or question: write a personalized, warm reply that moves them toward the questionnaire or a discovery call
4. If not_interested: write a brief, respectful close (1-2 sentences)
5. If auto_reply or spam: respond with "SKIP" only

TONE: Professional but conversational. You're Mike's AI assistant. Be concise (3-5 sentences max for interested replies). Don't be salesy — be helpful and direct.

REPLY FORMAT (JSON):
{
  "classification": "interested|question|not_interested|auto_reply|spam",
  "reply_body": "Your reply text here or SKIP",
  "confidence": 0.0-1.0,
  "reason": "Brief reason for classification"
}

RULES:
- Never include the lead's original email in your reply
- Never use generic templates — reference specific things from their reply
- For interested leads, always include the questionnaire link
- For very interested leads (asking about investment, territory, etc.), suggest the discovery call
- Keep subject line as-is (it's a reply in the same thread)
- Sign off as: Mike, STR Solutions USA
- Do NOT reply to bounce notifications, ticket systems, or support desk auto-replies
"""

# ── Log file ──
LOG_FILE = "/root/str-stack/instantly-reply-engine.log"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except:
        pass


def call_openai(lead_email, lead_name, reply_subject, reply_body, campaign_name=""):
    """Call OpenAI to classify and generate reply"""
    user_msg = f"""Lead: {lead_name} <{lead_email}>
Campaign: {campaign_name}
Subject: {reply_subject}
Reply body:
{reply_body[:1500]}"""

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.7,
        "max_tokens": 500,
        "response_format": {"type": "json_object"}
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
    )
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode())
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


def send_instantly_reply(reply_to_uuid, reply_body, eaccount="", subject=""):
    """Send reply via Instantly API"""
    # Convert plain text to simple HTML
    html_body = reply_body.replace("\n", "<br>")
    payload = {
        "reply_to_uuid": reply_to_uuid,
        "eaccount": eaccount,
        "subject": subject,
        "body": {"html": html_body, "text": reply_body}
    }

    req = urllib.request.Request(
        "https://api.instantly.ai/api/v2/emails/reply",
        data=json.dumps(payload).encode(),
        headers={
            "User-Agent": "STR-Stack/1.0",
            "Authorization": f"Bearer {INSTANTLY_API_KEY}",
            "Content-Type": "application/json"
        }
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read().decode())


def find_ghl_contact(email):
    """Find contact in GHL by email, return (contact_id, location_token)"""
    for token, loc in [(GHL_MASTER_TOKEN, "master"), (GHL_CC_TOKEN, "cc")]:
        url = f"https://services.leadconnectorhq.com/contacts/search/duplicate?email={email}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Version": "2021-07-28",
            "User-Agent": "STR-Stack/1.0"
        })
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode())
            contact = data.get("contact")
            if contact:
                return contact.get("id"), token, loc
        except:
            pass
    return None, None, None


def tag_ghl_contact(contact_id, token, tag):
    """Add tag to GHL contact"""
    if not contact_id or not token:
        return
    # Get current tags
    url = f"https://services.leadconnectorhq.com/contacts/{contact_id}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Version": "2021-07-28",
        "User-Agent": "STR-Stack/1.0"
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        current_tags = data.get("contact", {}).get("tags", [])
        if tag not in current_tags:
            current_tags.append(tag)
            update_body = json.dumps({"tags": current_tags}).encode()
            req2 = urllib.request.Request(
                f"https://services.leadconnectorhq.com/contacts/{contact_id}",
                data=update_body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Version": "2021-07-28",
                    "Content-Type": "application/json",
                    "User-Agent": "STR-Stack/1.0"
                },
                method="PUT"
            )
            urllib.request.urlopen(req2, timeout=15)
            log(f"  Tagged {contact_id} with #{tag}")
    except Exception as e:
        log(f"  GHL tag error: {e}")


def update_instantly_lead_status(email, campaign_id, interested_status):
    """Update lead interest status in Instantly (1=interested, 2=not_interested)"""
    payload = {
        "email": email,
        "campaign_id": campaign_id,
        "interested_status": interested_status
    }
    req = urllib.request.Request(
        "https://api.instantly.ai/api/v2/leads/update",
        data=json.dumps(payload).encode(),
        headers={
            "User-Agent": "STR-Stack/1.0",
            "Authorization": f"Bearer {INSTANTLY_API_KEY}",
            "Content-Type": "application/json"
        },
        method="PATCH"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        log(f"  Updated Instantly lead status: {interested_status}")
    except Exception as e:
        log(f"  Instantly status update error: {e}")


def process_reply(webhook_data):
    """Main processing pipeline for a reply"""
    try:
        # Extract fields from webhook payload
        # Instantly webhook payload structure may vary — handle flexibly
        email_data = webhook_data

        lead_email = (email_data.get("from_address_email") or
                      email_data.get("lead_email") or
                      email_data.get("email") or "")
        lead_name = (email_data.get("from_address_name") or
                     email_data.get("lead_name") or
                     email_data.get("first_name", "") + " " + email_data.get("last_name", "")).strip()
        reply_subject = email_data.get("subject", "")
        reply_body = email_data.get("body", "")
        if isinstance(reply_body, dict):
            reply_body = reply_body.get("text", "") or reply_body.get("html", "")
        reply_uuid = email_data.get("id") or email_data.get("uuid") or email_data.get("email_id", "")
        campaign_id = email_data.get("campaign_id", "")
        campaign_name = email_data.get("campaign_name", "")
        # eaccount = the sending email account (our alias that sent the campaign)
        eaccount = (email_data.get("eaccount") or
                    email_data.get("to_address_email_list") or
                    email_data.get("to_address_email") or "")

        if not lead_email:
            log("SKIP: No lead email in webhook data")
            return

        log(f"Processing reply from {lead_name} <{lead_email}>")
        log(f"  Subject: {reply_subject[:80]}")
        log(f"  Body preview: {str(reply_body)[:100]}")

        # 1. Classify with GPT
        result = call_openai(lead_email, lead_name, reply_subject, str(reply_body), campaign_name)
        classification = result.get("classification", "unknown")
        reply_text = result.get("reply_body", "")
        confidence = result.get("confidence", 0)
        reason = result.get("reason", "")

        log(f"  Classification: {classification} (confidence: {confidence})")
        log(f"  Reason: {reason}")

        # 2. Skip auto-replies and spam
        if classification in ("auto_reply", "spam") or reply_text == "SKIP":
            log(f"  SKIPPED ({classification})")
            return

        # 3. Send reply via Instantly
        if reply_uuid and reply_text and eaccount and classification in ("interested", "question", "not_interested"):
            try:
                send_result = send_instantly_reply(reply_uuid, reply_text, eaccount, reply_subject)
                log(f"  Reply sent via Instantly (from {eaccount}): {json.dumps(send_result)[:200]}")
            except Exception as e:
                log(f"  Instantly reply error: {e}")
                try: log(f"    {e.read().decode()[:300]}")
                except: pass

        # 4. Update Instantly lead status
        if campaign_id and lead_email:
            if classification == "interested":
                update_instantly_lead_status(lead_email, campaign_id, 1)
            elif classification == "not_interested":
                update_instantly_lead_status(lead_email, campaign_id, 2)

        # 5. Tag in GHL
        contact_id, token, loc = find_ghl_contact(lead_email)
        if contact_id:
            tag_map = {
                "interested": "ai-reply-interested",
                "question": "ai-reply-question",
                "not_interested": "ai-reply-not-interested"
            }
            tag = tag_map.get(classification)
            if tag:
                tag_ghl_contact(contact_id, token, tag)
        else:
            log(f"  No GHL contact found for {lead_email}")

        log(f"  DONE: {classification}")

    except Exception as e:
        log(f"ERROR processing reply: {e}")
        traceback.print_exc()


class ReplyHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode()) if body else {}

            log(f"Webhook received: {json.dumps(data)[:300]}")

            # Respond immediately (webhook expects fast response)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())

            # Process async
            threading.Thread(target=process_reply, args=(data,), daemon=True).start()

        except Exception as e:
            log(f"Webhook handler error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_GET(self):
        """Health check"""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        stats = {"service": "instantly-reply-engine", "status": "running", "port": PORT}
        self.wfile.write(json.dumps(stats).encode())

    def log_message(self, format, *args):
        pass  # suppress default HTTP logging


if __name__ == "__main__":
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY not set")
        exit(1)

    log(f"Starting Instantly Reply Engine on port {PORT}")
    log(f"  Model: {OPENAI_MODEL}")
    log(f"  Webhook: https://dashboard.strsolutionsusa.com/api/instantly-reply")

    server = http.server.HTTPServer(("127.0.0.1", PORT), ReplyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down")
        server.shutdown()
