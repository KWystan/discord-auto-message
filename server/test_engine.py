"""
Behavior-parity tests for AutomationEngine (server/engine.py).

Runs against a throwaway data file and MOCKS all Discord network calls —
nothing here touches the network, Firestore, or the real app_data.json.
Firestore is disabled explicitly so tests stay deterministic and offline.

Run:  server/venv/Scripts/python.exe server/test_engine.py
"""

import json
import os
import re
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from engine import AutomationEngine

REAL_REQUESTS = __import__("requests")


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class EngineParityTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="automsg_test_")
        self.data_file = os.path.join(self.tmpdir, "app_data.json")
        self.logs = []
        self.engine = AutomationEngine(
            data_file=self.data_file,
            log_callback=self.logs.append,
            enable_firestore=False,
        )

    # ── persistence ────────────────────────────────────────────────────
    def test_load_data_on_startup_creates_defaults(self):
        d = self.engine.data
        for key in ("tokens", "channels", "webhooks", "replacers", "jobs", "task_locks"):
            self.assertIn(key, d)
        self.assertEqual(d["humanizer_settings"]["simulate_typing"], True)
        self.assertEqual(d["listener_settings"]["slash_sorting"], "Interval")

    def test_load_data_on_startup_migrates_missing_keys(self):
        with open(self.data_file, "w") as f:
            json.dump({"jobs": []}, f)
        e = AutomationEngine(data_file=self.data_file, enable_firestore=False)
        self.assertIn("tokens", e.data)
        self.assertIn("humanizer_settings", e.data)

    def test_auto_save_persists_and_task_locks_synced(self):
        self.engine.task_locks["abc"] = "user1"
        self.engine.auto_save()
        with open(self.data_file) as f:
            saved = json.load(f)
        self.assertEqual(saved["task_locks"], {"abc": "user1"})

    # ── redaction ──────────────────────────────────────────────────────
    def test_clean_sensitive_data_redacts_token_regex(self):
        # Discord token shape: 24-28 . 6 . 27-38 word chars
        token = "abcdefghijklmnopqrstuvwx.abcdef.abcdefghijklmnopqrstuvwxyz1"
        text = f"here is a token {token} and more"
        cleaned = self.engine.clean_sensitive_data(text)
        self.assertIn("[WARNING: SENSITIVE AUTH REDACTED]", cleaned)
        self.assertNotIn(token, cleaned)

    def test_clean_sensitive_data_redacts_stored_token_webhook_channel(self):
        self.engine.data["tokens"]["t"] = "MY-STORED-TOKEN-123"
        self.engine.data["webhooks"]["w"] = "https://discord.com/api/webhooks/123/abc"
        self.engine.data["channels"]["c"] = "987654321"
        text = "token=MY-STORED-TOKEN-123 web=https://discord.com/api/webhooks/123/abc chan=987654321"
        cleaned = self.engine.clean_sensitive_data(text)
        self.assertIn("SENSITIVE AUTH REDACTED", cleaned)
        self.assertIn("WEBHOOK REDACTED", cleaned)
        self.assertIn("CHANNEL ID REDACTED", cleaned)
        self.assertNotIn("MY-STORED-TOKEN-123", cleaned)

    def test_contains_sensitive_data(self):
        token = "abcdefghijklmnopqrstuvwx.abcdef.abcdefghijklmnopqrstuvwxyz1"
        self.assertTrue(self.engine.contains_sensitive_data(token))
        self.assertFalse(self.engine.contains_sensitive_data("just a normal message"))

    # ── job CRUD ───────────────────────────────────────────────────────
    def test_create_job_requires_fields(self):
        with self.assertRaises(ValueError):
            self.engine.create_job("", "chan", "None", "msg", "120", "Min")

    def test_create_job_redacts_sensitive_message(self):
        token = "abcdefghijklmnopqrstuvwx.abcdef.abcdefghijklmnopqrstuvwxyz1"
        job, redacted = self.engine.create_job("acc", "chan", "None", token, "120", "Min")
        self.assertTrue(redacted)
        self.assertIn("[WARNING: SENSITIVE AUTH REDACTED]", job["msg"])
        with open(self.data_file) as f:
            self.assertIn("[WARNING: SENSITIVE AUTH REDACTED]", json.load(f)["jobs"][0]["msg"])

    def test_create_job_plain_message(self):
        job, redacted = self.engine.create_job("acc", "chan", "None", "hello world", "120", "Min")
        self.assertFalse(redacted)
        self.assertEqual(job["msg"], "hello world")
        self.assertIn("id", job)
        self.assertEqual(job["web"], "None")

    def test_update_job_mode_now_sets_running_jobs_zero(self):
        job, _ = self.engine.create_job("acc", "chan", "None", "v1", "120", "Min")
        self.engine.update_job(job["id"], "acc", "chan", "None", "v2", "90", "Sec", mode="now")
        self.assertEqual(self.engine.running_jobs[job["id"]], 0)
        self.assertEqual(self.engine.data["jobs"][0]["msg"], "v2")

    def test_update_job_mode_wait_keeps_countdown(self):
        job, _ = self.engine.create_job("acc", "chan", "None", "v1", "120", "Min")
        self.engine.running_jobs[job["id"]] = 12345
        self.engine.update_job(job["id"], "acc", "chan", "None", "v2", "120", "Min", mode="wait")
        self.assertEqual(self.engine.running_jobs[job["id"]], 12345)

    def test_delete_job_cleans_running_jobs_and_locks(self):
        job, _ = self.engine.create_job("acc", "chan", "None", "v1", "120", "Min")
        self.engine.running_jobs[job["id"]] = 0
        self.engine.task_locks[job["id"]] = "userA"
        self.engine.delete_job(job["id"])
        self.assertEqual(self.engine.data["jobs"], [])
        self.assertNotIn(job["id"], self.engine.running_jobs)
        self.assertNotIn(job["id"], self.engine.task_locks)

    def test_send_now_sets_running_jobs_zero(self):
        job, _ = self.engine.create_job("acc", "chan", "None", "v1", "120", "Min")
        self.engine.running_jobs[job["id"]] = 999
        self.engine.send_now(job["id"])
        self.assertEqual(self.engine.running_jobs[job["id"]], 0)

    # ── variants / spintax / replacers ─────────────────────────────────
    def test_extract_variants(self):
        self.assertEqual(self.engine.extract_variants("a---b---c"), ["a", "b", "c"])
        self.assertEqual(self.engine.extract_variants("a\n===\nb"), ["a", "b"])
        self.assertEqual(self.engine.extract_variants("single"), ["single"])
        self.assertEqual(self.engine.extract_variants(""), [""])

    def test_pick_next_variant_never_repeats(self):
        job_id = "123"
        picks = [self.engine.pick_next_variant(job_id, "a---b---c")[0] for _ in range(6)]
        for i in range(1, len(picks)):
            self.assertNotEqual(picks[i], picks[i - 1])

    def test_resolve_spintax(self):
        for _ in range(20):
            out = self.engine.resolve_spintax("{hi|hello|yo} there")
            self.assertIn(out, ("hi there", "hello there", "yo there"))
        self.assertEqual(self.engine.resolve_spintax("no braces"), "no braces")

    def test_apply_replacers_verbatim_legacy_tag_behavior(self):
        # LEGACY QUIRK (replicated verbatim): resolve_spintax runs first, so
        # single-token {time}/{min}/{date} tags are consumed by spintax and
        # render as literal "time"/"min"/"date" — the {time}->HH:MM:SS replace
        # never fires. This matches the desktop app exactly.
        self.engine.data["replacers"]["PLACEHOLDER"] = "REPLACED"
        out = self.engine.apply_replacers("time={time} min={min} date={date} PLACEHOLDER")
        self.assertEqual(out, "time=time min=min date=date REPLACED")

    def test_apply_replacers_spintax_and_custom(self):
        self.engine.data["replacers"]["PLACEHOLDER"] = "REPLACED"
        out = self.engine.apply_replacers("{hi|hello} PLACEHOLDER")
        self.assertIn(out, ("hi REPLACED", "hello REPLACED"))

    # ── send path (mocked network) ─────────────────────────────────────
    def test_send_humanized_message_success_and_429(self):
        self.engine.data["humanizer_settings"]["simulate_typing"] = False
        with patch.object(REAL_REQUESTS, "post", return_value=FakeResponse(200)) as post:
            ok = self.engine.send_humanized_message("tok", "123", "hello", acc_name="acc")
            self.assertTrue(ok)
            post.assert_called_once()
        with patch.object(REAL_REQUESTS, "post", return_value=FakeResponse(429, {"retry_after": 0})) as post:
            ok = self.engine.send_humanized_message("tok", "123", "hello", acc_name="acc")
            self.assertFalse(ok)
        sent = [l for l in self.logs if "SENT [acc]" in l]
        self.assertTrue(sent)

    def test_worker_engine_loop_sends_and_reschedules(self):
        self.engine.data["humanizer_settings"]["simulate_typing"] = False
        self.engine.data["tokens"]["acc"] = "fake-token"
        self.engine.data["channels"]["chan"] = "123"
        job, _ = self.engine.create_job("acc", "chan", "None", "cycle message", "0.001", "Min")
        sent = {"n": 0}

        def fake_post(url, **kwargs):
            if url.endswith("/typing"):
                return FakeResponse(204)
            sent["n"] += 1
            return FakeResponse(200)

        with patch.object(REAL_REQUESTS, "get", return_value=FakeResponse(200, {"rate_limit_per_user": 0})), \
             patch.object(REAL_REQUESTS, "post", side_effect=fake_post):
            self.engine.start_engine()
            time.sleep(1.5)
            self.engine.stop_engine()

        self.assertGreaterEqual(sent["n"], 1)
        with open(self.data_file) as f:
            saved = json.load(f)
        self.assertEqual(saved["jobs"][0]["msg"], "cycle message")

    # ── webhook posting (no account token) ─────────────────────────────
    def test_send_humanized_message_via_webhook(self):
        self.engine.data["humanizer_settings"]["simulate_typing"] = False
        with patch.object(REAL_REQUESTS, "post", return_value=FakeResponse(200)) as post:
            ok = self.engine.send_humanized_message(
                "", "", "hello",
                web_url="https://discord.com/api/v10/webhooks/111222/abcdef",
                acc_name="wh",
            )
            self.assertTrue(ok)
            url = post.call_args.args[0]
            self.assertIn("/webhooks/111222/abcdef", url)
            self.assertEqual(post.call_args.kwargs["json"]["content"], "hello")
        sent = [l for l in self.logs if "SENT [wh]" in l]
        self.assertTrue(sent)

    def test_send_humanized_message_webhook_invalid_url(self):
        self.engine.data["humanizer_settings"]["simulate_typing"] = False
        with patch.object(REAL_REQUESTS, "post", return_value=FakeResponse(200)) as post:
            ok = self.engine.send_humanized_message("", "", "hi", web_url="not-a-url", acc_name="wh")
            self.assertTrue(ok)
            post.assert_not_called()
        self.assertTrue(any("Invalid webhook URL" in l for l in self.logs))

    def test_worker_webhook_job_sends_without_token(self):
        self.engine.data["humanizer_settings"]["simulate_typing"] = False
        self.engine.data["webhooks"]["w"] = "https://discord.com/api/v10/webhooks/111222/abcdef"
        self.engine.data["channel_meta"]["general"] = {"rate_limit_per_user": 3600}
        job, _ = self.engine.create_job("webhook", "general", "w", "cycle message", "0.001", "Min")
        sent = {"n": 0}

        def fake_post(url, **kwargs):
            if "/typing" in url:
                return FakeResponse(204)
            sent["n"] += 1
            return FakeResponse(200)

        with patch.object(REAL_REQUESTS, "get", return_value=FakeResponse(200, {"rate_limit_per_user": 0})), \
             patch.object(REAL_REQUESTS, "post", side_effect=fake_post):
            self.engine.start_engine()
            time.sleep(1.5)
            self.engine.stop_engine()

        self.assertGreaterEqual(sent["n"], 1)
        self.assertTrue(any("SENT [webhook]" in l for l in self.logs))

    # ── session locks / DM commands ────────────────────────────────────
    def test_apply_grabbed_text_lock_and_block(self):
        job, _ = self.engine.create_job("acc", "chan", "None", "original", "120", "Min")
        self.engine.apply_grabbed_text(job["id"], "new text", None, "userA")
        self.assertEqual(self.engine.task_locks[job["id"]], "userA")
        self.assertEqual(self.engine.data["jobs"][0]["msg"], "new text")

        # Different author is blocked
        self.engine.apply_grabbed_text(job["id"], "sneaky text", None, "userB")
        self.assertEqual(self.engine.data["jobs"][0]["msg"], "new text")
        self.assertTrue(any("ACCESS BLOCKED" in l for l in self.logs))

    def test_apply_grabbed_text_int_command(self):
        job, _ = self.engine.create_job("acc", "chan", "None", "original", "120", "Min")
        self.engine.apply_grabbed_text(job["id"], f"#int {job['id']} 90 Min", None, "userA")
        self.assertEqual(self.engine.data["jobs"][0]["int"], "90")
        self.assertEqual(self.engine.data["jobs"][0]["unit"], "Min")

    def test_apply_grabbed_text_msg_command_sets_send_now_when_running(self):
        job, _ = self.engine.create_job("acc", "chan", "None", "original", "120", "Min")
        self.engine.running = True
        self.engine.running_jobs[job["id"]] = 999
        self.engine.apply_grabbed_text(job["id"], f"#msg {job['id']} brand new", None, "userA")
        self.assertEqual(self.engine.data["jobs"][0]["msg"], "brand new")
        self.assertEqual(self.engine.running_jobs[job["id"]], 0)

    # ── token-auth grab strips token ───────────────────────────────────
    def test_apply_grabbed_text_strips_matched_token_and_auth_prefix(self):
        job, _ = self.engine.create_job("acc", "chan", "None", "original", "120", "Min")
        self.engine.data["tokens"]["t"] = "TOKENVAL123"
        self.engine.apply_grabbed_text(job["id"], "auth: TOKENVAL123 hello world", "TOKENVAL123", "userA")
        self.assertEqual(self.engine.data["jobs"][0]["msg"], "hello world")
        self.assertTrue(any("Token-Auth verified" in l for l in self.logs))


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=2))
