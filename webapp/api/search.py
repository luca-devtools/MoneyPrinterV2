"""
Vercel Python serverless function: GET /api/search

Query params:
    q       search query (default: "Larry David Curb Your Enthusiasm")
    max     max results, 1..50 (default: 15)
    filter  "1"/"0" — when truthy, keep only Larry David / Curb results (default: 1)

Returns JSON: {ok, query, count, videos:[...]} or {ok:false, error}.
"""

import os
import sys
import json

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.append(os.path.dirname(__file__))

from _handler import run_search


def _truthy(value: str) -> bool:
    return str(value).strip().lower() not in ("0", "false", "no", "")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)

        status, payload = run_search(
            q=params.get("q", [""])[0],
            max_results=params.get("max", ["15"])[0],
            only_larry_david=_truthy(params.get("filter", ["1"])[0]),
        )

        body = json.dumps(payload).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep serverless logs quiet
        pass
