import json
import os
import queue
import threading
import time
from collections import deque
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request

import auth
from engine import AutomationEngine

load_dotenv()

# Same data file as the legacy desktop app (repo root). Overridable for tests.
DATA_FILE = os.getenv("AUTOMSG_DATA_FILE", str(Path(__file__).resolve().parent.parent / "app_data.json"))

app = Flask(__name__)

# ---------------------------------------------------------------------------
# SSE log broadcast — engine.log() lines are pushed to every subscriber.
# ---------------------------------------------------------------------------
_subscribers = set()
_sub_lock = threading.Lock()
_log_history = deque(maxlen=500)


def _on_log(line):
    with _sub_lock:
        _log_history.append(line)
        for q in list(_subscribers):
            try:
                q.put_nowait(line)
            except queue.Full:
                pass


engine = AutomationEngine(data_file=DATA_FILE, log_callback=_on_log)

MANAGER_CATS = ("tokens", "channels", "webhooks", "replacers")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mask(value, label):
    if not value:
        return value
    return "•••••••••••••••• [" + label + " HIDDEN]"


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
# Server scan (channels, icon, emojis — Discord-style panel data)
# ---------------------------------------------------------------------------
@app.get("/api/server")
def server_info():
    """Aggregate the fixed server's info: guild card, channel list, emojis.

    Scans with the first stored account token. Channel listing falls back
    gracefully: if GET /guilds/{id}/channels is denied (403 — no
    MANAGE_CHANNELS), only the configured channel is shown
    (channels_source='fallback'). Results are cached for 5 minutes.
    """
    scan_token = next((t for t in engine.data.get("tokens", {}).values() if t), None)
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
        buf_min_entry_text=str(body.get("cooldown_buffer_min_hrs", "1.0")),
        buf_max_entry_text=str(body.get("cooldown_buffer_max_hrs", "3.0")),
        typing_var=bool(body.get("simulate_typing", True)),
        sleep_var=bool(body.get("sleep_hours_enabled", False)),
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
    def gen():
        q = queue.Queue(maxsize=200)
        with _sub_lock:
            _subscribers.add(q)
            history = list(_log_history)
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
                _subscribers.discard(q)

    return Response(gen(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    # threaded=True: SSE streams and API calls must be served concurrently.
    app.run(host="127.0.0.1", port=port, debug=debug, threaded=True)
