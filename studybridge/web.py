"""Local web UI (standard library only).

Security choices: binds to 127.0.0.1 only; every POST needs JSON plus the
custom X-StudyBridge header (a cross-site form cannot set it, which blocks
CSRF); request bodies are capped at 8 KB; responses carry a strict CSP and
the page renders all text with textContent, never innerHTML.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import PACKAGE_ROOT
from .config import HOME_CURRENCY

STATIC = PACKAGE_ROOT / "static"
MAX_BODY = 8 * 1024
_FILES = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}


def _make_handler(agent):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, body: bytes, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, default=str).encode())

        def do_GET(self):
            if self.path in _FILES:
                name, ctype = _FILES[self.path]
                return self._send(200, (STATIC / name).read_bytes(), ctype)
            if self.path == "/api/wallet":
                with lock:
                    return self._json(200, {**agent.wallet.overview(HOME_CURRENCY),
                                            "tier": agent.session.granted_tier.name})
            if self.path == "/api/audit/verify":
                return self._json(200, agent.audit.verify())
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.headers.get("X-StudyBridge") != "1" or \
                    not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json(403, {"error": "missing required header"})
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_BODY:
                return self._json(413, {"error": "request too large"})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return self._json(400, {"error": "invalid JSON"})
            with lock:
                if self.path == "/api/chat":
                    resp = agent.handle(str(body.get("message", ""))[:1000])
                elif self.path == "/api/confirm":
                    resp = agent.confirm(str(body.get("id", "")))
                elif self.path == "/api/cancel":
                    resp = agent.cancel(str(body.get("id", "")))
                else:
                    return self._json(404, {"error": "not found"})
            self._json(200, {"text": resp.text, "intent": resp.intent, "blocked": resp.blocked,
                             "pending": resp.pending_action, "parse_source": resp.parse_source,
                             "guard_removed": resp.guard_removed})

    return Handler


def serve(agent, port: int = 8765, host: str = "127.0.0.1"):
    server = ThreadingHTTPServer((host, port), _make_handler(agent))
    print(f"StudyBridge web UI on http://{host}:{port}  (tier {agent.session.granted_tier.name}, "
          f"LLM {'on' if agent.llm else 'off'})  Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
