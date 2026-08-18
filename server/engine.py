"""
AutomationEngine — decoupled business logic extracted verbatim from automsg.py
(PersistentDiscordApp). Every mutation, schedule calculation, redaction rule,
and worker-thread behavior is preserved character-for-character; only the UI
sinks were replaced:

  * log()          -> forwards the same "[HH:MM:SS] <sanitized>" line to a
                      callback (SSE broadcast in the web app) instead of a
                      tkinter Text widget.
  * root.after()   -> on_data_change() callback (refresh hook, default no-op).
  * messagebox     -> create/update raise ValueError for validation failures;
                      the sensitive-data dialog becomes auto-redaction with a
                      `redacted` flag returned to the caller.

The engine shares the same app_data.json schema as the desktop app and writes
it with the same auto_save() semantics (full JSON dump, indent=4).

Persistence is Firestore-backed when Firebase credentials are available
(server/firebase-service-account.json or FIREBASE_SERVICE_ACCOUNT_PATH) and
falls back to the local app_data.json full-JSON-dump semantics otherwise.
"""

import copy
import json
import os
import random
import re
import threading
import time
from datetime import datetime

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

FIREBASE_ENABLED_ENV = "FIREBASE_ENABLED"
FIREBASE_CREDENTIAL_ENV = "FIREBASE_SERVICE_ACCOUNT_PATH"
FIRESTORE_COLLECTION_ENV = "FIRESTORE_COLLECTION"
FIRESTORE_DOC_ENV = "FIRESTORE_DOC"

DEFAULT_DATA = {
    "tokens": {},
    "channels": {},
    "webhooks": {},
    "replacers": {},
    "jobs": [],
    "task_locks": {},
    "channel_meta": {},
    "humanizer_settings": {
        "simulate_typing": True,
        "cooldown_buffer_min_hrs": 1.0,   # 1 hour extra
        "cooldown_buffer_max_hrs": 3.0,   # 3 hours extra
        "sleep_hours_enabled": False,
        "sleep_start_hour": 1,
        "sleep_end_hour": 8
    },
    "listener_settings": {
        "enabled": False,
        "token": "",
        "channel_id": "",
        "teacher_id": "",
        "target_job_id": "",
        "slash_input": "",
        "slash_channel": "",
        "slash_sorting": "Interval"
    }
}


class AutomationEngine:
    def __init__(self, data_file="app_data.json", log_callback=None, on_data_change=None, enable_firestore=None):
        self.data_file = data_file
        self._log_callback = log_callback
        self._on_data_change = on_data_change

        if enable_firestore is None:
            enable_firestore = os.getenv(FIREBASE_ENABLED_ENV, "1").lower() not in ("0", "false", "no")
        self._enable_firestore = bool(enable_firestore)
        self._save_lock = threading.Lock()
        self.data = {}
        self._firestore = self._init_firestore()

        self.data = self.load_data_on_startup()

        self.running = False
        self.slow_modes = {}
        self.running_jobs = {}
        self.last_variant_index = {}

        # Listener State
        self.listening = False
        self.last_seen_msg_id = None
        self.listener_user_id = None

        # Session-Lock Registry
        self.task_locks = self.data.get("task_locks", {})

        if self.data.get("listener_settings", {}).get("enabled", False):
            self.toggle_listener(force_state=True)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _init_firestore(self):
        """Return a Firestore client, or None to fall back to app_data.json.

        Credentials come from FIREBASE_SERVICE_ACCOUNT_PATH (env) or the
        auto-detected server/firebase-service-account.json file. Returns None
        when the SDK is missing, no credentials exist, or init fails.
        """
        if not self._enable_firestore:
            return None
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except Exception:
            self.log("Firebase Admin SDK not installed — using local data file.")
            return None

        cred_path = os.getenv(FIREBASE_CREDENTIAL_ENV, "").strip()
        if not cred_path:
            default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firebase-service-account.json")
            if os.path.exists(default_path):
                cred_path = default_path
        if not cred_path or not os.path.exists(cred_path):
            self.log("No Firebase service account found — using local data file.")
            return None

        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(credentials.Certificate(cred_path))
            self._firestore_collection = os.getenv(FIRESTORE_COLLECTION_ENV, "discordautomsg") or "discordautomsg"
            self._firestore_doc = os.getenv(FIRESTORE_DOC_ENV, "app_data") or "app_data"
            return firestore.client()
        except Exception as e:
            self.log(f"Firebase initialization failed ({e}) — using local data file.")
            return None

    def load_data_on_startup(self):
        default_data = copy.deepcopy(DEFAULT_DATA)
        content = None
        from_firestore = False

        if self._firestore is not None:
            try:
                doc = self._firestore.collection(self._firestore_collection).document(self._firestore_doc).get()
                if doc.exists:
                    content = doc.to_dict()
                    from_firestore = True
                    self.log("Loaded data from Firestore.")
            except Exception as e:
                self.log(f"Firestore read failed ({e}) — falling back to local file.")

        if content is None and os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r") as f:
                    content = json.load(f)
            except Exception:
                pass

        if content is None:
            content = {}

        for key, val in default_data.items():
            if key not in content:
                content[key] = val
        for job in content.get("jobs", []):
            if "id" not in job:
                job["id"] = str(random.randint(100000, 999999))

        if self._firestore is not None and not from_firestore:
            try:
                self._firestore.collection(self._firestore_collection).document(self._firestore_doc).set(content)
                self.log("Seeded Firestore with local data.")
            except Exception as e:
                self.log(f"Firestore seed failed ({e}).")

        return content

    def auto_save(self):
        self.data["task_locks"] = self.task_locks
        if self._firestore is not None:
            try:
                with self._save_lock:
                    self._firestore.collection(self._firestore_collection).document(self._firestore_doc).set(self.data)
                return
            except Exception as e:
                self.log(f"Firestore write failed ({e}) — writing local file instead.")
        with open(self.data_file, "w") as f:
            json.dump(self.data, f, indent=4)

    # ------------------------------------------------------------------
    # Redaction
    # ------------------------------------------------------------------
    def contains_sensitive_data(self, text):
        if not isinstance(text, str):
            return False
        token_pattern = r"[\w-]{24,28}\.[\w-]{6}\.[\w-]{27,38}"
        if re.search(token_pattern, text):
            return True
        for tok in self.data.get("tokens", {}).values():
            if tok and len(tok) > 5 and tok in text:
                return True
        for url in self.data.get("webhooks", {}).values():
            if url and len(url) > 10 and url in text:
                return True
        return False

    def clean_sensitive_data(self, text):
        if not isinstance(text, str):
            return text
        cleaned = text
        token_pattern = r"[\w-]{24,28}\.[\w-]{6}\.[\w-]{27,38}"
        if re.search(token_pattern, cleaned):
            cleaned = re.sub(token_pattern, "[WARNING: SENSITIVE AUTH REDACTED]", cleaned)
        for tok in self.data.get("tokens", {}).values():
            if tok and len(tok) > 5 and tok in cleaned:
                cleaned = cleaned.replace(tok, "[WARNING: SENSITIVE AUTH REDACTED]")
        for url in self.data.get("webhooks", {}).values():
            if url and len(url) > 10 and url in cleaned:
                cleaned = cleaned.replace(url, "[WARNING: WEBHOOK REDACTED]")
        for cid in self.data.get("channels", {}).values():
            if cid and len(cid) > 5 and cid in cleaned:
                cleaned = cleaned.replace(cid, "[WARNING: CHANNEL ID REDACTED]")
        return cleaned

    # ------------------------------------------------------------------
    # Manager entries (tokens / channels / webhooks / replacers)
    # ------------------------------------------------------------------
    def extract_channel_id(self, val):
        """Reduce a pasted Discord channel URL to its bare numeric ID."""
        val = str(val).strip()
        m = re.search(r"/channels/\d+/(\d+)", val)   # message link: /channels/GUILD/CHANNEL
        if m:
            return m.group(1)
        m = re.search(r"/channels/(\d+)", val)        # API endpoint: /api/vN/channels/ID/...
        if m:
            return m.group(1)
        return val

    def store_manager_entry(self, cat, name, val):
        if name and val:
            if cat == "channels":
                val = self.extract_channel_id(val)
            self.data[cat][name] = val
            self.auto_save()
            self.log(f"Saved {cat[:-1]}: {name}")

    def delete_manager_entry(self, cat, name):
        if cat in self.data and name in self.data[cat]:
            del self.data[cat][name]
            self.auto_save()

    def replace_data(self, new_data):
        """Manual JSON edit: wholesale data replacement (desktop: open + edit app_data.json)."""
        if not isinstance(new_data, dict):
            raise ValueError("Data must be a JSON object.")
        content = copy.deepcopy(new_data)
        for key, val in DEFAULT_DATA.items():
            if key not in content:
                content[key] = val
        for job in content.get("jobs", []):
            if "id" not in job:
                job["id"] = str(random.randint(100000, 999999))
        self.data = content
        self.task_locks = self.data.get("task_locks", {})
        self.auto_save()

    # ------------------------------------------------------------------
    # Humanizer settings
    # ------------------------------------------------------------------
    def save_humanizer_settings(self, buf_min_entry_text, buf_max_entry_text, typing_var, sleep_var):
        try:
            b_min_hrs = max(0.1, float(buf_min_entry_text.strip()))
            b_max_hrs = max(b_min_hrs, float(buf_max_entry_text.strip()))
        except Exception:
            b_min_hrs, b_max_hrs = 1.0, 3.0

        self.data["humanizer_settings"] = {
            "simulate_typing": typing_var,
            "cooldown_buffer_min_hrs": b_min_hrs,
            "cooldown_buffer_max_hrs": b_max_hrs,
            "sleep_hours_enabled": sleep_var,
            "sleep_start_hour": 1,
            "sleep_end_hour": 8
        }
        self.auto_save()
        self.log(f"🛡️ Settings Saved: Extra Delay = +{b_min_hrs:.1f}h to +{b_max_hrs:.1f}h past timeout | Sleep={sleep_var}")

    # ------------------------------------------------------------------
    # Job CRUD (mutations identical to add_or_update_job / delete_job)
    # ------------------------------------------------------------------
    def create_job(self, acc, chan, web, msg, interval, unit):
        if not (acc and chan and msg):
            raise ValueError("Ensure Account, Channel, and Message are filled.")

        redacted = False
        if self.contains_sensitive_data(msg):
            # Desktop UI asks "Replace the tokens with a placeholder?" — the
            # web API always takes the safe path and reports it via `redacted`.
            msg = self.clean_sensitive_data(msg)
            redacted = True

        job_id = str(random.randint(100000, 999999))
        sanitized_msg = self.clean_sensitive_data(msg)
        job = {"id": job_id, "acc": acc, "chan": chan, "msg": sanitized_msg, "int": interval, "unit": unit, "web": web}
        self.data["jobs"].append(job)
        if self.running:
            threading.Thread(target=self.worker, args=(job, 0), daemon=True).start()
        self.log(f"New task added to queue.")
        self.auto_save()
        return job, redacted

    def update_job(self, job_id, acc, chan, web, msg, interval, unit, mode="wait"):
        for job in self.data["jobs"]:
            if job["id"] == job_id:
                sanitized_msg = self.clean_sensitive_data(msg)
                job.update({"acc": acc, "chan": chan, "msg": sanitized_msg, "int": interval, "unit": unit, "web": web})
                if mode == "now":
                    self.running_jobs[job_id] = 0
                    self.log(f"Task {job_id} updated -> Forced SEND NOW.")
                else:
                    self.log(f"Task {job_id} updated -> Continuing countdown.")
                self.auto_save()
                return job
        raise KeyError(f"Job {job_id} not found")

    def delete_job(self, job_id):
        for idx, job in enumerate(self.data["jobs"]):
            if job["id"] == job_id:
                self.data["jobs"].pop(idx)
                if job_id in self.running_jobs:
                    del self.running_jobs[job_id]
                if job_id in self.task_locks:
                    del self.task_locks[job_id]
                self.auto_save()
                self.log(f"Task {job_id} removed.")
                return job
        raise KeyError(f"Job {job_id} not found")

    def send_now(self, job_id):
        if not any(j["id"] == job_id for j in self.data["jobs"]):
            raise KeyError(f"Job {job_id} not found")
        self.running_jobs[job_id] = 0
        self.log(f"Task {job_id} updated -> Forced SEND NOW.")

    # ------------------------------------------------------------------
    # Variants / spintax / replacers
    # ------------------------------------------------------------------
    def extract_variants(self, raw_text):
        raw_text = raw_text.strip()
        if not raw_text:
            return [""]
        if "---" in raw_text or "===" in raw_text:
            parts = re.split(r'\n?\s*(?:---|===)\s*\n?', raw_text)
            variants = [p.strip() for p in parts if p.strip()]
            if variants:
                return variants
        return [raw_text]

    def pick_next_variant(self, job_id, raw_text):
        variants = self.extract_variants(raw_text)
        total = len(variants)
        if total == 1:
            return variants[0], 1, 1
        last_idx = self.last_variant_index.get(job_id, -1)
        available_indices = [i for i in range(total) if i != last_idx]
        chosen_idx = random.choice(available_indices) if available_indices else 0
        self.last_variant_index[job_id] = chosen_idx
        return variants[chosen_idx], chosen_idx + 1, total

    def resolve_spintax(self, text):
        pattern = re.compile(r'\{([^{}]+)\}')
        while pattern.search(text):
            text = pattern.sub(lambda m: random.choice(m.group(1).split('|')), text)
        return text

    def apply_replacers(self, text):
        text = self.resolve_spintax(text)
        now = datetime.now()
        text = text.replace("{time}", now.strftime("%H:%M:%S"))
        text = text.replace("{min}", now.strftime("%M"))
        text = text.replace("{date}", now.strftime("%Y-%m-%d"))
        for find, replace in self.data.get("replacers", {}).items():
            if find:
                text = text.replace(find, replace)
        return text

    # ------------------------------------------------------------------
    # Discord send path
    # ------------------------------------------------------------------
    def get_slow_mode(self, token, cid, chan_name):
        try:
            res = requests.get(f"https://discord.com/api/v10/channels/{cid}", headers={"Authorization": token}, timeout=5)
            if res.status_code == 200:
                self.slow_modes[chan_name] = res.json().get("rate_limit_per_user", 0)
                return
        except Exception:
            pass
        self.slow_modes[chan_name] = 0

    def trigger_typing_indicator(self, token, cid):
        try:
            requests.post(f"https://discord.com/api/v10/channels/{cid}/typing", headers={"Authorization": token}, timeout=4)
        except Exception:
            pass

    def calculate_human_typing_seconds(self, text):
        char_count = len(text.strip())
        ms_per_char = random.uniform(0.015, 0.025)
        return max(1.2, min(5.0, (char_count * ms_per_char) + random.uniform(0.4, 0.9)))

    def send_humanized_message(self, token, cid, message_text, web_url=None, acc_name="", variant_info=""):
        h_sett = self.data.get("humanizer_settings", {})
        simulate_typing = h_sett.get("simulate_typing", True)

        # Webhooks can't trigger typing indicators — only the token path can.
        if simulate_typing and not web_url:
            typing_sec = self.calculate_human_typing_seconds(message_text)
            self.trigger_typing_indicator(token, cid)
            time.sleep(typing_sec)

        try:
            if web_url:
                # Post directly through the webhook (no account token needed).
                m = re.match(r"https://discord\.com/api/(?:v\d+/)?webhooks/(\d+)/([\w-]+)", web_url)
                if not m:
                    self.log(f"FAIL [{acc_name}]: Invalid webhook URL.")
                    return True
                res = requests.post(
                    f"https://discord.com/api/v10/webhooks/{m.group(1)}/{m.group(2)}",
                    json={"content": message_text}, timeout=10)
            else:
                res = requests.post(f"https://discord.com/api/v10/channels/{cid}/messages",
                                    headers={"Authorization": token, "Content-Type": "application/json"},
                                    json={"content": message_text}, timeout=10)
            if res.status_code == 200:
                self.log(f"SENT [{acc_name}] {variant_info}: {message_text[:30]}...")
            elif res.status_code == 429:
                retry = res.json().get("retry_after", 5)
                self.log(f"⚠️ RATE LIMIT ({acc_name}): Pausing {retry}s")
                time.sleep(retry)
                return False
            else:
                self.log(f"FAIL [{acc_name}]: Status {res.status_code}")
        except Exception as e:
            self.log(f"ERR [{acc_name}]: {e}")

        return True

    # ------------------------------------------------------------------
    # 1-3 HOUR RANDOM GAP CALCULATION PAST TIMEOUT
    # ------------------------------------------------------------------
    def calculate_human_interval(self, base_seconds):
        h_sett = self.data.get("humanizer_settings", {})

        # 1. Sleep Window Check (Optional)
        if h_sett.get("sleep_hours_enabled", False):
            current_hour = datetime.now().hour
            s_start = h_sett.get("sleep_start_hour", 1)
            s_end = h_sett.get("sleep_end_hour", 8)
            if s_start <= current_hour < s_end:
                wake_delay = ((s_end - current_hour) * 3600) + random.uniform(180, 600)
                self.log(f"🌙 Sleep Window Active ({s_start}AM-{s_end}AM). Pausing until morning...")
                return wake_delay

        # 2. Add 1.0 to 3.0 random hours extra past cooldown
        buf_min_hrs = float(h_sett.get("cooldown_buffer_min_hrs", 1.0))
        buf_max_hrs = float(h_sett.get("cooldown_buffer_max_hrs", 3.0))

        if base_seconds >= 1800:  # For 30m+ intervals
            # Pick random extra seconds between 1 hour and 3 hours
            extra_seconds = random.uniform(buf_min_hrs * 3600.0, buf_max_hrs * 3600.0)
            total_seconds = base_seconds + extra_seconds

            total_hrs = total_seconds / 3600.0
            base_hrs = base_seconds / 3600.0
            extra_hrs = extra_seconds / 3600.0

            self.log(f"⏱️ Next cycle in ~{total_hrs:.2f} hrs ({base_hrs:.1f}h timeout + {extra_hrs:.2f}h random gap).")
            return total_seconds
        else:
            variance = base_seconds * 0.15
            return max(5.0, base_seconds + random.uniform(-variance, variance))

    # ------------------------------------------------------------------
    # Worker thread (per job)
    # ------------------------------------------------------------------
    def worker(self, job, initial_delay=0):
        jid = job["id"]
        self.running_jobs[jid] = time.time() + initial_delay

        if initial_delay > 0:
            self.log(f"Queued [{job['acc']} -> {job['chan']}] with {initial_delay}s startup stagger...")

        while self.running and jid in self.running_jobs:
            now = time.time()
            if now >= self.running_jobs[jid]:
                current_job = next((j for j in self.data["jobs"] if j["id"] == jid), None)
                if not current_job:
                    break

                token = self.data["tokens"].get(current_job["acc"])
                cid = self.data["channels"].get(current_job["chan"])
                web_url = self.data["webhooks"].get(current_job["web"]) if current_job["web"] != "None" else None

                # Webhook jobs post without any account token; token jobs need
                # both an auth token and a channel ID.
                if not web_url and (not token or not cid):
                    self.log(f"Worker {jid} error: Auth/Channel missing.")
                    self.running_jobs[jid] = time.time() + 10
                    continue

                if token and current_job["chan"] not in self.slow_modes:
                    self.get_slow_mode(token, cid, current_job["chan"])

                # Pick variant from '---' pool
                raw_variant, v_num, v_total = self.pick_next_variant(jid, current_job["msg"])
                v_tag = f"(Variant {v_num}/{v_total})" if v_total > 1 else ""

                # Apply replacers & sanitize
                final_msg = self.clean_sensitive_data(self.apply_replacers(raw_variant))

                # Send with typing indicator
                self.send_humanized_message(token, cid, final_msg, web_url, current_job['acc'], v_tag)

                # Compute next run (Base 2 hrs + 1 to 3 hours random gap).
                # Slowmode is honored from the live fetch (token jobs) or the
                # persisted channel_meta (webhook jobs — no token to query).
                try:
                    ival = float(current_job["int"])
                    base_wait = (ival * 60.0) if current_job["unit"] == "Min" else ival

                    human_wait = self.calculate_human_interval(base_wait)
                    meta_slow = self.data.get("channel_meta", {}).get(current_job["chan"], {}).get("rate_limit_per_user", 0)
                    slow = max(self.slow_modes.get(current_job["chan"], 0), meta_slow)
                    actual_wait = max(human_wait, slow + 1.0)
                    self.running_jobs[jid] = time.time() + actual_wait
                except Exception:
                    self.running_jobs[jid] = time.time() + 120 * 60

            time.sleep(0.5)

    # ------------------------------------------------------------------
    # Engine start / stop
    # ------------------------------------------------------------------
    def start_engine(self):
        if self.running:
            return False
        self.running = True
        self.log(">>> ENGINE STARTING (1-3HR RANDOM GAP ACTIVE) <<<")

        stagger_interval = 2.0
        for idx, job in enumerate(self.data["jobs"]):
            stagger_delay = idx * stagger_interval
            threading.Thread(target=self.worker, args=(job, stagger_delay), daemon=True).start()
        return True

    def stop_engine(self):
        if not self.running:
            return False
        self.running = False
        self.running_jobs.clear()
        self.log(">>> ENGINE SHUTDOWN <<<")
        return True

    # ------------------------------------------------------------------
    # Auto-Grab Listener (with session locks)
    # ------------------------------------------------------------------
    def toggle_listener(self, token_nick=None, chan_id=None, teacher_id=None, target_job_id=None,
                        slash_input=None, slash_channel=None, slash_sorting=None, force_state=None):
        target_state = (not self.listening) if force_state is None else force_state
        if target_state:
            if not token_nick or not chan_id or not target_job_id:
                raise ValueError("Please configure listener Token, Channel ID, and default target.")

            self.data["listener_settings"] = {
                "enabled": True,
                "token": token_nick,
                "channel_id": chan_id,
                "teacher_id": teacher_id or "",
                "target_job_id": target_job_id,
                "slash_input": slash_input or "",
                "slash_channel": slash_channel or "",
                "slash_sorting": slash_sorting or "Interval"
            }
            self.auto_save()
            self.listening = True
            self.log(f"Auto-Grab Listener ON. Listening in channel {chan_id}...")
            threading.Thread(target=self.listener_worker, daemon=True).start()
        else:
            self.listening = False
            self.data["listener_settings"]["enabled"] = False
            self.auto_save()
            self.log("Auto-Grab Listener OFF.")

    def listener_worker(self):
        while self.listening:
            sett = self.data.get("listener_settings", {})
            token_val = self.data["tokens"].get(sett.get("token"))
            chan_id = sett.get("channel_id")
            teacher_id_raw = sett.get("teacher_id", "")
            target_job_id = sett.get("target_job_id")

            if not token_val or not chan_id:
                time.sleep(5)
                continue

            if not self.listener_user_id:
                try:
                    r = requests.get("https://discord.com/api/v10/users/@me", headers={"Authorization": token_val}, timeout=5)
                    if r.status_code == 200:
                        self.listener_user_id = r.json().get("id")
                except Exception:
                    pass

            try:
                headers = {"Authorization": token_val}
                url = f"https://discord.com/api/v10/channels/{chan_id}/messages?limit=5"
                res = requests.get(url, headers=headers, timeout=5)

                if res.status_code == 200:
                    messages = res.json()
                    for msg in messages:
                        author_id = msg.get("author", {}).get("id")
                        msg_id = msg.get("id")
                        content = msg.get("content", "").strip()

                        if self.listener_user_id and author_id == self.listener_user_id:
                            continue

                        authorized = False
                        matched_token = None

                        whitelisted_ids = [uid.strip() for uid in teacher_id_raw.split(",") if uid.strip()]
                        if author_id in whitelisted_ids:
                            authorized = True

                        for tok_name, tok_val in self.data.get("tokens", {}).items():
                            if tok_val and len(tok_val) > 5 and tok_val in content:
                                authorized = True
                                matched_token = tok_val
                                break

                        if authorized:
                            if self.last_seen_msg_id != msg_id:
                                self.last_seen_msg_id = msg_id
                                if content:
                                    self.apply_grabbed_text(target_job_id, content, matched_token, author_id)
                            break
                elif res.status_code == 429:
                    retry_after = res.json().get("retry_after", 5)
                    time.sleep(retry_after)
                    continue
            except Exception:
                pass
            time.sleep(3.5)

    def apply_grabbed_text(self, job_id, new_text, matched_token=None, author_id="Unknown"):
        if matched_token:
            new_text = new_text.replace(matched_token, "")
            new_text = re.sub(r"\bauth\s*:\s*", "", new_text, flags=re.IGNORECASE)
            new_text = re.sub(r"\bauth\s+", "", new_text, flags=re.IGNORECASE)
            new_text = new_text.strip()
            self.log(f"🔑 Security: Token-Auth verified successfully from sender {author_id}.")
        else:
            self.log(f"📋 Security: Whitelist-Auth verified successfully for Player {author_id}.")

        new_text = self.clean_sensitive_data(new_text)
        updated = False
        parsed_msg = new_text
        parsed_interval = None
        parsed_unit = None
        target_job_id = job_id

        if new_text.startswith("#msg"):
            try:
                parts = new_text.split(" ", 2)
                target_job_id = parts[1].strip()
                parsed_msg = parts[2].strip()
            except Exception:
                pass
        elif new_text.startswith("#int"):
            try:
                parts = new_text.split(" ", 3)
                target_job_id = parts[1].strip()
                parsed_interval = parts[2].strip()
                if len(parts) > 3:
                    parsed_unit = parts[3].strip().capitalize()
                    if parsed_unit not in ["Sec", "Min"]:
                        parsed_unit = "Min"
                else:
                    parsed_unit = "Min"
            except Exception:
                pass

        if target_job_id in self.task_locks:
            current_owner = self.task_locks[target_job_id]
            if author_id != current_owner:
                self.log(f"🛑 ACCESS BLOCKED: Player {author_id} tried to modify Task {target_job_id} which is LOCKED to Player {current_owner}!")
                return
        else:
            self.task_locks[target_job_id] = author_id
            self.log(f"🔒 Session-Lock Engaged: Task {target_job_id} has been securely locked to Player {author_id}.")

        for job in self.data["jobs"]:
            if job["id"] == target_job_id:
                if parsed_interval is not None:
                    if job.get("int") != parsed_interval or job.get("unit") != parsed_unit:
                        job["int"] = parsed_interval
                        job["unit"] = parsed_unit
                        updated = True
                        self.log(f"⭐ DM Command: Updated Task {target_job_id} Interval to {parsed_interval} {parsed_unit}.")
                else:
                    if job.get("msg") != parsed_msg:
                        job["msg"] = parsed_msg
                        updated = True
                        if self.running and target_job_id in self.running_jobs:
                            self.running_jobs[target_job_id] = 0
                        self.log(f"⭐ DM Command: Updated Task {target_job_id} Message.")
                break

        if updated:
            self.auto_save()
            if self._on_data_change:
                self._on_data_change()

    # ------------------------------------------------------------------
    # Logging (same line format as the desktop log box)
    # ------------------------------------------------------------------
    def log(self, msg):
        cleaned_msg = self.clean_sensitive_data(str(msg))
        line = f"[{time.strftime('%H:%M:%S')}] {cleaned_msg}"
        if self._log_callback:
            self._log_callback(line)
