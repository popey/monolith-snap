#!/usr/bin/env python3
"""Exercise only a test-owned loopback page and its CSS/image assets."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
from pathlib import Path
import re
import subprocess
import tempfile
import threading
from urllib.parse import unquote_to_bytes

artifacts = Path('artifacts')
artifacts.mkdir(exist_ok=True)
expected = re.search(r"(?m)^version: 'v?([^']+)'$", Path('snap/snapcraft.yaml').read_text()).group(1)
version = subprocess.run(['snap', 'run', 'monolith', '--version'], capture_output=True, text=True, timeout=30, check=True)
(artifacts / 'version.log').write_text(version.stdout)
assert re.search(r'(?<![0-9.])' + re.escape(expected) + r'(?![0-9.])', version.stdout), version.stdout
assets = {
    '/index.html': ('text/html', b'<html><head><link rel="stylesheet" href="/style.css"></head><body><h1>Snapstead archive fixture</h1><img src="/image.svg"></body></html>'),
    '/style.css': ('text/css', b'h1 { color: #123456; }'),
    '/image.svg': ('image/svg+xml', b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="red"/></svg>'),
}
requests = set()
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in assets:
            self.send_error(404)
            return
        requests.add(self.path)
        mime, content = assets[self.path]
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.end_headers()
        self.wfile.write(content)
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    # A non-hidden home path is accessible through the snap's home interface.
    with tempfile.TemporaryDirectory(prefix='snapstead-monolith-', dir=Path.home()) as tmp:
        output = Path(tmp) / 'archive.html'
        result = subprocess.run(['snap', 'run', 'monolith', f'http://127.0.0.1:{server.server_port}/index.html', '-o', str(output)], capture_output=True, text=True, timeout=60, check=True)
        (artifacts / 'archive.log').write_text(result.stdout + result.stderr)
        document = output.read_text()
        assert 'Snapstead archive fixture' in document
        embedded = {}
        for metadata, payload in re.findall(r'data:([^,"\s]*),([^"\s]*)', html.unescape(document)):
            mime = metadata.split(';')[0]
            embedded[mime] = base64.b64decode(payload) if ';base64' in metadata else unquote_to_bytes(payload)
        assert embedded.get('image/svg+xml') == assets['/image.svg'][1], 'Image was not embedded'
        assert b'#123456' in embedded.get('text/css', b''), 'Stylesheet was not embedded'
        assert set(assets) <= requests, requests
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
print('Installed version and loopback HTML/CSS/image archive checks passed')
