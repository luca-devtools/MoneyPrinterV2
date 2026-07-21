# Larry David Video Finder — Web App

A small, self-contained web version of the MPV2 "Find Larry David Videos"
feature: search YouTube for Larry David / *Curb Your Enthusiasm* clips and save
the ones you want.

It is deliberately isolated from the CLI (its own `requirements.txt` with just
`requests`) so it deploys cleanly to a serverless host without pulling in the
heavy CLI dependencies (MoviePy, Selenium, etc.).

## Layout

```
webapp/
├── api/
│   ├── search.py     # Vercel serverless function → GET /api/search
│   ├── _handler.py   # shared request logic (used by the function and dev server)
│   └── _youtube.py   # vendored copy of src/lib/youtube_search.py (fetch + parse)
├── public/
│   ├── index.html    # search page
│   ├── saved.html    # saved-videos page
│   ├── app.js        # shared client logic
│   └── styles.css
├── server.py         # local dev server (stdlib) with the same behavior as Vercel
├── requirements.txt  # requests
└── vercel.json
```

## Run locally

From the `webapp/` directory:

```bash
pip install -r requirements.txt
python server.py
# open http://localhost:8000   (PORT env var overrides the port)
```

The dev server serves the static pages and handles `GET /api/search` with the
exact logic the deployed function uses.

## Deploy to Vercel

The app is configured as a Vercel project rooted at this `webapp/` directory.

**Vercel CLI:**

```bash
cd webapp
npx vercel        # first run links/creates the project (follow the prompts)
npx vercel --prod # deploy to production
```

**Vercel dashboard / Git import:** import the repository and set the project's
**Root Directory** to `webapp`. Vercel auto-detects `api/search.py` as a Python
serverless function and serves `public/` as static assets. No build step or env
vars are required.

After deploy:
- `/` — search page
- `/saved` — saved videos
- `/api/search?q=...&max=15&filter=1` — JSON API

## API

`GET /api/search`

| param    | default                             | notes                                          |
|----------|-------------------------------------|------------------------------------------------|
| `q`      | `Larry David Curb Your Enthusiasm`  | search query                                   |
| `max`    | `15`                                | result cap, clamped to 1–50                    |
| `filter` | `1`                                 | `1` = only Larry David / Curb; `0` = keep all  |

Response: `{ "ok": true, "query": "...", "count": N, "videos": [ ... ] }`
or, on failure, `{ "ok": false, "error": "..." }` with HTTP 502.

## Notes & caveats

- **Persistence is client-side.** Saved videos live in the browser's
  `localStorage` (key `mpv2.savedVideos`), not in a database and not synced with
  the CLI's `.mp/video_finds.json`. This keeps the hosted app stateless; a shared
  database (e.g. Supabase / Vercel Postgres) would be the next step if you want
  cross-device durable saves.
- **Scraping reliability.** The app scrapes YouTube's public pages. From a
  datacenter IP (as on most hosts) YouTube may rate-limit or bot-challenge more
  than it does from a home connection; if searches stop returning results, that,
  or a change to YouTube's page markup, is the usual cause.
- **Keep the parser in sync.** `api/_youtube.py` is a verbatim copy of
  `src/lib/youtube_search.py`. Update both together.
