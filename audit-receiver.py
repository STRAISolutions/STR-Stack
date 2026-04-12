#!/usr/bin/env python3
"""Lightweight HTTP receiver for audit JSON uploads from Kristine's PC.
Listens on port 9450 (Tailscale only — not exposed to internet)."""

import json, os, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

SAVE_DIR = '/root/str-stack/task-mining/kristine'
PUBLIC_DIR = '/srv/str-stack-public/task-mining'

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            hostname = data.get('meta', {}).get('hostname', 'unknown')
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            fname = f'audit_{hostname}_{ts}.json'
            path = os.path.join(SAVE_DIR, fname)
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            # Also copy to public dir for dashboard access
            pub_path = os.path.join(PUBLIC_DIR, fname)
            with open(pub_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f'[{ts}] Saved audit from {hostname}: {path}')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'file': fname}).encode())
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def log_message(self, fmt, *args):
        pass  # suppress default logging

if __name__ == '__main__':
    os.makedirs(SAVE_DIR, exist_ok=True)
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    server = HTTPServer(('0.0.0.0', 9450), Handler)
    print(f'Audit receiver listening on :9450 — saving to {SAVE_DIR}')
    server.serve_forever()
