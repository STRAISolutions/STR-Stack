#!/usr/bin/env python3
"""ElevenLabs TTS proxy server — runs on port 8501, proxied by nginx at /api/tts"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json, urllib.request, os, sys

ELEVEN_KEY = os.environ.get('ELEVENLABS_API_KEY', 'sk_a601e26ca5b67989b6624529959045ed3be27b0f1657cdfc')
DEFAULT_VOICE = 'c2O7ZagKqb05VCpb66Qc'  # Lily (natural female)
MODEL = 'eleven_turbo_v2_5'
MAX_CHARS = 500

class TTSHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/api/tts':
            self.send_response(404)
            self.end_headers()
            return

        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Bad JSON')
            return

        text = body.get('text', '')[:MAX_CHARS]
        voice = body.get('voice', DEFAULT_VOICE)

        if not text.strip():
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'No text')
            return

        url = f'https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream'
        payload = json.dumps({
            'text': text,
            'model_id': MODEL,
            'voice_settings': {
                'stability': 0.5,
                'similarity_boost': 0.75,
                'style': 0.3,
                'use_speaker_boost': True
            }
        }).encode()

        req = urllib.request.Request(url, data=payload, method='POST', headers={
            'Content-Type': 'application/json',
            'xi-api-key': ELEVEN_KEY,
            'Accept': 'audio/mpeg'
        })

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                audio = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg')
                self.send_header('Content-Length', str(len(audio)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(audio)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f'TTS error: {e}'.encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f'[tts-proxy] {args[0]}')

if __name__ == '__main__':
    port = 8501
    server = HTTPServer(('127.0.0.1', port), TTSHandler)
    print(f'[tts-proxy] ElevenLabs TTS proxy on :{port}')
    server.serve_forever()
