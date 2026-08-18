# Discord Auto Message — Web App

React + Vite frontend (`client/`) talking to a Flask API (`server/`) through a Vite dev proxy. Schedules auto messages for the game server's channels (channel list hardcoded in `client/src/channels.js`). Posting is done with a stored **account token** (the legacy self-bot approach from `automsg.py`) — **no Discord OAuth, no webhooks**.

**Login is a simple username + password** (no email, no OAuth). Every account's configs, settings, tokens and jobs are stored in **its own Firestore document** (`discordautomsg/user-<username>` via the Firebase Admin SDK) and are never visible to other users. Without Firebase, accounts fall back to `server/users.json` (password hashes) and data to the local `app_data.json`.

## Requirements

- Node.js 22+ (npm 11+)
- Python 3.11+

## Project structure

```
├── client/   # React + Vite frontend
├── server/   # Flask API (venv/, api.py, engine.py, requirements.txt, .env)
├── api/      # Vercel Python Function adapter for server/api.py
├── scripts/  # Cross-platform dev helpers
└── automsg.py  # Legacy tkinter app (not part of the web scaffold)
```

## Installation

From the repository root, run the one-time setup command:

```bash
npm run setup
```

It installs the client dependencies, creates `server/venv` when needed, and installs `server/requirements.txt`. Copy the backend environment template before starting:

```bash
copy server\.env.example server\.env   # Windows
cp server/.env.example server/.env      # macOS/Linux
```

The backend virtual environment can also be prepared manually:

- macOS/Linux: `source server/venv/bin/activate`
- Windows (PowerShell): `server\venv\Scripts\activate`

`npm run api` does not require the venv to be activated — `scripts/api.cjs` locates the venv interpreter automatically (falling back to `python` on PATH).

## Running the application

From the project root:

```bash
npm run dev      # React/Vite dev server (http://localhost:5173)
npm run api      # Flask API (http://localhost:5000)
npm run start    # client + API together
npm run check    # frontend lint + backend tests
```

For a single-process build where Flask serves the compiled React app:

```bash
npm run serve    # build client/dist, then serve it from Flask
```

Also available: `npm run build` (frontend production build), `npm run lint` (oxlint), and `npm run preview` (Vite preview server).

In development, React calls `fetch('/api/health')`; Vite proxies `/api/*` to `http://localhost:5000`, so no CORS or hardcoded backend URLs are needed. In production, Flask serves `client/dist` from the same port. If port 5173 is already in use (another Vite app running), Vite automatically picks the next free port (5174, ...) — check the `npm run dev` output.

## Vercel deployment

The repository root is the Vercel project root. Do **not** set Vercel's Root Directory to `client` or `server`.

`vercel.json` configures the deployment as follows:

- `npm install` installs the root tools and `client/` dependencies
- `npm run build` builds the React app into `client/dist`
- `client/dist` is the deployment output
- `/api/*` rewrites to `api/index.py`, which imports the Flask app from `server/api.py`
- all other routes fall back to the React `index.html`

Set these Vercel environment variables (all required for the app to work):

- `SECRET_KEY` — a stable random session key
- `FIREBASE_ENABLED=1`
- `FIREBASE_SERVICE_ACCOUNT_JSON` — **required** — paste the full JSON contents of your `server/firebase-service-account.json` as one secret value. Without this, user accounts and app data can't be stored on Vercel (the filesystem is read-only)
- `FIRESTORE_COLLECTION=discordautomsg`
- `DISCORD_GUILD_ID` = `571992648190263317`
- `DISCORD_CHANNEL_ID` = `997645910769160202`
- `AUTOMSG_ICON_SCAN_TOKEN` — optional Discord token used only for server/channel icons and live channel metadata; it is not added to any user's posting-token tabs

The service-account file is intentionally gitignored; use `FIREBASE_SERVICE_ACCOUNT_JSON` on Vercel instead. The root `requirements.txt` includes `server/requirements.txt` so the Python Function gets the same backend dependencies.

Vercel Functions are request-based and do not provide a permanent worker process. The React UI, login, Firestore-backed CRUD, and API requests can deploy there, but the scheduler's long-running background threads cannot be guaranteed to keep running after a request ends. Use an always-on host for reliable automatic sending, or run Vercel as the UI/API layer and host the scheduler worker separately.

## Usage

1. **Log in** (or register) with a username + password — the app is otherwise locked
2. **Save an account token** in the sidebar's *Account token* panel (nickname + token, like the legacy desktop app). It is the posting account and powers the server scan
3. **Click a channel** in the sidebar list — it appears in the Compose panel
4. **Compose** the message (Discord Markdown formatting toolbar: bold/italic/underline/strikethrough), pick the interval (presets adapt to each channel's slowmode limit) and an optional delay buffer
5. **Add to Queue** → the task lands in the Scheduler table
6. **Start engine** — workers post on schedule (slowmode floor enforced, no random gap)

All of the above is scoped to your account: tokens, jobs, tabs and settings live in your own Firestore document and vanish for anyone else logging in.

> Token posting is a self-bot per Discord ToS — ban risk on the account. Same trade-off as `automsg.py`.

## API

`GET /api/health` → `{"status": "ok"}`

**Auth (username + password, session cookie):**
- `POST /api/auth/register` `{username, password}` → 201 + auto-login (409 if taken)
- `POST /api/auth/login` `{username, password}` → 200 (401 on bad credentials)
- `POST /api/auth/logout` → clears the session
- `GET /api/auth/me` → `{"user": "<username>"}` (or `{"user": null}`)

Every other endpoint returns **401** unless logged in. All data is per-user (each account gets its own engine + Firestore doc).

Jobs and engine (all mutations auto-save to the user's Firestore doc, falling back to `app_data.json`):

- `GET /api/jobs` — jobs (with variant count, preview, next-run timestamp), engine/listener state, task locks, humanizer settings
- `POST /api/jobs` — create `{acc, chan, web, msg, int, unit, channel_id}` → 201 with job + `redacted` flag (sensitive Discord auth content is replaced with a placeholder); `channel_id` syncs `channels[name] → id` so token jobs resolve the channel
- `PUT /api/jobs/<id>` — update; `mode: "now"` forces send on next worker tick, `"wait"` (default) continues the countdown
- `DELETE /api/jobs/<id>` — remove (also clears its task lock and pending run)
- `POST /api/jobs/<id>/send-now` — force send (sets next run to 0)
- `POST /api/engine/start` / `POST /api/engine/stop` — start/stop all job workers (2s startup stagger, same as desktop)
- `GET /api/manager` — token/channel/replacer names (token values masked)
- `POST /api/manager/<tokens|channels|replacers>` / `DELETE /api/manager/<cat>/<name>` — save/remove manager entries
- `PUT /api/settings/humanizer` — typing simulation settings
- `GET /api/data` / `PUT /api/data` — raw data read/replace (shows real tokens; localhost only)
- `GET /api/logs/stream` — SSE: sanitized log lines (history replay + live), same format as the desktop log box

## Server scan (channels, click to configure)

The **server** tab renders the game-server channel list hardcoded in `client/src/channels.js` (`HARDCODED_CHANNELS`: channel id, display name, icon and message limit — no channel-listing permission needed). Each row shows its emoji glyph and a per-channel limit badge (for example `2 hrs / msg`) even without a scan token. A live scan can update channel metadata. Clicking a channel selects it in the Compose panel.

- `GET /api/server` — aggregated `{guild, channels, channels_source, emojis}` for the fixed server (5-minute in-memory cache); uses the selected account token when available and persists live `rate_limit_per_user` data into `channel_meta`
  - `channels_source: "list"` — full channel list returned (merged over the hardcoded names where they match)
  - `channels_source: "fallback"` — channel listing was denied (403); the hardcoded list still renders
- `GET /api/server/channels/<id>` — a single channel's details (works with `VIEW_CHANNEL` only)

**Slowmode is enforced by the engine**: each channel's `rate_limit_per_user` is read at scan time and the next run is `max(interval, slowmode + 1)` — a `1 msg/hr` channel never receives more than one message per hour, regardless of the configured interval.

## Storage: Firestore (with JSON fallback)

Persistence is Firestore-backed through the Firebase Admin SDK. Each username gets a separate engine document (`discordautomsg/user-<username>`), and credentials are stored separately in the `users` collection. The engine writes the full per-user data document on every mutation.

- Collection `discordautomsg`, document `user-<username>` (base collection configurable via `FIRESTORE_COLLECTION`)
- Collection `users`, document `<username>` stores the password hash only
- The service account must live at `server/firebase-service-account.json` (or point `FIREBASE_SERVICE_ACCOUNT_PATH` at it) — **never commit it** (already gitignored)
- If Firebase is unavailable (SDK missing, no credentials, DB missing, or `FIREBASE_ENABLED=0`), users fall back to `server/users.json` and each user's engine data falls back to an isolated `app_data-<username>.json` file
- On first run against an empty user document, the engine seeds that user's document from local data (or defaults)
- The legacy desktop app (`automsg.py`) still uses `app_data.json` — don't run both simultaneously against the same store (last `auto_save()` wins)

### One-time setup (required)

The Firestore database itself must be created once in the Google Cloud console (the service account cannot create it):

1. Open the Firebase console → Firestore (the server log prints the project link)
2. Click **Create database** → choose **Firestore mode** (native) → pick a region (e.g. `us-central1`) → **Enable**
3. Restart the API (`npm run api`) — the engine log will show `Loaded data from Firestore.`

## Engine architecture

`server/engine.py` is an extraction of the desktop app's business logic (`automsg.py`): job schema, worker-thread loop, variant/spintax parsing, exact interval scheduling, 429/slowmode handling, session locks, and `clean_sensitive_data()` redaction. Each logged-in user has its own engine instance and Firestore document; engines continue running their user's jobs after logout.

Known legacy quirk (replicated on purpose): `{time}`/`{min}`/`{date}` tags are consumed by spintax resolution before tag replacement runs, so they render as literal "time"/"min"/"date" — identical to the desktop app.

Backend tests: `npm run check` (27 engine tests + 14 auth tests; all Discord calls mocked).

## Environment variables

`server/.env` holds local backend configuration. It is local-only and ignored by Git — never commit it. `server/.env.example` documents the available variables:

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `PORT` | `5000` | Flask port |
| `HOST` | `127.0.0.1` | Flask bind address (`0.0.0.0` for a network deployment) |
| `FLASK_DEBUG` | `0` | Keep `0` — the reloader would duplicate engine threads |
| `SECRET_KEY` | *(random per restart)* | Session signing key — set a stable value |
| `AUTOMSG_DATA_FILE` | *(repo-root `app_data.json`)* | Base path for isolated local fallback files |
| `FIREBASE_ENABLED` | `1` | Set to `0` to force local JSON storage |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | *(auto: `server/firebase-service-account.json`)* | Path to the Firebase service-account JSON |
| `FIRESTORE_COLLECTION` | `discordautomsg` | Firestore collection holding the app document |
| `FIRESTORE_DOC` | `app_data` | Legacy/default document name; logged-in users use `user-<username>` |
| `DISCORD_GUILD_ID` | *(empty)* | Fixed target server used by the server scan |
| `DISCORD_CHANNEL_ID` | *(empty)* | Fallback channel fetched when channel listing is denied |

Vite-side variables are exposed to the browser, so backend secrets stay on the Flask side only.
