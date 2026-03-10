"""
Local dashboard proxy server.
Serves index.html on http://localhost:8891
Proxies all /api/* to VM (no CORS issues).
Usage: python dashboard/serve.py
"""
import http.server
import socketserver
import urllib.request
import urllib.error
import socket
import os
from pathlib import Path

PORT          = 8890
VM_API        = "http://34.31.64.224:8080"
API_KEY       = "0ea9522009779654decab58134a352e6"
DASHBOARD_DIR = Path(__file__).parent


class ProxyHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            # Static files — add no-cache via standard flow
            super().do_GET()

    def end_headers(self):
        """Add no-cache only for static files (not called from _proxy)."""
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def _proxy(self):
        """Forward /api/* to VM — bypasses browser CORS."""
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
        self.send_header("Content-Length", str(len(body)))
        # Use base class end_headers to avoid double no-cache headers
        http.server.BaseHTTPRequestHandler.end_headers(self)
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # silent


class ReuseServer(socketserver.TCPServer):
    allow_reuse_address = True
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()


if __name__ == "__main__":
    os.chdir(DASHBOARD_DIR)
    with ReuseServer(("", PORT), ProxyHandler) as httpd:
        print(f"Dashboard: http://localhost:{PORT}")
        print(f"Proxying /api/* -> {VM_API}")
        print("Ctrl+C to stop.")
        httpd.serve_forever()

