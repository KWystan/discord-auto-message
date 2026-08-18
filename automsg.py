import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import json, os, threading, time, requests, subprocess, sys, random, re
from datetime import datetime

class PersistentDiscordApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Discord Auto Message - Xeanz Edition (1-3hr Gap Engine)")
        self.root.geometry("960x1080")
        
        self.data_file = "app_data.json"
        self.data = self.load_data_on_startup()
        
        self.running = False
        self.slow_modes = {} 
        self.running_jobs = {}
        self.editing_job_id = None
        self.last_variant_index = {}
        
        # Listener State
        self.listening = False
        self.last_seen_msg_id = None
        self.listener_user_id = None
        
        # Session-Lock Registry
        self.task_locks = self.data.get("task_locks", {})
        
        self.setup_ui()
        self.refresh_ui_lists()
        self.refresh_saved_data_table()
        
        if self.data.get("listener_settings", {}).get("enabled", False):
            self.toggle_listener(force_state=True)

    def load_data_on_startup(self):
        default_data = {
            "tokens": {}, 
            "channels": {}, 
            "webhooks": {}, 
            "replacers": {}, 
            "jobs": [],
            "task_locks": {},
            "humanizer_settings": {
                "simulate_typing": True,
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
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r") as f:
                    content = json.load(f)
                    for key, val in default_data.items():
                        if key not in content:
                            content[key] = val
                    for job in content.get("jobs", []):
                        if "id" not in job: job["id"] = str(random.randint(100000, 999999))
                    return content
            except Exception:
                pass
        return default_data

    def auto_save(self):
        self.data["task_locks"] = self.task_locks
        with open(self.data_file, "w") as f:
            json.dump(self.data, f, indent=4)

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

    def relaunch_app(self):
        self.auto_save()
        self.log("Saving state and relaunching application process...")
        try:
            python = sys.executable
            os.execl(python, python, *sys.argv)
        except Exception as e:
            messagebox.showerror("Relaunch Error", f"Could not restart automatically: {e}")

    def open_json_manually(self):
        self.auto_save() 
        try:
            if sys.platform == "win32":
                os.startfile(self.data_file)
            elif sys.platform == "darwin":
                subprocess.call(["open", self.data_file])
            else:
                subprocess.call(["xdg-open", self.data_file])
            self.log("Opened JSON editor.")
        except Exception as e:
            self.log(f"Could not open file: {e}")

    def setup_ui(self):
        manager_frame = tk.LabelFrame(self.root, text="Manager (Tokens, Channels, Webhooks, Replacers)")
        manager_frame.pack(fill="x", padx=10, pady=3)

        input_row = tk.Frame(manager_frame)
        input_row.pack(fill="x", padx=5, pady=2)
        
        tk.Label(input_row, text="Nick / Find:").pack(side="left")
        self.nick_entry = tk.Entry(input_row, width=15)
        self.nick_entry.pack(side="left", padx=5)

        tk.Label(input_row, text="Value / Replace With:").pack(side="left")
        self.val_entry = tk.Entry(input_row, width=35)
        self.val_entry.pack(side="left", padx=5)

        save_btn_row = tk.Frame(manager_frame)
        save_btn_row.pack(fill="x", padx=5, pady=2)
        
        tk.Button(save_btn_row, text="Save Token", bg="#e1e1e1", command=lambda: self.quick_store("tokens")).pack(side="left", padx=2)
        tk.Button(save_btn_row, text="Save Channel", bg="#e1e1e1", command=lambda: self.quick_store("channels")).pack(side="left", padx=2)
        tk.Button(save_btn_row, text="Save Webhook", bg="#e1e1e1", command=lambda: self.quick_store("webhooks")).pack(side="left", padx=2)
        
        tk.Frame(save_btn_row, width=20).pack(side="left")
        self.replacer_mode = tk.StringVar(value="store")
        tk.Radiobutton(save_btn_row, text="Store Rule", variable=self.replacer_mode, value="store", font=("Arial", 8)).pack(side="left")
        tk.Radiobutton(save_btn_row, text="Literal Replace", variable=self.replacer_mode, value="literal", font=("Arial", 8)).pack(side="left")
        
        tk.Button(save_btn_row, text="EXECUTE REPLACER", bg="#fff3cd", font=("Arial", 9, "bold"), command=lambda: self.quick_store("replacers")).pack(side="left", padx=2)
        tk.Button(save_btn_row, text="MANUAL EDIT (JSON)", bg="#333", fg="white", command=self.open_json_manually).pack(side="right", padx=5)

        table_frame = tk.Frame(manager_frame)
        table_frame.pack(fill="x", padx=5, pady=2)
        
        self.data_tree = ttk.Treeview(table_frame, columns=("Type", "Name", "Value"), show="headings", height=3)
        self.data_tree.heading("Type", text="Type")
        self.data_tree.heading("Name", text="Nickname / Target")
        self.data_tree.heading("Value", text="Value / Replacement")
        self.data_tree.column("Type", width=80)
        self.data_tree.column("Name", width=120)
        self.data_tree.pack(side="left", fill="x", expand=True)
        
        side_btns = tk.Frame(table_frame)
        side_btns.pack(side="left", padx=5)
        tk.Button(side_btns, text="LOAD SELECTED", fg="blue", command=self.load_selected_for_edit).pack(fill="x", pady=1)
        tk.Button(side_btns, text="REMOVE", fg="red", command=self.delete_selected_data).pack(fill="x", pady=1)

        # Humanizer Settings (1-3hr Gap Configuration)
        h_sett = self.data.get("humanizer_settings", {})
        humanizer_frame = tk.LabelFrame(self.root, text="🛡️ Random Gap Settings (Past Cooldown)", bg="#f8f9fa")
        humanizer_frame.pack(fill="x", padx=10, pady=3)

        h_row = tk.Frame(humanizer_frame, bg="#f8f9fa")
        h_row.pack(fill="x", padx=5, pady=2)

        self.typing_var = tk.BooleanVar(value=h_sett.get("simulate_typing", True))
        tk.Checkbutton(h_row, text="Simulate 'is typing...'", variable=self.typing_var, 
                       font=("Arial", 8, "bold"), bg="#f8f9fa", command=self.save_humanizer_settings).pack(side="left", padx=4)

        self.sleep_var = tk.BooleanVar(value=h_sett.get("sleep_hours_enabled", False))
        tk.Checkbutton(h_row, text="Sleep (1AM-8AM)", variable=self.sleep_var, 
        font=("Arial", 8), bg="#f8f9fa", command=self.save_humanizer_settings).pack(side="left", padx=12)

        tk.Button(h_row, text="SAVE SETTINGS", font=("Arial", 7, "bold"), bg="#d1e7dd", command=self.save_humanizer_settings).pack(side="right", padx=5)

        # Scheduler Frame
        job_frame = tk.LabelFrame(self.root, text="Message Scheduler (Supports Multiple Variations via '---')")
        job_frame.pack(fill="x", padx=10, pady=3)

        tk.Label(job_frame, text="Account:").grid(row=0, column=0, sticky="w", padx=5)
        self.token_cb = ttk.Combobox(job_frame, state="readonly", width=18)
        self.token_cb.grid(row=0, column=1, padx=5, pady=3)

        tk.Label(job_frame, text="Channel:").grid(row=0, column=2, sticky="w", padx=5)
        self.chan_cb = ttk.Combobox(job_frame, state="readonly", width=18)
        self.chan_cb.grid(row=0, column=3, padx=5, pady=3)

        tk.Label(job_frame, text="Log to Webhook:").grid(row=0, column=4, sticky="w", padx=5)
        self.webhook_cb = ttk.Combobox(job_frame, state="readonly", width=18)
        self.webhook_cb.grid(row=0, column=5, padx=5, pady=3)

        tk.Label(job_frame, text="Message:\n(Separate by\n--- for pools)", font=("Arial", 8)).grid(row=1, column=0, sticky="nw", padx=5)
        
        msg_container = tk.Frame(job_frame)
        msg_container.grid(row=1, column=1, columnspan=3, sticky="we", padx=5, pady=3)
        
        self.msg_text = tk.Text(msg_container, width=42, height=6, font=("Arial", 9))
        self.msg_text.pack(side="top", fill="x", expand=True)
        
        tag_row = tk.Frame(msg_container)
        tag_row.pack(side="top", fill="x")
        tk.Label(tag_row, text="Quick Tools:", font=("Arial", 7)).pack(side="left")
        tk.Button(tag_row, text="{time}", font=("Arial", 7), command=lambda: self.msg_text.insert(tk.INSERT, "{time}")).pack(side="left", padx=2)
        tk.Button(tag_row, text="{min}", font=("Arial", 7), command=lambda: self.msg_text.insert(tk.INSERT, "{min}")).pack(side="left", padx=2)
        tk.Button(tag_row, text="+ '---' (Separator)", bg="#fff3cd", font=("Arial", 7, "bold"), command=lambda: self.msg_text.insert(tk.INSERT, "\n---\n")).pack(side="left", padx=4)
        
        right_container = tk.Frame(job_frame)
        right_container.grid(row=1, column=4, columnspan=2, sticky="nw", padx=5, pady=3)

        settings_col = tk.Frame(right_container)
        settings_col.pack(side="left", anchor="nw")

        tk.Label(settings_col, text="Base Interval (120 Min):").pack(anchor="w")
        int_input_frame = tk.Frame(settings_col)
        int_input_frame.pack(anchor="w", pady=(0, 5))
        
        self.int_entry = tk.Entry(int_input_frame, width=8)
        self.int_entry.insert(0, "120")
        self.int_entry.pack(side="left")
        
        self.unit_cb = ttk.Combobox(int_input_frame, values=["Sec", "Min"], state="readonly", width=5)
        self.unit_cb.set("Min")
        self.unit_cb.pack(side="left", padx=2)

        self.edit_options_frame = tk.LabelFrame(settings_col, text="On Update", fg="gray")
        self.edit_options_frame.pack(anchor="w", fill="x", pady=2)
        
        self.update_mode = tk.StringVar(value="wait")
        self.rb_now = tk.Radiobutton(self.edit_options_frame, text="Send Now", variable=self.update_mode, value="now", state="disabled")
        self.rb_now.pack(anchor="w")
        self.rb_wait = tk.Radiobutton(self.edit_options_frame, text="Continue Count", variable=self.update_mode, value="wait", state="disabled")
        self.rb_wait.pack(anchor="w")

        edit_btn_col = tk.Frame(right_container)
        edit_btn_col.pack(side="left", anchor="center", padx=(15, 0), pady=(10, 0))
        
        tk.Button(edit_btn_col, text="EDIT SELECTED\nTASK", bg="#ffc107", fg="black", 
                  font=("Arial", 9, "bold"), width=14, height=2, command=self.load_task_for_edit).pack()

        self.add_btn = tk.Button(job_frame, text="ADD TO QUEUE", bg="#007acc", fg="white", font=("Arial", 9, "bold"), 
                  command=self.add_or_update_job)
        self.add_btn.grid(row=2, column=1, columnspan=5, padx=5, pady=3, sticky="nsew")

        # Listener Frame
        listener_frame = tk.LabelFrame(self.root, text="Auto-Grab Listener (Players / Multiple Accounts Connection)")
        listener_frame.pack(fill="x", padx=10, pady=3)
        
        l_inputs = tk.Frame(listener_frame)
        l_inputs.pack(fill="x", padx=5, pady=2)
        
        tk.Label(l_inputs, text="Listener's Token:").grid(row=0, column=0, sticky="w", padx=2)
        self.listener_token_cb = ttk.Combobox(l_inputs, state="readonly", width=18)
        self.listener_token_cb.grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(l_inputs, text="Channel/DM ID:").grid(row=0, column=2, sticky="w", padx=2)
        self.listener_chan_entry = tk.Entry(l_inputs, width=20)
        self.listener_chan_entry.grid(row=0, column=3, padx=5, pady=2)
        
        tk.Label(l_inputs, text="Sender Whitelist (Optional):").grid(row=1, column=0, sticky="w", padx=2)
        self.listener_teacher_entry = tk.Entry(l_inputs, width=20)
        self.listener_teacher_entry.grid(row=1, column=1, padx=5, pady=2)
        
        tk.Label(l_inputs, text="Default Target Task:").grid(row=1, column=2, sticky="w", padx=2)
        self.listener_task_cb = ttk.Combobox(l_inputs, state="readonly", width=18)
        self.listener_task_cb.grid(row=1, column=3, padx=5, pady=2)

        slash_bar = tk.Frame(listener_frame, bg="#2f3136", bd=1, relief="solid")
        slash_bar.pack(fill="x", padx=5, pady=3)
        
        tk.Label(slash_bar, text=" /search ", fg="#00b0f4", bg="#2f3136", font=("Arial", 8, "bold")).pack(side="left", padx=2)
        tk.Label(slash_bar, text=" input ", fg="#b9bbbe", bg="#4f545c", font=("Arial", 7)).pack(side="left", padx=(2, 0))
        self.slash_input_entry = tk.Entry(slash_bar, bg="#202225", fg="white", insertbackground="white", bd=0, width=15, font=("Arial", 8))
        self.slash_input_entry.pack(side="left", padx=(0, 5), pady=2)
        
        tk.Label(slash_bar, text=" accessible ", fg="#ffffff", bg="#f04747", font=("Arial", 7)).pack(side="left")
        self.slash_chan_entry = tk.Entry(slash_bar, bg="#202225", fg="white", insertbackground="white", bd=0, width=15, font=("Arial", 8))
        self.slash_chan_entry.pack(side="left", padx=(0, 5), pady=2)
        
        tk.Label(slash_bar, text=" sorting ", fg="#ffffff", bg="#faa61a", font=("Arial", 7)).pack(side="left")
        self.slash_sorting_cb = ttk.Combobox(slash_bar, values=["Interval", "Message"], state="readonly", width=8, font=("Arial", 8))
        self.slash_sorting_cb.set("Interval")
        self.slash_sorting_cb.pack(side="left", padx=(0, 5), pady=2)
        
        self.btn_listener = tk.Button(listener_frame, text="ACTIVATE LISTENER", bg="#17a2b8", fg="white", font=("Arial", 8, "bold"), command=self.toggle_listener)
        self.btn_listener.pack(side="right", padx=10, pady=3)

        # Queue Table
        self.tree = ttk.Treeview(self.root, columns=("Acc", "Chan", "Int", "Unit", "Message", "Webhook"), show="headings", height=5)
        for h in ["Acc", "Chan", "Int", "Unit", "Message", "Webhook"]: self.tree.heading(h, text=h)
        self.tree.column("Int", width=60)
        self.tree.column("Unit", width=60)
        self.tree.pack(fill="x", padx=10, pady=2)

        # Log Box
        self.log_box = tk.Text(self.root, height=8, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9))
        self.log_box.pack(fill="both", padx=10, pady=3)

        # Footer
        footer = tk.Frame(self.root)
        footer.pack(fill="x", padx=10, pady=3)
        
        self.btn_run = tk.Button(footer, text="START ENGINE", bg="#28a745", fg="white", width=18, height=2, font=("Arial", 10, "bold"), command=self.toggle_engine)
        self.btn_run.pack(side="left", padx=5)
        
        tk.Button(footer, text="RELAUNCH / HOT-RELOAD", bg="#17a2b8", fg="white", width=22, height=2, font=("Arial", 9, "bold"), command=self.relaunch_app).pack(side="left", padx=5)
        tk.Button(footer, text="REMOVE TASK", bg="#dc3545", fg="white", command=self.delete_job).pack(side="right", padx=5)

    def save_humanizer_settings(self):
        self.data["humanizer_settings"] = {
            "simulate_typing": self.typing_var.get(),
            "sleep_hours_enabled": self.sleep_var.get(),
            "sleep_start_hour": 1,
            "sleep_end_hour": 8
        }
        self.auto_save()
        self.log(f"🛡️ Settings Saved: Simulate typing = {self.typing_var.get()} | Sleep={self.sleep_var.get()}")

    def quick_store(self, cat):
        name, val = self.nick_entry.get().strip(), self.val_entry.get().strip()
        if cat == "replacers" and self.replacer_mode.get() == "literal":
            content = self.msg_text.get("1.0", tk.END)
            new_content = content.replace(name, val)
            self.msg_text.delete("1.0", tk.END)
            self.msg_text.insert("1.0", new_content)
            self.log(f"Executed literal replace: '{name}' -> '{val}'")
            return

        if name and val:
            self.data[cat][name] = val
            self.auto_save()
            self.refresh_saved_data_table()
            self.refresh_ui_lists()
            self.log(f"Saved {cat[:-1]}: {name}")
            self.nick_entry.delete(0, tk.END); self.val_entry.delete(0, tk.END)

    def refresh_saved_data_table(self):
        for i in self.data_tree.get_children(): self.data_tree.delete(i)
        for cat in ["tokens", "channels", "webhooks", "replacers"]:
            for name, val in self.data[cat].items():
                if cat == "tokens": d_val = "•••••••••••••••• [TOKEN HIDDEN]"
                elif cat == "webhooks": d_val = "•••••••••••••••• [WEBHOOK HIDDEN]"
                else: d_val = val if len(val) < 40 else val[:37] + "..."
                self.data_tree.insert("", "end", values=(cat[:-1].capitalize(), name, d_val), tags=(cat, name))

    def load_selected_for_edit(self):
        sel = self.data_tree.selection()
        if not sel: return
        tags = self.data_tree.item(sel[0], "tags")
        if tags:
            self.nick_entry.delete(0, tk.END); self.nick_entry.insert(0, tags[1])
            self.val_entry.delete(0, tk.END); self.val_entry.insert(0, self.data[tags[0]][tags[1]])

    def delete_selected_data(self):
        sel = self.data_tree.selection()
        if not sel: return
        tags = self.data_tree.item(sel[0], "tags")
        if tags:
            del self.data[tags[0]][tags[1]]
            self.auto_save(); self.refresh_saved_data_table(); self.refresh_ui_lists()

    def load_task_for_edit(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Task", "Please select a task from the queue to edit.")
            return
        idx = self.tree.index(sel[0])
        job = self.data["jobs"][idx]
        self.token_cb.set(job["acc"])
        self.chan_cb.set(job["chan"])
        self.webhook_cb.set(job.get("web", "None"))
        self.msg_text.delete("1.0", tk.END)
        self.msg_text.insert("1.0", job["msg"])
        self.int_entry.delete(0, tk.END)
        self.int_entry.insert(0, job["int"])
        self.unit_cb.set(job.get("unit", "Min"))
        self.editing_job_id = job["id"]
        
        self.edit_options_frame.config(fg="black")
        self.rb_now.config(state="normal")
        self.rb_wait.config(state="normal")
        self.update_mode.set("wait")

        self.add_btn.config(text="UPDATE TASK", bg="#20c997")
        self.log(f"Editing task {job['id']}...")

    def add_or_update_job(self):
        acc, chan, web = self.token_cb.get(), self.chan_cb.get(), self.webhook_cb.get()
        msg, interval, unit = self.msg_text.get("1.0", tk.END).strip(), self.int_entry.get(), self.unit_cb.get()
        
        if not (acc and chan and msg):
            messagebox.showwarning("Missing Data", "Ensure Account, Channel, and Message are filled.")
            return

        if self.contains_sensitive_data(msg):
            ans = messagebox.askyesno("⚠️ Warning: Discord Authorization Detected", 
                "WARNING: Your message content consists of sensitive Discord Authorization information!\n\n"
                "Replace the tokens with a placeholder?")
            if ans: msg = self.clean_sensitive_data(msg)

        if self.editing_job_id:
            for job in self.data["jobs"]:
                if job["id"] == self.editing_job_id:
                    sanitized_msg = self.clean_sensitive_data(msg)
                    job.update({"acc": acc, "chan": chan, "msg": sanitized_msg, "int": interval, "unit": unit, "web": web})
                    if self.update_mode.get() == "now":
                        self.running_jobs[self.editing_job_id] = 0
                        self.log(f"Task {self.editing_job_id} updated -> Forced SEND NOW.")
                    else:
                        self.log(f"Task {self.editing_job_id} updated -> Continuing countdown.")
                    break
            
            self.editing_job_id = None
            self.add_btn.config(text="ADD TO QUEUE", bg="#007acc")
            self.rb_now.config(state="disabled")
            self.rb_wait.config(state="disabled")
            self.edit_options_frame.config(fg="gray")
        else:
            job_id = str(random.randint(100000, 999999))
            sanitized_msg = self.clean_sensitive_data(msg)
            job = {"id": job_id, "acc": acc, "chan": chan, "msg": sanitized_msg, "int": interval, "unit": unit, "web": web}
            self.data["jobs"].append(job)
            if self.running:
                threading.Thread(target=self.worker, args=(job, 0), daemon=True).start()
            self.log(f"New task added to queue.")

        self.auto_save()
        self.refresh_ui_lists()
        self.msg_text.delete("1.0", tk.END)

    def extract_variants(self, raw_text):
        raw_text = raw_text.strip()
        if not raw_text: return [""]
        if "---" in raw_text or "===" in raw_text:
            parts = re.split(r'\n?\s*(?:---|===)\s*\n?', raw_text)
            variants = [p.strip() for p in parts if p.strip()]
            if variants: return variants
        return [raw_text]

    def pick_next_variant(self, job_id, raw_text):
        variants = self.extract_variants(raw_text)
        total = len(variants)
        if total == 1: return variants[0], 1, 1
        last_idx = self.last_variant_index.get(job_id, -1)
        available_indices = [i for i in range(total) if i != last_idx]
        chosen_idx = random.choice(available_indices) if available_indices else 0
        self.last_variant_index[job_id] = chosen_idx
        return variants[chosen_idx], chosen_idx + 1, total

    def refresh_ui_lists(self):
        tokens = list(self.data["tokens"].keys())
        self.token_cb['values'] = tokens
        self.listener_token_cb['values'] = tokens
        
        self.chan_cb['values'] = list(self.data["channels"].keys())
        self.webhook_cb['values'] = ["None"] + list(self.data["webhooks"].keys())
        
        job_display_list = [f"{j['acc']} -> {j['chan']} ({j['id']})" for j in self.data["jobs"]]
        self.listener_task_cb['values'] = job_display_list
        
        sett = self.data.get("listener_settings", {})
        if sett.get("token"): self.listener_token_cb.set(sett.get("token"))
        if sett.get("channel_id"):
            self.listener_chan_entry.delete(0, tk.END)
            self.listener_chan_entry.insert(0, sett.get("channel_id"))
        if sett.get("teacher_id"):
            self.listener_teacher_entry.delete(0, tk.END)
            self.listener_teacher_entry.insert(0, sett.get("teacher_id"))
        if sett.get("target_job_id"):
            target_id = sett.get("target_job_id")
            for display_str in job_display_list:
                if f"({target_id})" in display_str:
                    self.listener_task_cb.set(display_str)
                    break
        
        if sett.get("slash_input"):
            self.slash_input_entry.delete(0, tk.END)
            self.slash_input_entry.insert(0, sett.get("slash_input"))
        if sett.get("slash_channel"):
            self.slash_chan_entry.delete(0, tk.END)
            self.slash_chan_entry.insert(0, sett.get("slash_channel"))
        if sett.get("slash_sorting"):
            self.slash_sorting_cb.set(sett.get("slash_sorting"))

        for i in self.tree.get_children(): self.tree.delete(i)
        for j in self.data["jobs"]:
            variants = self.extract_variants(j["msg"])
            preview = variants[0][:28].replace("\n", " ")
            if len(variants) > 1:
                preview = f"[{len(variants)} Variants] {preview}..."
            self.tree.insert("", "end", values=(j["acc"], j["chan"], j["int"], j["unit"], preview, j["web"]))

    def delete_job(self):
        sel = self.tree.selection()
        if sel:
            idx = self.tree.index(sel[0])
            job = self.data["jobs"].pop(idx)
            if job["id"] in self.running_jobs: del self.running_jobs[job["id"]]
            if job["id"] in self.task_locks: del self.task_locks[job["id"]]
            self.auto_save(); self.refresh_ui_lists()
            self.log(f"Task {job['id']} removed.")

    def log(self, msg):
        cleaned_msg = self.clean_sensitive_data(str(msg))
        self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {cleaned_msg}\n")
        self.log_box.see("end")

    def toggle_engine(self):
        if not self.running:
            self.running = True
            self.btn_run.config(text="STOP ENGINE", bg="#dc3545")
            self.log(">>> ENGINE STARTING <<<")
            
            stagger_interval = 2.0
            for idx, job in enumerate(self.data["jobs"]):
                stagger_delay = idx * stagger_interval
                threading.Thread(target=self.worker, args=(job, stagger_delay), daemon=True).start()
        else:
            self.running = False
            self.running_jobs.clear()
            self.btn_run.config(text="START ENGINE", bg="#28a745")
            self.log(">>> ENGINE SHUTDOWN <<<")

    def toggle_listener(self, force_state=None):
        target_state = not self.listening if force_state is None else force_state
        if target_state:
            token_nick = self.listener_token_cb.get()
            chan_id = self.listener_chan_entry.get().strip()
            teacher_id = self.listener_teacher_entry.get().strip()
            task_selection = self.listener_task_cb.get()
            slash_input = self.slash_input_entry.get().strip()
            slash_channel = self.slash_chan_entry.get().strip()
            slash_sorting = self.slash_sorting_cb.get()
            
            if not token_nick or not chan_id or not task_selection:
                messagebox.showwarning("Listener Error", "Please configure listener Token, Channel ID, and default target.")
                return
                
            try:
                target_job_id = task_selection.split("(")[-1].replace(")", "").strip()
            except Exception:
                messagebox.showerror("Selection Error", "Invalid Target Task selected.")
                return
                
            self.data["listener_settings"] = {
                "enabled": True,
                "token": token_nick,
                "channel_id": chan_id,
                "teacher_id": teacher_id,
                "target_job_id": target_job_id,
                "slash_input": slash_input,
                "slash_channel": slash_channel,
                "slash_sorting": slash_sorting
            }
            self.auto_save()
            self.listening = True
            self.btn_listener.config(text="DEACTIVATE LISTENER", bg="#dc3545")
            self.log(f"Auto-Grab Listener ON. Listening in channel {chan_id}...")
            threading.Thread(target=self.listener_worker, daemon=True).start()
        else:
            self.listening = False
            self.data["listener_settings"]["enabled"] = False
            self.auto_save()
            self.btn_listener.config(text="ACTIVATE LISTENER", bg="#17a2b8")
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
                    if r.status_code == 200: self.listener_user_id = r.json().get("id")
                except Exception: pass

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
                        if author_id in whitelisted_ids: authorized = True
                        
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
            except Exception: pass
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
            except Exception: pass 
        elif new_text.startswith("#int"):
            try:
                parts = new_text.split(" ", 3)
                target_job_id = parts[1].strip()
                parsed_interval = parts[2].strip()
                if len(parts) > 3:
                    parsed_unit = parts[3].strip().capitalize()
                    if parsed_unit not in ["Sec", "Min"]: parsed_unit = "Min"
                else:
                    parsed_unit = "Min"
            except Exception: pass

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
            self.root.after(0, self.refresh_ui_lists)

    def get_slow_mode(self, token, cid, chan_name):
        try:
            res = requests.get(f"https://discord.com/api/v10/channels/{cid}", headers={"Authorization": token}, timeout=5)
            if res.status_code == 200:
                self.slow_modes[chan_name] = res.json().get("rate_limit_per_user", 0)
                return
        except Exception: pass
        self.slow_modes[chan_name] = 0

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
            if find: text = text.replace(find, replace)
        return text

    def trigger_typing_indicator(self, token, cid):
        try:
            requests.post(f"https://discord.com/api/v10/channels/{cid}/typing", headers={"Authorization": token}, timeout=4)
        except Exception: pass

    def calculate_human_typing_seconds(self, text):
        char_count = len(text.strip())
        ms_per_char = random.uniform(0.015, 0.025)
        return max(1.2, min(5.0, (char_count * ms_per_char) + random.uniform(0.4, 0.9)))

    def send_humanized_message(self, token, cid, message_text, web_url=None, acc_name="", variant_info=""):
        h_sett = self.data.get("humanizer_settings", {})
        simulate_typing = h_sett.get("simulate_typing", True)

        if simulate_typing:
            typing_sec = self.calculate_human_typing_seconds(message_text)
            self.trigger_typing_indicator(token, cid)
            time.sleep(typing_sec)

        try:
            res = requests.post(f"https://discord.com/api/v10/channels/{cid}/messages", 
                                headers={"Authorization": token, "Content-Type": "application/json"},
                                json={"content": message_text}, timeout=10)
            if res.status_code == 200:
                self.log(f"SENT [{acc_name}] {variant_info}: {message_text[:30]}...")
                if web_url:
                    try:
                        secure_log = self.clean_sensitive_data(f"✅ Sent {variant_info}: {message_text[:40]}...")
                        requests.post(web_url, json={"content": secure_log}, timeout=4)
                    except Exception: pass
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

    def worker(self, job, initial_delay=0):
        jid = job["id"]
        self.running_jobs[jid] = time.time() + initial_delay
        
        if initial_delay > 0:
            self.log(f"Queued [{job['acc']} -> {job['chan']}] with {initial_delay}s startup stagger...")
        
        while self.running and jid in self.running_jobs:
            now = time.time()
            if now >= self.running_jobs[jid]:
                current_job = next((j for j in self.data["jobs"] if j["id"] == jid), None)
                if not current_job: break
                
                token = self.data["tokens"].get(current_job["acc"])
                cid = self.data["channels"].get(current_job["chan"])
                web_url = self.data["webhooks"].get(current_job["web"]) if current_job["web"] != "None" else None
                
                if not token or not cid:
                    self.log(f"Worker {jid} error: Auth/Channel missing.")
                    self.running_jobs[jid] = time.time() + 10
                    continue

                if current_job["chan"] not in self.slow_modes:
                    self.get_slow_mode(token, cid, current_job["chan"])

                # Pick variant from '---' pool
                raw_variant, v_num, v_total = self.pick_next_variant(jid, current_job["msg"])
                v_tag = f"(Variant {v_num}/{v_total})" if v_total > 1 else ""

                # Apply replacers & sanitize
                final_msg = self.clean_sensitive_data(self.apply_replacers(raw_variant))
                
                # Send with typing indicator
                self.send_humanized_message(token, cid, final_msg, web_url, current_job['acc'], v_tag)

                # Compute next run (the configured interval as-is, floored by
                # slowmode + 1s)
                try:
                    ival = float(current_job["int"])
                    base_wait = (ival * 60.0) if current_job["unit"] == "Min" else ival
                    
                    actual_wait = max(base_wait, self.slow_modes.get(current_job["chan"], 0) + 1.0)
                    self.running_jobs[jid] = time.time() + actual_wait
                except Exception:
                    self.running_jobs[jid] = time.time() + 120 * 60
            
            time.sleep(0.5)

if __name__ == "__main__":
    root = tk.Tk()
    app = PersistentDiscordApp(root)
    root.mainloop()