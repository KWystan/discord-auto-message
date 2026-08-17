import json
import os
import queue
import threading
from collections import deque
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request

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


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


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
# Listener
# ---------------------------------------------------------------------------
@app.post("/api/listener/start")
def listener_start():
    body = request.get_json(force=True) or {}
    try:
        engine.toggle_listener(
            token_nick=str(body.get("token", "")).strip(),
            chan_id=str(body.get("channel_id", "")).strip(),
            teacher_id=str(body.get("teacher_id", "")).strip(),
            target_job_id=str(body.get("target_job_id", "")).strip(),
            slash_input=str(body.get("slash_input", "")).strip(),
            slash_channel=str(body.get("slash_channel", "")).strip(),
            slash_sorting=str(body.get("slash_sorting", "Interval")),
            force_state=True,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"listening": engine.listening})


@app.post("/api/listener/stop")
def listener_stop():
    engine.toggle_listener(force_state=False)
    return jsonify({"listening": engine.listening})


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
    try:
        job, redacted = engine.create_job(
            acc=str(body.get("acc", "")).strip(),
            chan=str(body.get("chan", "")).strip(),
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
    try:
        job = engine.update_job(
            job_id,
            acc=str(body.get("acc", "")).strip(),
            chan=str(body.get("chan", "")).strip(),
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
