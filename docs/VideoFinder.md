# Find Larry David Videos

The **Find Larry David Videos** option (menu item 5) identifies existing videos
on YouTube that match a search query — by default, Larry David / *Curb Your
Enthusiasm* content. It is a discovery tool: it surfaces public video metadata
(id, title, channel, duration, view count) so you can source ideas or track what
is out there. It does **not** download any media, keeping in line with the
project's original-content approach.

## How it works

MPV2 requests the public YouTube search results page (no Data API key required),
extracts the embedded `ytInitialData` JSON blob, and reads every video entry out
of it. Results are filtered by the `must_match` terms and capped at
`max_results`.

The request restricts results to the "Video" type and sends a consent cookie so
the EU cookie-consent interstitial does not replace the results page.

## Usage

From the main menu:

```
5. Find Larry David Videos
```

You are prompted for:

- **Search query** — press Enter to accept the configured default.
- **Max results** — press Enter to accept the configured default.

Results are printed as a table. You are then asked whether to save them to the
cache.

## Caching

Saved videos are stored in `.mp/video_finds.json`, de-duplicated by video id:

```json
{
    "videos": [
        {
            "video_id": "dQw4w9WgXcQ",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "title": "...",
            "channel": "...",
            "duration": "2:34",
            "views": "1,234,567 views",
            "published": "3 years ago",
            "description": "..."
        }
    ]
}
```

## Configuration

The `larry_david` block in `config.json` is optional; every value has a default,
so omitting the block is fine. See [Configuration.md](./Configuration.md) for the
field reference.

```json
"larry_david": {
    "search_query": "Larry David Curb Your Enthusiasm",
    "max_results": 15,
    "must_match": ["larry david", "curb"]
}
```

Set `must_match` to `[]` to keep every result the search returns, or change
`search_query` to reuse the finder for any other topic.

## Programmatic use

```python
from classes.VideoFinder import VideoFinder

finder = VideoFinder(query="Larry David interview", max_results=10)
videos = finder.search()
finder.display(videos)
finder.save(videos)
```
