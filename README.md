# Discord Auto Message — Web App

React + Vite frontend (`client/`) talking to a Flask API (`server/`) through a Vite dev proxy. Schedules auto messages for the game server's channels (channel list hardcoded in `client/src/channels.js`). Posting is done with a stored **account token** (the legacy self-bot approach from `automsg.py`) — **no Discord OAuth, no webhooks**.

## Requirements

- Node.js 22+ (npm 11+)
- Python 3.11+

## Project structure

```
├── client/   # React + Vite frontend
├── server/   # Flask API (venv/, api.py, engine.py, requirements.txt, .env)
├── scripts/  # Cross-platform dev helpers
└── automsg.py  # Legacy tkinter app (not part of the web scaffold)
```

## Installation

Frontend:

```bash
cd client
npm install
```

Backend (virtual environment):

```bash
python -m venv server/venv
```

Activate the venv:

- macOS/Linux: `source server/venv/bin/activate`
- Windows (PowerShell): `server\venv\Scripts\activate`

Then install dependencies:

```bash
pip install -r server/requirements.txt
```

`npm run api` does not require the venv to be activated — `scripts/api.cjs` locates the venv interpreter automatically (falling back to `python` on PATH).

## Running the application

From the project root:

```bash
npm run dev      # React/Vite dev server (http://localhost:5173)
npm run api      # Flask API (http://localhost:5000)
npm run start    # both at once (via concurrently)
```

Also available: `npm run build` (production build of the frontend) and `npm run lint` (oxlint).

In development, React calls `fetch('/api/health')`; Vite proxies `/api/*` to `http://localhost:5000`, so no CORS or hardcoded backend URLs are needed. If port 5173 is already in use (another Vite app running), Vite automatically picks the next free port (5174, ...) — check the `npm run dev` output.

## Usage

1. **Save an account token** in the sidebar's *Account token* panel (nickname + token, like the legacy desktop app). It is the posting account and powers the server scan.
2. **Click a channel** in the sidebar list — it appears in the Compose panel.
3. **Compose** the message (Discord Markdown formatting toolbar: bold/italic/underline/strikethrough/headings, plus `{time}`/`{min}`/`{date}` and `---` variant separators), pick the interval (1–6h presets) and an optional delay buffer.
4. **Add to Queue** → the task lands in the Scheduler table.
5. **Start engine** — workers post on schedule (base interval + random gap, slowmode and 60m minimum enforced).

> Token posting is a self-bot per Discord ToS — ban risk on the account. Same trade-off as `automsg.py`.

## API

`GET /api/health` → `{"status": "ok"}`

Jobs and engine (all mutations auto-save to Firestore, falling back to `app_data.json`):

- `GET /api/jobs` — jobs (with variant count, preview, next-run timestamp), engine/listener state, task locks, humanizer settings
- `POST /api/jobs` — create `{acc, chan, web, msg, int, unit, channel_id}` → 201 with job + `redacted` flag (sensitive Discord auth content is replaced with a placeholder); `channel_id` syncs `channels[name] → id` so token jobs resolve the channel
- `PUT /api/jobs/<id>` — update; `mode: "now"` forces send on next worker tick, `"wait"` (default) continues the countdown
- `DELETE /api/jobs/<id>` — remove (also clears its task lock and pending run)
- `POST /api/jobs/<id>/send-now` — force send (sets next run to 0)
- `POST /api/engine/start` / `POST /api/engine/stop` — start/stop all job workers (2s startup stagger, same as desktop)
- `GET /api/manager` — token/channel/replacer names (token values masked)
- `POST /api/manager/<tokens|channels|webhooks|replacers>` / `DELETE /api/manager/<cat>/<name>` — save/remove manager entries
- `PUT /api/settings/humanizer` — typing simulation, cooldown buffer, sleep window
- `GET /api/data` / `PUT /api/data` — raw data read/replace (shows real tokens; localhost only)
- `GET /api/logs/stream` — SSE: sanitized log lines (history replay + live), same format as the desktop log box

## Server scan (channels, click to configure)

The **server** tab renders the game-server channel list hardcoded in `client/src/channels.js` (`HARDCODED_CHANNELS`: channel id + display name — no channel-listing permission needed). Each row shows its emoji glyph and a per-channel **slowmode badge** (e.g. `1 msg/hr`) when the scan can read it. Clicking a channel selects it in the Compose panel.

- `GET /api/server` — aggregated `{guild, channels, channels_source, emojis}` for the fixed server (5-minute in-memory cache); scans with the first stored account token; persists each channel's `rate_limit_per_user` into `channel_meta` so jobs space sends correctly
  - `channels_source: "list"` — full channel list returned (merged over the hardcoded names where they match)
  - `channels_source: "fallback"` — channel listing was denied (403); the hardcoded list still renders
- `GET /api/server/channels/<id>` — a single channel's details (works with `VIEW_CHANNEL` only)

**Slowmode is enforced by the engine**: each channel's `rate_limit_per_user` is read at scan time and the next run is `max(interval, slowmode + 1)` — a `1 msg/hr` channel never receives more than one message per hour, regardless of the configured interval.

## Storage: Firestore (with JSON fallback)

Persistence is Firestore-backed. The engine writes the full data document on every mutation (the Firestore equivalent of the old full-JSON-dump `auto_save()`).

- Collection `discordautomsg`, document `app_data` (configurable via `FIRESTORE_COLLECTION` / `FIRESTORE_DOC`)
- The service account must live at `server/firebase-service-account.json` (or point `FIREBASE_SERVICE_ACCOUNT_PATH` at it) — **never commit it** (already gitignored)
- If Firebase is unavailable (SDK missing, no credentials, DB missing, or `FIREBASE_ENABLED=0`), the engine falls back to the local `app_data.json` file with the exact same semantics as before
- On first run against an empty Firestore, the engine seeds the document from local data (or defaults) — a one-time migration path
- The legacy desktop app (`automsg.py`) still uses `app_data.json` — don't run both simultaneously against the same store (last `auto_save()` wins)

### One-time setup (required)

The Firestore database itself must be created once in the Google Cloud console (the service account cannot create it):

1. Open the Firebase console → Firestore (the server log prints the project link)
2. Click **Create database** → choose **Firestore mode** (native) → pick a region (e.g. `us-central1`) → **Enable**
3. Restart the API (`npm run api`) — the engine log will show `Loaded data from Firestore.`

## Engine architecture

`server/engine.py` is a verbatim extraction of the desktop app's business logic (`automsg.py`): job schema, worker-thread loop, variant/spintax parsing, random-gap calculation, 429/slowmode handling, session locks, and `clean_sensitive_data()` redaction are preserved line-for-line. Each process holds its own in-memory copy, so don't run two web-api processes against the same Firestore doc simultaneously — last `auto_save()` wins.

Known legacy quirk (replicated on purpose): `{time}`/`{min}`/`{date}` tags are consumed by spintax resolution before tag replacement runs, so they render as literal "time"/"min"/"date" — identical to the desktop app.

Backend tests: `server/venv/Scripts/python.exe server/test_engine.py` + `server/test_auth.py` — all Discord calls mocked.

## Environment variables

`server/.env` holds local backend configuration. It is local-only and ignored by Git — never commit it. `server/.env.example` documents the available variables:

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `PORT` | `5000` | Flask port |
| `FLASK_DEBUG` | `0` | Keep `0` — the reloader would duplicate engine threads |
| `FIREBASE_ENABLED` | `1` | Set to `0` to force local JSON storage |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | *(auto: `server/firebase-service-account.json`)* | Path to the Firebase service-account JSON |
| `FIRESTORE_COLLECTION` | `discordautomsg` | Firestore collection holding the app document |
| `FIRESTORE_DOC` | `app_data` | Firestore document holding the full data payload |
| `DISCORD_GUILD_ID` | *(empty)* | Fixed target server used by the server scan |
| `DISCORD_CHANNEL_ID` | *(empty)* | Fallback channel fetched when channel listing is denied |

Vite-side variables are exposed to the browser, so backend secrets stay on the Flask side only.
