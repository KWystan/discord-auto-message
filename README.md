# Discord Auto Message — Web App

React + Vite frontend (`client/`) talking to a Flask API (`server/`) through a Vite dev proxy. The legacy desktop automator lives in `automsg.py` (tkinter, standalone) and is not part of the web app yet.

## Requirements

- Node.js 22+ (npm 11+)
- Python 3.11+

## Project structure

```
├── client/   # React + Vite frontend
├── server/   # Flask API (venv/, api.py, requirements.txt, .env)
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

## API

`GET /api/health` → `{"status": "ok"}`

Jobs and engine (all mutations auto-save to `app_data.json`, shared with the legacy desktop app):

- `GET /api/jobs` — jobs (with variant count, preview, next-run timestamp), engine/listener state, task locks, humanizer settings
- `POST /api/jobs` — create `{acc, chan, web, msg, int, unit}` → 201 with job + `redacted` flag (sensitive Discord auth content is replaced with a placeholder, mirroring the desktop's dialog)
- `PUT /api/jobs/<id>` — update; `mode: "now"` forces send on next worker tick, `"wait"` (default) continues the countdown
- `DELETE /api/jobs/<id>` — remove (also clears its task lock and pending run)
- `POST /api/jobs/<id>/send-now` — force send (sets next run to 0)
- `POST /api/engine/start` / `POST /api/engine/stop` — start/stop all job workers (2s startup stagger, same as desktop)
- `GET /api/manager` — token/channel/webhook/replacer names (token & webhook values masked)
- `POST /api/manager/<tokens|channels|webhooks|replacers>` / `DELETE /api/manager/<cat>/<name>` — save/remove manager entries (same mutations as the desktop's Save Token/Channel/Webhook + replacers)
- `PUT /api/settings/humanizer` — typing simulation, 1–3h cooldown buffer, sleep window (same clamping + log line as desktop)
- `POST /api/listener/start` / `POST /api/listener/stop` — Auto-Grab Listener control (validates Token/Channel/target like the desktop)
- `GET /api/data` / `PUT /api/data` — raw app_data.json read/replace (the web equivalent of the desktop's MANUAL EDIT (JSON); shows real tokens, localhost only)
- `GET /api/logs/stream` — SSE: sanitized log lines (history replay + live), same format as the desktop log box

## Engine architecture

`server/engine.py` is a verbatim extraction of the desktop app's business logic (`automsg.py`): job schema, worker-thread loop, variant/spintax parsing, 1–3h random-gap calculation, 429/slowmode handling, session locks, and `clean_sensitive_data()` redaction are preserved line-for-line. The web app and the desktop app read/write the same `app_data.json`. Do not run both at the same time — each holds its own in-memory copy and the last `auto_save()` wins.

Known legacy quirk (replicated on purpose): `{time}`/`{min}`/`{date}` tags are consumed by spintax resolution before tag replacement runs, so they render as literal "time"/"min"/"date" — identical to the desktop app.

Backend tests: `server/venv/Scripts/python.exe server/test_engine.py` (all Discord calls mocked).

## Environment variables

`server/.env` holds local backend configuration (`PORT`, `FLASK_DEBUG`). It is local-only and ignored by Git — never commit it. `server/.env.example` documents the available variables. Vite-side variables are exposed to the browser, so backend secrets stay on the Flask side only.
