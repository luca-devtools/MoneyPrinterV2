import json

import requests

from cache import add_video_finds
from typing import List, Optional
from config import get_larry_david_config, get_verbose
from status import info, success, warning, error
from termcolor import colored
from prettytable import PrettyTable

# Public YouTube search endpoint. No Data API key is required — the results
# page ships an embedded ``ytInitialData`` JSON blob that we parse directly.
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


class VideoFinder:
    """
    Identifies videos on YouTube that match a search query (Larry David /
    Curb Your Enthusiasm by default) by reading the public search results page.

    No YouTube Data API key is required. The class fetches the search results
    HTML, extracts the embedded ``ytInitialData`` JSON blob, walks it for every
    ``videoRenderer`` entry, and normalizes each into a plain dict. Results can
    be persisted to the ``.mp`` cache so the other MPV2 workflows can reuse them.

    Only public metadata (video id, title, channel, duration, view count) is
    collected — no media is downloaded, matching the project's original-content
    posture.
    """

    def __init__(
        self,
        query: Optional[str] = None,
        max_results: Optional[int] = None,
        must_match: Optional[List[str]] = None,
    ) -> None:
        """
        Constructor for the VideoFinder class.

        Args:
            query (Optional[str]): The search query. Falls back to the configured
                default when empty.
            max_results (Optional[int]): Maximum number of videos to return.
                Falls back to the configured default when not a positive int.
            must_match (Optional[List[str]]): Case-insensitive substrings; a
                video is kept when any appears in its title, channel or
                description. Falls back to the configured terms when None; pass
                an empty list to disable filtering.

        Returns:
            None
        """
        config = get_larry_david_config()

        self.query: str = (query or config["search_query"]).strip() or config["search_query"]

        if isinstance(max_results, int) and max_results > 0:
            self.max_results: int = max_results
        else:
            self.max_results = config["max_results"]

        if must_match is None:
            self.must_match: List[str] = config["must_match"]
        else:
            self.must_match = [term.strip().lower() for term in must_match if term.strip()]

    def search(self) -> List[dict]:
        """
        Runs the search and returns the matching videos.

        Returns:
            videos (List[dict]): Normalized video records, capped at
                ``max_results``. Empty on network or parse failure.
        """
        if get_verbose():
            info(f" => Searching YouTube for: {self.query}", False)

        try:
            response = requests.get(
                YOUTUBE_SEARCH_URL,
                params={"search_query": self.query, "sp": VIDEO_ONLY_FILTER},
                headers=REQUEST_HEADERS,
                cookies=REQUEST_COOKIES,
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            error(f"Failed to fetch YouTube search results: {e}")
            return []

        data = self._extract_initial_data(response.text)
        if not data:
            warning("Could not parse YouTube search results (page format may have changed).")
            return []

        videos = self._parse_videos(data)
        matches = [video for video in videos if self._matches_filter(video)]

        if get_verbose():
            info(f" => Found {len(matches)} matching video(s).", False)

        return matches[: self.max_results]

    @staticmethod
    def _extract_initial_data(html: str) -> dict:
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

            # Only treat this as an assignment (``ytInitialData = {...}``), not
            # an incidental mention elsewhere in the page.
            if "=" in html[idx + len(marker):brace_start]:
                json_str = VideoFinder._match_braces(html, brace_start)
                if json_str:
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        pass

            idx = html.find(marker, brace_start)

        return {}

    @staticmethod
    def _match_braces(text: str, start: int) -> str:
        """
        Returns the balanced ``{...}`` substring beginning at ``start``.

        Walks the text tracking brace depth while ignoring braces that appear
        inside JSON string literals (respecting backslash escapes).

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

    def _parse_videos(self, data: dict) -> List[dict]:
        """
        Collects and normalizes every video renderer in the parsed data.

        Args:
            data (dict): The parsed ``ytInitialData`` object.

        Returns:
            videos (List[dict]): De-duplicated normalized video records.
        """
        renderers: List[dict] = []
        self._collect_renderers(data, renderers)

        videos: List[dict] = []
        seen = set()

        for renderer in renderers:
            video = self._normalize_renderer(renderer)
            if video and video["video_id"] not in seen:
                seen.add(video["video_id"])
                videos.append(video)

        return videos

    @staticmethod
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
                VideoFinder._collect_renderers(value, out)
        elif isinstance(node, list):
            for item in node:
                VideoFinder._collect_renderers(item, out)

    @staticmethod
    def _normalize_renderer(renderer: dict) -> Optional[dict]:
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
            description = VideoFinder._read_text(snippets[0].get("snippetText"))

        return {
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "title": VideoFinder._read_text(renderer.get("title")),
            "channel": (
                VideoFinder._read_text(renderer.get("ownerText"))
                or VideoFinder._read_text(renderer.get("longBylineText"))
            ),
            "duration": VideoFinder._read_text(renderer.get("lengthText")) or "N/A",
            "views": VideoFinder._read_text(renderer.get("viewCountText")),
            "published": VideoFinder._read_text(renderer.get("publishedTimeText")),
            "description": description,
        }

    @staticmethod
    def _read_text(node) -> str:
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

    def _matches_filter(self, video: dict) -> bool:
        """
        Checks whether a video satisfies the ``must_match`` filter.

        Args:
            video (dict): A normalized video record.

        Returns:
            matches (bool): True when filtering is disabled or any term is
                present in the title, channel or description.
        """
        if not self.must_match:
            return True

        haystack = f"{video['title']} {video['channel']} {video['description']}".lower()
        return any(term in haystack for term in self.must_match)

    def display(self, videos: List[dict]) -> None:
        """
        Prints the videos as a table.

        Args:
            videos (List[dict]): Normalized video records.

        Returns:
            None
        """
        if not videos:
            warning("No matching videos found.")
            return

        table = PrettyTable()
        table.field_names = ["#", "Video ID", "Title", "Channel", "Duration", "Views"]
        table.align["Title"] = "l"
        table.align["Channel"] = "l"

        for idx, video in enumerate(videos):
            title = video["title"]
            display_title = title[:50] + ("..." if len(title) > 50 else "")
            table.add_row([
                idx + 1,
                colored(video["video_id"], "cyan"),
                colored(display_title, "green"),
                colored(video["channel"][:24], "blue"),
                video["duration"],
                video["views"],
            ])

        print(table)

    def save(self, videos: List[dict]) -> int:
        """
        Persists the videos to the ``.mp`` cache, skipping duplicates.

        Args:
            videos (List[dict]): Normalized video records.

        Returns:
            added (int): The number of newly stored videos.
        """
        added = add_video_finds(videos)

        if get_verbose():
            success(f" => Cached {added} new video(s).", False)

        return added
