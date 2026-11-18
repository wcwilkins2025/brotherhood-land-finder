"""Serve downloads/store/out on http://127.0.0.1:8793 the way Cloudflare R2 will: byte-range
requests for the soil grids, gzip-encoded JSON shards, and open CORS. For testing on this PC only."""
import http.server, os, re, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'downloads', 'store', 'out'))


class H(http.server.BaseHTTPRequestHandler):
    def _path(self):
        p = self.path.split('?', 1)[0].lstrip('/')
        f = os.path.normpath(os.path.join(ROOT, p))
        if not f.startswith(ROOT):
            return None
        if not os.path.exists(f) and p.startswith('wells/'):
            f = os.path.join(ROOT, 'wells.test', p[len('wells/'):])     # test well set
        return f if os.path.isfile(f) else None

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Range')
        self.send_header('Access-Control-Expose-Headers', 'Content-Range, Content-Length, Accept-Ranges')

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        f = self._path()
        if not f:
            self.send_response(404); self._cors(); self.end_headers(); return
        data = open(f, 'rb').read()
        gz = f.endswith('.json') and data[:2] == b'\x1f\x8b'
        ctype = 'application/json' if f.endswith('.json') else 'image/tiff'
        rng = self.headers.get('Range')
        m = re.match(r'bytes=(\d+)-(\d*)', rng or '')
        if m and not gz:
            a = int(m.group(1)); b = int(m.group(2)) if m.group(2) else len(data) - 1
            b = min(b, len(data) - 1); part = data[a:b + 1]
            self.send_response(206); self._cors()
            self.send_header('Content-Range', f'bytes {a}-{b}/{len(data)}')
            self.send_header('Content-Type', ctype); self.send_header('Accept-Ranges', 'bytes'); self.send_header('Content-Length', str(len(part)))
            self.end_headers(); self.wfile.write(part); return
        self.send_response(200); self._cors()
        self.send_header('Content-Type', ctype); self.send_header('Accept-Ranges', 'bytes'); self.send_header('Content-Length', str(len(data)))
        if gz:
            self.send_header('Content-Encoding', 'gzip')
        self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    http.server.ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1]) if len(sys.argv) > 1 else 8793), H).serve_forever()
