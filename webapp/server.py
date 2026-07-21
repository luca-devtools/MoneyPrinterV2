"""
Local development server for the MPV2 video finder web app.

Serves the static pages in ``public/`` and handles ``GET /api/search`` using the
same logic as the deployed Vercel function — so ``python server.py`` gives you
the exact hosted behavior on ``http://localhost:8000``.

Only depends on the standard library plus ``requests`` (via the search module).
"""

import os
import sys
import json

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(HERE, "public")

sys.path.insert(0, os.path.join(HERE, "api"))

from _handler import run_search


def _truthy(value: str) -> bool:
    return str(value).strip().lower() not in ("0", "false", "no", "")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            status, payload = run_search(
                q=params.get("q", [""])[0],
                max_results=params.get("max", ["15"])[0],
                only_larry_david=_truthy(params.get("filter", ["1"])[0]),
            )
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        # Pretty routes -> static files.
        if parsed.path == "/":
            self.path = "/index.html"
        elif parsed.path == "/saved":
            self.path = "/saved.html"

        return super().do_GET()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"MPV2 video finder → http://localhost:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping…")
        server.shutdown()


if __name__ == "__main__":
    main()
