"""
Pure YouTube search + parse logic, with no MPV2 dependencies.

This module scrapes the public YouTube search results page (no Data API key
required), extracts the embedded ``ytInitialData`` JSON blob, walks it for every
``videoRenderer`` entry, and normalizes each into a flat dict. It only depends
on ``requests`` so it can be reused anywhere — the CLI ``VideoFinder`` class and
the standalone web app both build on top of it.

Only public metadata (video id, title, channel, duration, view count) is
collected; no media is downloaded.

NOTE: ``webapp/api/_youtube.py`` is a vendored copy of this module so the web
app can deploy as an isolated unit. Keep the two in sync when the parsing logic
changes.
"""

import json

import requests

from typing import List, Optional

# Public YouTube search endpoint. The results page ships an embedded
# ``ytInitialData`` JSON blob that we parse directly.
YOUTUBE_SEARCH_URL = "https://www.youtube.com/results"

# The ``sp`` parameter is YouTube's URL-safe search filter token. This value
# ("EgIQAQ==") restricts results to the "Video" type, dropping channels,
# playlists and shelves from the response.
VIDEO_ONLY_FILTER = "EgIQAQ=="

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Skips the EU cookie-consent interstitial, which otherwise replaces the
# results page (and its ytInitialData blob) with a consent form.
REQUEST_COOKIES = {"CONSENT": "YES+cb"}


def search_youtube(
    query: str,
    max_results: int = 15,
    must_match: Optional[List[str]] = None,
    timeout: int = 30,
) -> List[dict]:
    """
    Searches YouTube and returns matching, normalized video records.

    Args:
        query (str): The search query.
        max_results (int): Maximum number of videos to return.
        must_match (Optional[List[str]]): Case-insensitive terms; a video is
            kept when any appears in its title, channel or description. Pass
            None or an empty list to keep every result.
        timeout (int): Per-request timeout in seconds.

    Returns:
        videos (List[dict]): Normalized records, capped at ``max_results``.
            Empty when the page cannot be parsed.

    Raises:
        requests.RequestException: If the HTTP request fails.
    """
    terms = [term.strip().lower() for term in (must_match or []) if term.strip()]

    response = requests.get(
        YOUTUBE_SEARCH_URL,
        params={"search_query": query, "sp": VIDEO_ONLY_FILTER},
        headers=REQUEST_HEADERS,
        cookies=REQUEST_COOKIES,
        timeout=timeout,
    )
    response.raise_for_status()

    data = extract_initial_data(response.text)
    if not data:
        return []

    videos = parse_videos(data)
    matches = [video for video in videos if matches_filter(video, terms)]

    if max_results and max_results > 0:
        matches = matches[:max_results]

    return matches


def extract_initial_data(html: str) -> dict:
    """
    Extracts and parses the ``ytInitialData`` JSON object from page HTML.

    Args:
        html (str): The raw search results page HTML.

    Returns:
        data (dict): The parsed object, or an empty dict if not found.
    """
    marker = "ytInitialData"
    idx = html.find(marker)

    while idx != -1:
        brace_start = html.find("{", idx)
        if brace_start == -1:
            return {}

        # Only treat this as an assignment (``ytInitialData = {...}``), not an
        # incidental mention elsewhere in the page.
        if "=" in html[idx + len(marker):brace_start]:
            json_str = _match_braces(html, brace_start)
            if json_str:
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass

        idx = html.find(marker, brace_start)

    return {}


def _match_braces(text: str, start: int) -> str:
    """
    Returns the balanced ``{...}`` substring beginning at ``start``.

    Walks the text tracking brace depth while ignoring braces that appear inside
    JSON string literals (respecting backslash escapes).

    Args:
        text (str): The text to scan.
        start (int): Index of the opening ``{``.

    Returns:
        substring (str): The balanced object, or "" if unbalanced.
    """
    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        char = text[i]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

    return ""


def parse_videos(data: dict) -> List[dict]:
    """
    Collects and normalizes every video renderer in the parsed data.

    Args:
        data (dict): The parsed ``ytInitialData`` object.

    Returns:
        videos (List[dict]): De-duplicated normalized video records.
    """
    renderers: List[dict] = []
    _collect_renderers(data, renderers)

    videos: List[dict] = []
    seen = set()

    for renderer in renderers:
        video = normalize_renderer(renderer)
        if video and video["video_id"] not in seen:
            seen.add(video["video_id"])
            videos.append(video)

    return videos


def _collect_renderers(node, out: List[dict]) -> None:
    """
    Recursively collects every ``videoRenderer`` dict found under ``node``.

    Args:
        node: An arbitrary JSON node (dict, list or scalar).
        out (List[dict]): Accumulator for discovered renderers.

    Returns:
        None
    """
    if isinstance(node, dict):
        renderer = node.get("videoRenderer")
        if isinstance(renderer, dict):
            out.append(renderer)
        for value in node.values():
            _collect_renderers(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_renderers(item, out)


def normalize_renderer(renderer: dict) -> Optional[dict]:
    """
    Converts a raw ``videoRenderer`` into a flat record.

    Args:
        renderer (dict): A single YouTube video renderer.

    Returns:
        video (Optional[dict]): The normalized record, or None if it has no
            video id.
    """
    video_id = renderer.get("videoId")
    if not video_id:
        return None

    description = ""
    snippets = renderer.get("detailedMetadataSnippets")
    if isinstance(snippets, list) and snippets and isinstance(snippets[0], dict):
        description = read_text(snippets[0].get("snippetText"))

    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": read_text(renderer.get("title")),
        "channel": (
            read_text(renderer.get("ownerText"))
            or read_text(renderer.get("longBylineText"))
        ),
        "duration": read_text(renderer.get("lengthText")) or "N/A",
        "views": read_text(renderer.get("viewCountText")),
        "published": read_text(renderer.get("publishedTimeText")),
        "description": description,
    }


def read_text(node) -> str:
    """
    Reads a YouTube text node, which is either ``{"simpleText": ...}`` or
    ``{"runs": [{"text": ...}, ...]}``.

    Args:
        node: The text node.

    Returns:
        text (str): The concatenated text, or "" when unavailable.
    """
    if not isinstance(node, dict):
        return ""

    if "simpleText" in node:
        return node["simpleText"]

    runs = node.get("runs")
    if isinstance(runs, list):
        return "".join(run.get("text", "") for run in runs if isinstance(run, dict))

    return ""


def matches_filter(video: dict, must_match: List[str]) -> bool:
    """
    Checks whether a video satisfies the ``must_match`` filter.

    Args:
        video (dict): A normalized video record.
        must_match (List[str]): Lower-cased terms. Empty disables filtering.

    Returns:
        matches (bool): True when filtering is disabled or any term is present
            in the title, channel or description.
    """
    if not must_match:
        return True

    haystack = f"{video['title']} {video['channel']} {video['description']}".lower()
    return any(term in haystack for term in must_match)
