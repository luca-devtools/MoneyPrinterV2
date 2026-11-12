"""
Shared search-request logic used by both the Vercel serverless function
(``api/search.py``) and the local dev server (``server.py``).

Kept separate so the two entry points behave identically.
"""

import os
import sys

sys.path.append(os.path.dirname(__file__))

from _youtube import search_youtube

DEFAULT_QUERY = "Larry David Curb Your Enthusiasm"
DEFAULT_MUST_MATCH = ["larry david", "curb"]
MAX_RESULTS_CAP = 50


def run_search(q=None, max_results=15, only_larry_david=True):
    """
    Runs a YouTube search and returns an (http_status, payload) tuple.

    Args:
        q: The raw query string (falls back to the default when blank).
        max_results: Requested result count (clamped to 1..MAX_RESULTS_CAP).
        only_larry_david (bool): When True, keep only Larry David / Curb results.

    Returns:
        (status, payload): HTTP status code and a JSON-serializable dict.
    """
    query = (q or "").strip() or DEFAULT_QUERY

    try:
        count = int(max_results)
    except (TypeError, ValueError):
        count = 15
    count = max(1, min(count, MAX_RESULTS_CAP))

    must_match = DEFAULT_MUST_MATCH if only_larry_david else []

    try:
        videos = search_youtube(query, count, must_match)
        return 200, {
            "ok": True,
            "query": query,
            "count": len(videos),
            "videos": videos,
        }
    except Exception as exc:  # network failure, unexpected page, etc.
        return 502, {
            "ok": False,
            "error": f"Failed to fetch YouTube results: {exc}",
        }
