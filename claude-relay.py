import os, json
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request, urllib.error

OPENAI_KEY = os.environ.get('OPENAI_API_KEY', '')
MODEL = 'gpt-4o'
SYSTEM = 'You are an AI strategist embedded in the STR Solutions USA command center. STR Solutions is a short-term rental management company. The founder is Mike. Full tech stack: GoHighLevel CRM (Master + Call Center accounts), OpenClaw Discord AI agent, SwarmClaw multi-agent runtime, Flowise AI workflows, Vapi voice AI, Instantly email outreach, Apollo lead gen, Hostfully property management (44 properties), AirDNA market data, Digital Ocean droplet at 134.209.11.87. Be concise, direct, and strategic. Reference actual tools when discussing operations.'

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()
    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            message = body.get('question') or body.get('message') or body.get('text', '')
            history = body.get('history', [])
            messages = [{'role': 'system', 'content': SYSTEM}]
            for h in history[-10:]:
                if h.get('role') and h.get('content'):
                    messages.append({'role': h['role'], 'content': h['content']})
            messages.append({'role': 'user', 'content': message})
            payload = json.dumps({'model': MODEL, 'max_tokens': 1024, 'messages': messages}).encode()
            req = urllib.request.Request('https://api.openai.com/v1/chat/completions', data=payload,
                headers={'Authorization': f'Bearer {OPENAI_KEY}', 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            text = data['choices'][0]['message']['content']
            self.send_response(200); self._cors()
            self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(json.dumps({'text': text}).encode())
        except Exception as e:
            self.send_response(500); self._cors()
            self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 19876))
    print(f'STR relay on :{port}')
    HTTPServer(('127.0.0.1', port), Handler).serve_forever()
