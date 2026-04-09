#!/usr/bin/env python3
"""Send email via Gmail API using existing OAuth token.
Usage: python3 send-alert-email.py "subject" "body" [recipient]
"""
import sys
import base64
import json
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TOKEN_FILE = "/root/.openclaw/google/token.json"
DEFAULT_TO = "mike@strincsolutions.com"

def get_credentials():
    with open(TOKEN_FILE) as f:
        data = json.load(f)
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes", [])
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token
        data["token"] = creds.token
        with open(TOKEN_FILE, "w") as f:
            json.dump(data, f, indent=2)
    return creds

def send_email(subject, body, to=DEFAULT_TO):
    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    
    msg = MIMEText(body, "plain")
    msg["to"] = to
    msg["subject"] = subject
    
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
    print(f"Email sent: {result.get('id', 'unknown')}")
    return result

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: send-alert-email.py <subject> <body> [recipient]")
        sys.exit(1)
    
    subject = sys.argv[1]
    body = sys.argv[2]
    to = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_TO
    
    try:
        send_email(subject, body, to)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
