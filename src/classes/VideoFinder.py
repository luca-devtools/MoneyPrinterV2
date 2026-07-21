import requests

from cache import add_video_finds
from typing import List, Optional
from config import get_larry_david_config, get_verbose
from status import info, success, warning, error
from termcolor import colored
from prettytable import PrettyTable
from lib.youtube_search import search_youtube


class VideoFinder:
    """
    Identifies videos on YouTube that match a search query (Larry David /
    Curb Your Enthusiasm by default) by reading the public search results page.

    The heavy lifting (fetch, ``ytInitialData`` extraction, parsing and
    filtering) lives in :mod:`lib.youtube_search`; this class adds the MPV2
    concerns on top: config-driven defaults, terminal display and caching.

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
            videos = search_youtube(self.query, self.max_results, self.must_match)
        except requests.RequestException as e:
            error(f"Failed to fetch YouTube search results: {e}")
            return []

        if not videos:
            warning("No matching videos found (or the page format may have changed).")

        if get_verbose():
            info(f" => Found {len(videos)} matching video(s).", False)

        return videos

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
