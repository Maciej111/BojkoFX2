"""
Unified local dashboard proxy.
Serves index.html on http://localhost:8890
Proxies /api/* to the VM running the unified dashboard app.py.

Usage:
  python dashboard/serve.py

Configure VM address with env vars:
  VM_API=http://34.31.64.224:8080  (default)
  API_KEY=your-key
"""
import http.server
import socketserver
import urllib.request
import urllib.error
import os
from pathlib import Path

PORT          = int(os.environ.get("DASHBOARD_LOCAL_PORT", 8890))
VM_API        = os.environ.get("VM_API",  "http://34.31.64.224:8080")
API_KEY       = os.environ.get("API_KEY", "changeme")
DASHBOARD_DIR = Path(__file__).parent


class ProxyHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def _proxy(self):
        url = VM_API + self.path
        req = urllib.request.Request(url, headers={"X-API-Key": API_KEY})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            self._json_response(e.code, body)
            return
        except Exception as exc:
            body = ('{"error":"' + str(exc).replace('"', "'") + '"}').encode()
            self._json_response(503, body)
            return
        self._json_response(200, body)

    def _json_response(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Suppress noisy access log for /api/* on success
        if args and len(args) >= 2 and "200" in str(args[1]) and "/api/" in str(args[0]):
            return
        super().log_message(fmt, *args)


class _ConcurrentProxy(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with _ConcurrentProxy(("", PORT), ProxyHandler) as httpd:
        print(f"Dashboard: http://localhost:{PORT}")
        print(f"Proxying /api/* → {VM_API}")
        print("Press Ctrl+C to stop.")
        httpd.serve_forever()
