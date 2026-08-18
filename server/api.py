import json
import os
import queue
import re
import secrets
import threading
import time
from collections import deque
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

import auth
from engine import AutomationEngine

load_dotenv()

# Same data file as the legacy desktop app (repo root). Overridable for tests.
DATA_FILE = os.getenv("AUTOMSG_DATA_FILE", str(Path(__file__).resolve().parent.parent / "app_data.json"))

app = Flask(__name__)
# Session cookie signing key (username/password login). A random key is used
# when SECRET_KEY isn't configured — sessions reset on server restart then.
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

# ---------------------------------------------------------------------------
# SSE log broadcast — engine.log() lines are pushed to every subscriber,
# scoped per logged-in user.
# ---------------------------------------------------------------------------
_subscribers = {}
_log_history = {}
_sub_lock = threading.Lock()


def _on_log(user, line):
    with _sub_lock:
        _log_history.setdefault(user, deque(maxlen=500)).append(line)
        for q in list(_subscribers.get(user, set())):
            try:
                q.put_nowait(line)
            except queue.Full:
                pass


# ---------------------------------------------------------------------------
# Per-user engines — every logged-in account owns its own engine instance
# (Firestore doc "user-<name>"), so configs, settings and jobs are isolated.
# Engines stay alive after logout so their jobs keep running.
# ---------------------------------------------------------------------------
_engines = {}


def _current_engine():
    user = session.get("user")
    if not user:
        raise RuntimeError("Not logged in.")
    if user not in _engines:
        _engines[user] = AutomationEngine(
            data_file=_user_data_file(user),
            log_callback=lambda line, u=user: _on_log(u, line),
            user=user,
        )
    return _engines[user]


class _EngineProxy:
    def __getattr__(self, name):
        return getattr(_current_engine(), name)


engine = _EngineProxy()


def _user_data_file(username):
    """Return an isolated local fallback file for a username."""
    base = Path(DATA_FILE)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", username)
    suffix = base.suffix or ".json"
    return str(base.with_name(f"{base.stem}-{safe_name}{suffix}"))

MANAGER_CATS = ("tokens", "channels", "webhooks", "replacers")

# ---------------------------------------------------------------------------
# Users store — Firestore collection "users" (doc per username) with a local
# server/users.json fallback when Firebase is unavailable.
# ---------------------------------------------------------------------------
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")


def _fs():
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            credential_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
            cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
            if not credential_json and not cred_path:
                default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firebase-service-account.json")
                if os.path.exists(default_path):
                    cred_path = default_path
            if not credential_json and (not cred_path or not os.path.exists(cred_path)):
                return None
            certificate = credentials.Certificate(
                json.loads(credential_json) if credential_json else cred_path
            )
            firebase_admin.initialize_app(certificate)
        return firestore.client()
    except Exception:
        return None


def _local_users():
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_local_users(data):
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=4)


def _storage_available():
    """Return True if either Firestore or the local users file is usable."""
    db = _fs()
    if db is not None:
        return True
    try:
        with open(USERS_FILE, "a"):
            pass
        return True
    except OSError:
        return False


def _get_user_doc(username):
    db = _fs()
    if db is not None:
        try:
            return db.collection("users").document(username).get().to_dict()
        except Exception:
            return None
    return _local_users().get(username)


def _set_user(username, payload):
    db = _fs()
    if db is not None:
        try:
            db.collection("users").document(username).set(payload)
            return
        except Exception:
            pass
    data = _local_users()
    data[username] = payload
    _save_local_users(data)


def _require_storage():
    """Check that user storage is available — raises on Vercel without Firebase."""
    db = _fs()
    if db is not None:
        return
    try:
        with open(USERS_FILE, "a"):
            pass
    except OSError:
        raise RuntimeError(
            "User storage not available. Set FIREBASE_SERVICE_ACCOUNT_JSON "
            "as a Vercel environment variable to enable Firestore user storage."
        )


# ---------------------------------------------------------------------------
# Auth guard — everything except /api/health and /api/auth/* needs a login.
# ---------------------------------------------------------------------------
@app.before_request
def _auth_guard():
    path = request.path
    if not path.startswith("/api/"):
        return None
    if path == "/api/health" or path.startswith("/api/auth/"):
        return None
    if not session.get("user"):
        return jsonify({"error": "Not logged in."}), 401
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mask(value, label):
    """Partially mask secrets (first 4 + last 4) so the UI can show what's
    saved without exposing the full value — like other apps' token fields."""
    if not value:
        return value
    value = str(value)
    if len(value) > 12:
        return value[:4] + "••••••••" + value[-4:]
    return "••••••••"


def _job_view(job):
    variants = engine.extract_variants(job["msg"])
    preview = variants[0][:28].replace("\n", " ")
    if len(variants) > 1:
        preview = f"[{len(variants)} Variants] {preview}..."
    return {
        **job,
        "variants": len(variants),
        "preview": preview,
        "next_run": engine.running_jobs.get(job["id"]),
    }


def _cdn_url(kind, obj_id, hash_value, size=256):
    if not hash_value:
        return None
    ext = "gif" if str(hash_value).startswith("a_") else "png"
    return f"https://cdn.discordapp.com/{kind}/{obj_id}/{hash_value}.{ext}?size={size}"


_server_cache = {}
_server_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Username + password auth (no OAuth, no email)
# ---------------------------------------------------------------------------
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{2,32}$")


@app.get("/api/auth/me")
def auth_me():
    return jsonify({"user": session.get("user")})


@app.post("/api/auth/register")
def auth_register():
    body = request.get_json(force=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not USERNAME_RE.match(username):
        return jsonify({"error": "Username must be 2-32 characters (letters, numbers, . _ -)."}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400
    try:
        _require_storage()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    if _get_user_doc(username):
        return jsonify({"error": "Username already taken."}), 409
    try:
        _set_user(username, {"password_hash": generate_password_hash(password)})
    except Exception as e:
        return jsonify({"error": f"Failed to save user: {e}"}), 500
    session["user"] = username
    return jsonify({"user": username}), 201


@app.post("/api/auth/login")
def auth_login():
    body = request.get_json(force=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    try:
        doc = _get_user_doc(username)
    except Exception:
        doc = None
    if not doc or not check_password_hash(doc.get("password_hash", ""), password):
        return jsonify({"error": "Invalid username or password."}), 401
    session["user"] = username
    return jsonify({"user": username})


@app.post("/api/auth/logout")
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Icon-only scan token (powers /api/server icons; never used for posting)
# ---------------------------------------------------------------------------
@app.get("/api/scan-token")
def scan_token_status():
    return jsonify({"set": bool(engine.data.get("scan_token"))})


@app.post("/api/scan-token")
def scan_token_set():
    body = request.get_json(force=True) or {}
    val = str(body.get("token", "")).strip()
    if not val:
        return jsonify({"error": "Token is required."}), 400
    engine.data["scan_token"] = val
    engine.auto_save()
    return jsonify({"ok": True})


@app.delete("/api/scan-token")
def scan_token_clear():
    engine.data.pop("scan_token", None)
    engine.auto_save()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Server scan (channels, icon, emojis — Discord-style panel data)
# ---------------------------------------------------------------------------
@app.get("/api/server")
def server_info():
    """Aggregate the fixed server's info: guild card, channel list, emojis.

    Scans with the stored account token named by ?token=, then the optional
    icon-only AUTOMSG_ICON_SCAN_TOKEN, then the per-user scan token and first
    saved token. Channel listing falls back gracefully: if
    GET /guilds/{id}/channels is denied (403 — no MANAGE_CHANNELS), only the
    configured channel is shown (channels_source='fallback'). Results are
    cached for 5 minutes.
    """
    tokens = engine.data.get("tokens", {})
    nick = request.args.get("token", "").strip()
    # The requested tab's token wins; the environment token is icon-only and
    # is never inserted into the user's posting-token map.
    icon_scan_token = os.getenv("AUTOMSG_ICON_SCAN_TOKEN", "").strip()
    scan_token = (
        tokens.get(nick)
        or icon_scan_token
        or engine.data.get("scan_token")
        or next((t for t in tokens.values() if t), None)
    )
    if not scan_token:
        return jsonify({"error": "No account token saved yet."}), 401

    with _server_cache_lock:
        cached = _server_cache.get("anon")
        if cached and cached.get("ts", 0) > time.time() - 300:
            return jsonify(cached["data"])

    guild_id = auth.target_guild_id()
    if not guild_id:
        return jsonify({"error": "DISCORD_GUILD_ID is not configured."}), 400
    try:
        # Guild card comes from the preview endpoint (name, icon, member
        # counts, description, emojis) — no 'guilds' OAuth scope needed.
        preview = {}
        try:
            preview = auth.fetch_guild_preview(scan_token, guild_id)
        except requests.HTTPError:
            pass
        guild = {
            "id": guild_id,
            "name": preview.get("name"),
            "icon": preview.get("icon"),
            "approximate_member_count": preview.get("approximate_member_count"),
            "approximate_presence_count": preview.get("approximate_presence_count"),
            "description": preview.get("description"),
        }
        # Enrich with the guilds list when the credential can read it.
        try:
            guilds = auth.fetch_user_guilds(scan_token)
            entry = next((g for g in guilds if str(g.get("id")) == guild_id), None)
            if entry:
                guild.update({
                    "name": entry.get("name") or guild.get("name"),
                    "icon": entry.get("icon") or guild.get("icon"),
                    "approximate_member_count": entry.get("approximate_member_count") or guild.get("approximate_member_count"),
                    "approximate_presence_count": entry.get("approximate_presence_count") or guild.get("approximate_presence_count"),
                    "permissions": entry.get("permissions"),
                })
        except requests.HTTPError:
            pass
        if not guild.get("name"):
            return jsonify({"error": "Could not read the configured server."}), 404

        channels = []
        source = "none"
        try:
            channels = auth.fetch_channels(scan_token, guild_id)
            source = "list"
        except requests.HTTPError:
            source = "fallback"

        # Include the configured channel in fallback mode.
        known_ids = {str(c.get("id")) for c in channels}
        if source == "fallback" and auth.target_channel_id() and str(auth.target_channel_id()) not in known_ids:
            try:
                channels.append(auth.fetch_channel(scan_token, auth.target_channel_id()))
            except requests.HTTPError:
                pass

        # Persist per-channel slowmode (channel_meta) so jobs on channels the
        # scan can't list still space sends correctly.
        meta = engine.data.setdefault("channel_meta", {})
        meta_changed = False
        for ch in channels:
            name = ch.get("name")
            if not name:
                continue
            val = int(ch.get("rate_limit_per_user") or 0)
            if meta.get(name, {}).get("rate_limit_per_user", 0) != val:
                meta[name] = {"rate_limit_per_user": val}
                meta_changed = True
        if meta_changed:
            engine.auto_save()

        payload = {
            "guild": {
                "id": guild.get("id"),
                "name": guild.get("name"),
                "icon_url": _cdn_url("icons", guild.get("id"), guild.get("icon")),
                "member_count": guild.get("approximate_member_count"),
                "presence_count": guild.get("approximate_presence_count"),
                "description": guild.get("description"),
                "permissions": guild.get("permissions"),
            },
            "channels": channels,
            "channels_source": source,
            "emojis": [
                {
                    "id": e.get("id"),
                    "name": e.get("name"),
                    "animated": bool(e.get("animated")),
                    "url": f"https://cdn.discordapp.com/emojis/{e.get('id')}.{'gif' if e.get('animated') else 'png'}",
                }
                for e in preview.get("emojis", [])
            ],
        }
    except requests.HTTPError as e:
        return jsonify({"error": f"Discord API error {e.response.status_code}"}), 502

    with _server_cache_lock:
        _server_cache["anon"] = {"ts": time.time(), "data": payload}
    return jsonify(payload)


@app.get("/api/server/channels/<channel_id>")
def server_channel(channel_id):
    """Fetch a single channel's details (works with VIEW_CHANNEL only)."""
    candidates = [t for t in engine.data.get("tokens", {}).values() if t]
    icon_scan_token = os.getenv("AUTOMSG_ICON_SCAN_TOKEN", "").strip()
    if icon_scan_token:
        candidates.append(icon_scan_token)
    if engine.data.get("scan_token"):
        candidates.append(engine.data["scan_token"])
    last_code = None
    for tok in candidates:
        try:
            return jsonify(auth.fetch_channel(tok, channel_id))
        except requests.HTTPError as e:
            last_code = e.response.status_code
    if last_code:
        return jsonify({"error": f"Discord API error {last_code}"}), 502
    return jsonify({"error": "No account token saved yet."}), 401


# ---------------------------------------------------------------------------
# Manager entries (tokens / channels / webhooks / replacers)
# ---------------------------------------------------------------------------
@app.get("/api/manager")
def manager():
    return jsonify({
        "tokens": {name: _mask(val, "TOKEN") for name, val in engine.data.get("tokens", {}).items()},
        "channels": engine.data.get("channels", {}),
        "webhooks": {name: _mask(val, "WEBHOOK") for name, val in engine.data.get("webhooks", {}).items()},
        "replacers": engine.data.get("replacers", {}),
    })


@app.post("/api/manager/<cat>")
def manager_store(cat):
    if cat not in MANAGER_CATS:
        return jsonify({"error": f"Unknown category {cat}"}), 400
    body = request.get_json(force=True) or {}
    name = str(body.get("name", "")).strip()
    val = str(body.get("value", "")).strip()
    if not (name and val):
        return jsonify({"error": "Nick / Find and Value / Replace With are required."}), 400
    engine.store_manager_entry(cat, name, val)
    return jsonify({"ok": True, "category": cat, "name": name}), 201


@app.delete("/api/manager/<cat>/<name>")
def manager_delete(cat, name):
    if cat not in MANAGER_CATS:
        return jsonify({"error": f"Unknown category {cat}"}), 400
    engine.delete_manager_entry(cat, name)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Humanizer settings
# ---------------------------------------------------------------------------
@app.put("/api/settings/humanizer")
def humanizer():
    body = request.get_json(force=True) or {}
    engine.save_humanizer_settings(
        typing_var=bool(body.get("simulate_typing", True)),
    )
    return jsonify({"humanizer_settings": engine.data["humanizer_settings"]})


# ---------------------------------------------------------------------------
# Raw data (manual JSON edit, mirrors the desktop's open-in-editor)
# ---------------------------------------------------------------------------
@app.get("/api/data")
def data_raw():
    return jsonify(engine.data)


@app.put("/api/data")
def data_replace():
    body = request.get_json(force=True)
    try:
        engine.replace_data(body)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
@app.get("/api/jobs")
def list_jobs():
    return jsonify({
        "engine_running": engine.running,
        "listening": engine.listening,
        "next_runs": engine.running_jobs,
        "task_locks": engine.task_locks,
        "humanizer_settings": engine.data.get("humanizer_settings", {}),
        "listener_settings": engine.data.get("listener_settings", {}),
        "jobs": [_job_view(j) for j in engine.data["jobs"]],
    })


@app.post("/api/jobs")
def create_job():
    body = request.get_json(force=True) or {}
    chan = str(body.get("chan", "")).strip()
    # Token jobs need channels[name] -> id so the engine can resolve the
    # channel; webhook jobs tolerate it too (harmless extra mapping).
    channel_id = str(body.get("channel_id", "")).strip()
    if channel_id and chan:
        try:
            engine.store_manager_entry("channels", chan, channel_id)
        except Exception:
            pass
    try:
        job, redacted = engine.create_job(
            acc=str(body.get("acc", "")).strip(),
            chan=chan,
            web=str(body.get("web") or "None"),
            msg=str(body.get("msg", "")).strip(),
            interval=str(body.get("int", "")).strip(),
            unit=str(body.get("unit") or "Min"),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"job": _job_view(job), "redacted": redacted}), 201


@app.put("/api/jobs/<job_id>")
def update_job(job_id):
    body = request.get_json(force=True) or {}
    chan = str(body.get("chan", "")).strip()
    channel_id = str(body.get("channel_id", "")).strip()
    if channel_id and chan:
        try:
            engine.store_manager_entry("channels", chan, channel_id)
        except Exception:
            pass
    try:
        job = engine.update_job(
            job_id,
            acc=str(body.get("acc", "")).strip(),
            chan=chan,
            web=str(body.get("web") or "None"),
            msg=str(body.get("msg", "")).strip(),
            interval=str(body.get("int", "")).strip(),
            unit=str(body.get("unit") or "Min"),
            mode=body.get("mode", "wait"),
        )
    except KeyError:
        return jsonify({"error": f"Job {job_id} not found"}), 404
    return jsonify({"job": _job_view(job), "redacted": bool(engine.contains_sensitive_data(str(body.get("msg", ""))))})


@app.delete("/api/jobs/<job_id>")
def delete_job(job_id):
    try:
        job = engine.delete_job(job_id)
    except KeyError:
        return jsonify({"error": f"Job {job_id} not found"}), 404
    return jsonify({"deleted": job["id"]})


@app.post("/api/jobs/<job_id>/send-now")
def send_now(job_id):
    try:
        engine.send_now(job_id)
    except KeyError:
        return jsonify({"error": f"Job {job_id} not found"}), 404
    return jsonify({"ok": True, "job_id": job_id})


# ---------------------------------------------------------------------------
# Engine start / stop
# ---------------------------------------------------------------------------
@app.post("/api/engine/start")
def engine_start():
    started = engine.start_engine()
    return jsonify({"running": engine.running, "started": started})


@app.post("/api/engine/stop")
def engine_stop():
    stopped = engine.stop_engine()
    return jsonify({"running": engine.running, "stopped": stopped})


# ---------------------------------------------------------------------------
# SSE log stream
# ---------------------------------------------------------------------------
@app.get("/api/logs/stream")
def logs_stream():
    user = session.get("user")
    if not user:
        return Response('data: {"error":"not logged in"}\n\n', mimetype="text/event-stream")

    def gen():
        q = queue.Queue(maxsize=200)
        with _sub_lock:
            _subscribers.setdefault(user, set()).add(q)
            history = list(_log_history.get(user, []))
        try:
            for line in history:
                yield f"data: {json.dumps({'line': line})}\n\n"
            while True:
                try:
                    line = q.get(timeout=15)
                    yield f"data: {json.dumps({'line': line})}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _sub_lock:
                _subscribers.get(user, set()).discard(q)

    return Response(gen(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })


CLIENT_DIST = Path(__file__).resolve().parent.parent / "client" / "dist"


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def frontend(path):
    """Serve the built Vite app when running Flask in production mode."""
    if path.startswith("api/"):
        return jsonify({"error": "Not found."}), 404
    if not CLIENT_DIST.is_dir():
        return jsonify({"error": "Client build not found. Run npm run build first."}), 404
    requested = CLIENT_DIST / path if path else CLIENT_DIST / "index.html"
    if path and requested.is_file():
        return send_from_directory(str(CLIENT_DIST), path)
    return send_from_directory(str(CLIENT_DIST), "index.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    host = os.getenv("HOST", "127.0.0.1")
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    # threaded=True: SSE streams and API calls must be served concurrently.
    app.run(host=host, port=port, debug=debug, threaded=True)
