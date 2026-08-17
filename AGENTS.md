# DiscordAutoMSG

Three parts:

1. **Legacy desktop app** — `automsg.py`: single-file Python 3 + tkinter Discord scheduler (daemon threads per job, raw Discord REST api/v10 with user-token Authorization, typing simulation, +1–3h random gaps, spintax/variants, channel-listener with session locks).
2. **Web app** — `client/` (React + Vite) + `server/` (Flask API, proxied via Vite). Job dashboard, editor modal, SSE live log.
3. **Engine** — `server/engine.py`: the desktop app's business logic extracted verbatim. **The web app and desktop app share the same `app_data.json` — never run both simultaneously (last auto_save wins).**

Not a git repo; no CI.

## Web app commands (from repo root)
- `npm run dev` — Vite dev server (client/). If 5173 is taken (another Vite app is often running on this machine), Vite auto-increments the port — read its output.
- `npm run api` — Flask via `scripts/api.cjs` (auto-detects `server/venv/Scripts/python.exe` on Windows, `server/venv/bin/python` elsewhere, falls back to `python` on PATH).
- `npm run start` — both via concurrently. `npm run build` / `npm run lint` (oxlint) — frontend only.
- Flask: `server/api.py` on port 5000, config from `server/.env` (`PORT`, `FLASK_DEBUG` — keep `FLASK_DEBUG=0`; the reloader would duplicate engine threads).
- `AUTOMSG_DATA_FILE` env var overrides the data file (read at `server/api.py:16`, passed to the engine; default: repo-root `app_data.json`). The engine's own default is CWD-relative `app_data.json` — importing/running engine.py from another directory silently uses a second data file, same trap as automsg.py.
- Backend tests: `server/venv/Scripts/python.exe server/test_engine.py` (26 tests, all Discord calls mocked).
- Full API surface (incl. `send-now`, `PUT mode: "now"`, SSE log stream) is documented in `README.md` — read it before touching endpoints.

## Engine (server/engine.py) — the rules
- **Verbatim extraction**: job schema `{id, acc, chan, msg, int, unit, web}`, worker loop (0.5s tick, `running_jobs[jid]` = next-run epoch), variant pools (`---`/`===` separators, never repeats back-to-back), spintax `{a|b}`, 1–3h random gap past timeout (≥30min base), ±15% below, sleep window 1AM–8AM, 429 `retry_after` sleep, slowmode per channel, session locks (`task_locks`), DM commands (`#msg <id> <text>`, `#int <id> <n> Sec|Min`). Do NOT "fix" or modernize any of it — bug-for-bug parity is the requirement.
- Known legacy quirk: `{time}`/`{min}`/`{date}` tags are eaten by `resolve_spintax` before tag replacement, so they render literally — keep it.
- `log()` forwards sanitized `[HH:MM:SS] ...` lines to a callback (SSE broadcast); `on_data_change` replaces `root.after(0, refresh_ui_lists)`.
- `create_job`/`update_job` auto-redact sensitive messages (the desktop's askyesno dialog is a UI decision) and return `redacted`; validation failures raise ValueError → 400.
- Redaction: token regex `[\w-]{24,28}\.[\w-]{6}\.[\w-]{27,38}` + stored tokens/webhooks/channel IDs replaced with `[WARNING: ... REDACTED]` in logs and stored messages.

## Legacy app (automsg.py)
- Run from the repo root: `python automsg.py` — `app_data.json` is **CWD-relative**; running from another directory silently uses a second data file. Only third-party dep: `requests`.
- Every mutation calls `auto_save()` (full JSON dump, indent=4). Worker threads call `self.log()` (tkinter Text insert) directly from background threads — established pattern, keep it.

## Pitfalls
- **Orphaned processes**: killing the npm wrapper (`npm run api` / `npm run dev`) does NOT kill the python/vite child on Windows — check `netstat -ano | grep LISTENING` for `:5000`/`:517x` and `taskkill /PID <pid> /F` before restarting, or the old code answers requests.
- Port 5173 is frequently occupied by the user's other Vite app.
- The file previously had `8)`→😎 emoji corruption and a `_name_` guard bug; both fixed — don't reintroduce autocorrect mangling.
- `simpledialog` import in automsg.py is unused.
