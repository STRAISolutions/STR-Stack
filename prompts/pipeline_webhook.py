#!/usr/bin/env python3
"""
Minimal HTTP server that triggers str_pipeline.py when POST /run is called.
Used by n8n to manually trigger or inspect the pipeline.
Runs on port 9876 (loopback only).
"""
import http.server, subprocess, json, threading, os, sys
from datetime import datetime

PORT = 9876
SCRIPT = "/root/str-stack/prompts/run_pipeline.sh"
LOG = "/root/str-stack/prompts/pipeline.log"
last_result = {"status": "idle", "ran_at": None, "summary": ""}

def run_pipeline(args=None):
    global last_result
    last_result = {"status": "running", "ran_at": datetime.utcnow().isoformat(), "summary": ""}
    cmd = [SCRIPT] + (args or [])
    env = os.environ.copy()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, env=env)
        out = result.stdout[-3000:]
        last_result = {
            "status": "ok" if result.returncode == 0 else "error",
            "ran_at": datetime.utcnow().isoformat(),
            "summary": out,
            "returncode": result.returncode,
        }
    except Exception as e:
        last_result = {"status": "error", "ran_at": datetime.utcnow().isoformat(), "summary": str(e)}

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == "/status":
            self._json(last_result)
        elif self.path == "/health":
            self._json({"ok": True})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/run":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            args = body.get("args", [])
            t = threading.Thread(target=run_pipeline, args=(args,), daemon=True)
            t.start()
            self._json({"status": "started", "ran_at": datetime.utcnow().isoformat()})
        else:
            self._json({"error": "not found"}, 404)

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Pipeline webhook on http://127.0.0.1:{PORT}", flush=True)
    server.serve_forever()
