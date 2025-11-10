import customtkinter as ctk
from tkinter import filedialog, messagebox
import json
import requests
import threading
import time
import os
import sqlite3
from datetime import datetime
from PIL import Image
import re
import sys

APP_NAME = "Dark API Tester"

# --- PyInstaller-safe path handling ---
def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS  # PyInstaller temp folder
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- Writable user directory for persistent history ---
USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "Documents", "DarkAPITesterData")
os.makedirs(USER_DATA_DIR, exist_ok=True)

SQLITE_PATH = os.path.join(USER_DATA_DIR, "history.db")
JSON_HISTORY_PATH = os.path.join(USER_DATA_DIR, "history.json")

# --- Folder with icons (asserts, not assets) ---
ICON_DIR = resource_path(os.path.join("asserts", "icons"))

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def now_iso():
    return datetime.utcnow().isoformat() + "Z"

def is_valid_url(url: str) -> bool:
    return bool(re.match(r"^https?://", url.strip()))

def parse_headers_text(text: str):
    raw = text.strip()
    if not raw:
        return {}
    try:
        h = json.loads(raw)
        if isinstance(h, dict):
            return {str(k): str(v) for k, v in h.items()}
        raise ValueError("Headers JSON must be an object")
    except Exception:
        headers = {}
        for line in raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip()] = v.strip()
        return headers


# ------------------ HISTORY STORE ------------------
class HistoryStore:
    def __init__(self):
        self._ensure_sqlite()

    def _ensure_sqlite(self):
        conn = sqlite3.connect(SQLITE_PATH)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            method TEXT, url TEXT, headers TEXT, body TEXT,
            response_status INTEGER, response_headers TEXT,
            response_body TEXT, time_ms REAL, timestamp TEXT
        )
        """)
        conn.commit()
        conn.close()

    def add_entry(self, entry: dict):
        conn = sqlite3.connect(SQLITE_PATH)
        c = conn.cursor()
        c.execute("""
        INSERT INTO history (method,url,headers,body,response_status,response_headers,response_body,time_ms,timestamp)
        VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            entry["method"], entry["url"], json.dumps(entry["headers"]),
            entry["body"], entry["response_status"], json.dumps(entry["response_headers"]),
            entry["response_body"], entry["time_ms"], entry["timestamp"]
        ))
        conn.commit()
        conn.close()
        # also backup to JSON
        history = []
        if os.path.exists(JSON_HISTORY_PATH):
            try:
                with open(JSON_HISTORY_PATH, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []
        history.append(entry)
        with open(JSON_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

    def list_entries(self, limit=100):
        conn = sqlite3.connect(SQLITE_PATH)
        c = conn.cursor()
        c.execute("SELECT id, method, url, response_status, timestamp FROM history ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_entry(self, entry_id):
        conn = sqlite3.connect(SQLITE_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM history WHERE id=?", (entry_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "method": row[1],
            "url": row[2],
            "headers": json.loads(row[3]) if row[3] else {},
            "body": row[4],
            "response_status": row[5],
            "response_headers": json.loads(row[6]) if row[6] else {},
            "response_body": row[7],
            "time_ms": row[8],
            "timestamp": row[9]
        }

    def import_from_json(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                items = json.load(f)
            for entry in items:
                self.add_entry(entry)
            return len(items)
        except Exception as e:
            print(f"⚠️ Failed import: {e}")
            return 0

    def export_to_json(self, filepath):
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            c = conn.cursor()
            c.execute("SELECT method,url,headers,body,response_status,response_headers,response_body,time_ms,timestamp FROM history")
            rows = c.fetchall()
            conn.close()
            data = []
            for r in rows:
                data.append({
                    "method": r[0],
                    "url": r[1],
                    "headers": json.loads(r[2]),
                    "body": r[3],
                    "response_status": r[4],
                    "response_headers": json.loads(r[5]),
                    "response_body": r[6],
                    "time_ms": r[7],
                    "timestamp": r[8]
                })
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return len(data)
        except Exception as e:
            print(f"⚠️ Failed export: {e}")
            return 0


# ------------------ MAIN APP ------------------
class APITesterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.iconbitmap(resource_path(os.path.join("asserts", "icons", "app.ico")))
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.store = HistoryStore()
        self._build_ui()
        self.reload_history()

    def _load_icon(self, name, size=(20, 20)):
        path = os.path.join(ICON_DIR, name)
        if os.path.exists(path):
            return ctk.CTkImage(light_image=Image.open(path), dark_image=Image.open(path), size=size)
        else:
            print(f"⚠️ Icon missing: {path}")
            return None

    def _build_ui(self):
        top = ctk.CTkFrame(self, corner_radius=10)
        top.pack(fill="x", padx=10, pady=10)

        self.url_entry = ctk.CTkEntry(top, placeholder_text="Enter API URL...", width=700)
        self.url_entry.pack(side="left", padx=5)

        self.method_option = ctk.CTkOptionMenu(top, values=["GET", "POST", "PUT", "DELETE", "PATCH"], width=100)
        self.method_option.set("GET")
        self.method_option.pack(side="left", padx=5)

        send_icon = self._load_icon("send.png")
        self.send_btn = ctk.CTkButton(top, text="Send", image=send_icon, compound="left", command=self.send_request)
        self.send_btn.pack(side="left", padx=5)

        clear_icon = self._load_icon("clear.png")
        ctk.CTkButton(top, text="Clear", image=clear_icon, compound="left", command=self.clear_fields).pack(side="left", padx=5)

        # Export/Import buttons
        export_icon = self._load_icon("export.png")
        import_icon = self._load_icon("import.png")
        ctk.CTkButton(top, text="Export", image=export_icon, compound="left", command=self.export_history).pack(side="left", padx=5)
        ctk.CTkButton(top, text="Import", image=import_icon, compound="left", command=self.import_history).pack(side="left", padx=5)

        body_frame = ctk.CTkFrame(self)
        body_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.headers_box = ctk.CTkTextbox(body_frame, height=100)
        self.headers_box.insert("1.0", '{\n  "Content-Type": "application/json"\n}')
        self.headers_box.pack(fill="x", pady=5)

        self.body_box = ctk.CTkTextbox(body_frame, height=150)
        self.body_box.insert("1.0", '{\n  "example": "data"\n}')
        self.body_box.pack(fill="x", pady=5)

        self.response_box = ctk.CTkTextbox(body_frame, height=200)
        self.response_box.insert("1.0", "Response will appear here...")
        self.response_box.pack(fill="both", expand=True, pady=5)

        hist_frame = ctk.CTkFrame(self)
        hist_frame.pack(fill="x", padx=10, pady=10)
        hist_icon = self._load_icon("history.png")
        ctk.CTkLabel(hist_frame, text="History", image=hist_icon, compound="left").pack(anchor="w", pady=4)
        self.hist_list = ctk.CTkOptionMenu(hist_frame, values=["No history yet"])
        self.hist_list.pack(anchor="w", padx=5)
        load_icon = self._load_icon("load.png")
        ctk.CTkButton(hist_frame, text="Load", image=load_icon, compound="left", command=self.load_selected).pack(anchor="w", padx=5, pady=5)

    def send_request(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "Please enter a URL.")
            return
        if not is_valid_url(url):
            messagebox.showwarning(APP_NAME, "URL must start with http:// or https://")
            return
        method = self.method_option.get()
        headers_text = self.headers_box.get("1.0", "end")
        body_text = self.body_box.get("1.0", "end")
        try:
            headers = parse_headers_text(headers_text)
        except ValueError as e:
            messagebox.showerror(APP_NAME, f"Header Error:\n{e}")
            return
        threading.Thread(target=self._send_thread, args=(method, url, headers, body_text), daemon=True).start()

    def _send_thread(self, method, url, headers, body):
        start = time.perf_counter()
        try:
            r = requests.request(method, url, headers=headers, data=body, timeout=30)
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            entry = {
                "method": method, "url": url, "headers": headers, "body": body,
                "response_status": r.status_code, "response_headers": dict(r.headers),
                "response_body": r.text, "time_ms": elapsed, "timestamp": now_iso()
            }
            self.store.add_entry(entry)
            self.after(0, lambda: self._display_response(entry))
            self.after(0, self.reload_history)
        except Exception as e:
            self.after(0, lambda err=e: self.response_box.insert("end", f"\nError: {err}\n"))

    def _display_response(self, entry):
        pretty_body = entry["response_body"]
        try:
            pretty_body = json.dumps(json.loads(pretty_body), indent=2)
        except Exception:
            pass
        text = f"Status: {entry['response_status']}   Time: {entry['time_ms']} ms\n\n"
        text += f"Headers:\n{json.dumps(entry['response_headers'], indent=2)}\n\n"
        text += f"Body:\n{pretty_body}\n"
        self.response_box.delete("1.0", "end")
        self.response_box.insert("1.0", text)

    def reload_history(self):
        rows = self.store.list_entries()
        if not rows:
            self.hist_list.configure(values=["No history yet"])
            return
        display = [f"[{r[0]}] {r[1]} {r[2]} ({r[3]})" for r in rows]
        self.hist_list.configure(values=display)
        self.hist_list.set(display[0])

    def load_selected(self):
        value = self.hist_list.get()
        if not value or value == "No history yet":
            return
        entry_id = int(value.split("]")[0].strip("["))
        entry = self.store.get_entry(entry_id)
        if not entry:
            return
        self.method_option.set(entry["method"])
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, entry["url"])
        self.headers_box.delete("1.0", "end")
        self.headers_box.insert("1.0", json.dumps(entry["headers"], indent=2))
        self.body_box.delete("1.0", "end")
        self.body_box.insert("1.0", entry["body"])
        self._display_response(entry)

    def clear_fields(self):
        self.url_entry.delete(0, "end")
        self.headers_box.delete("1.0", "end")
        self.body_box.delete("1.0", "end")
        self.response_box.delete("1.0", "end")

    # --- EXPORT / IMPORT ---
    def export_history(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            title="Export History"
        )
        if not filepath:
            return
        count = self.store.export_to_json(filepath)
        messagebox.showinfo(APP_NAME, f"Exported {count} entries to:\n{filepath}")

    def import_history(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json")],
            title="Import History"
        )
        if not filepath:
            return
        count = self.store.import_from_json(filepath)
        messagebox.showinfo(APP_NAME, f"Imported {count} entries.")
        self.reload_history()
