"""The picker page's tiny local server: serves studio/ and engine/, reads and writes ~/.reel-studio/config.json.

  python3 studio_server.py [port]      (reel.py studio starts it detached and opens the browser)

GET  /                 the picker page
GET  /engine.js        the shared caption engine (the page previews with the very code that renders)
GET  /api/config       current config (defaults merged)
POST /api/config       save config  -> {"ok": true, "path": "..."}
GET  /api/custom-fonts families found in ~/.reel-studio/fonts/custom/
"""
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from common import STUDIO, ENGINE, FONTS_DIR, CFG_DIR, load_config, save_config, deep_merge, DEFAULT_CONFIG

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7788


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STUDIO), **kw)

    def log_message(self, *a):  # quiet
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith('/api/config'):
            return self._json(DEFAULT_CONFIG if 'defaults=1' in self.path else load_config())
        if self.path.startswith('/api/custom-fonts'):
            custom = FONTS_DIR / 'custom'
            fams = sorted({p.stem.split('-')[0].replace('_', ' ') for p in custom.iterdir()
                           if p.suffix.lower() in ('.ttf', '.otf', '.woff', '.woff2')}) if custom.exists() else []
            return self._json({"families": fams, "dir": str(custom)})
        if self.path.startswith('/engine.js'):
            data = (ENGINE / 'engine.js').read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return self.wfile.write(data)
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith('/api/config'):
            n = int(self.headers.get('Content-Length') or 0)
            try:
                incoming = json.loads(self.rfile.read(n).decode('utf-8'))
                cfg = deep_merge(DEFAULT_CONFIG, incoming)
                path = save_config(cfg)
                return self._json({"ok": True, "path": str(path)})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)}, 400)
        self.send_error(404)


if __name__ == '__main__':
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    (CFG_DIR / 'studio.pid').write_text(str(os.getpid()))
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), H)
    print(f'http://127.0.0.1:{PORT}/', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
