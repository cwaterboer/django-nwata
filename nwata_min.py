import time
import sqlite3
import threading
import platform
import requests
import json
import os
from datetime import datetime, timezone, timedelta

# -----------------------------
# CONFIG
# -----------------------------
DB_PATH = "nwata.db"
TOKEN_FILE = "device_token.json"
DJANGO_API_URL = "https://effective-fishstick-jwj65pv99w9fq4j9-8000.app.github.dev"
SYNC_BATCH_SIZE = 20
TRACK_INTERVAL = 1  # seconds
SYNC_INTERVAL = 10  # flush every 10s
ACTIVE_FLUSH_INTERVAL = 20  # flush even if unchanged

# -----------------------------
# OS WINDOW DETECTION
# -----------------------------
if platform.system() == "Windows":
    import win32gui
elif platform.system() == "Darwin":
    from AppKit import NSWorkspace

def get_active_window():
    try:
        if platform.system() == "Windows":
            return win32gui.GetWindowText(win32gui.GetForegroundWindow())
        elif platform.system() == "Darwin":
            app = NSWorkspace.sharedWorkspace().activeApplication()
            return app.get("NSApplicationName", "Unknown")
    except Exception:
        return "Unknown"

# -----------------------------
# LOCAL DATABASE
# -----------------------------
class LocalDB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            window_title TEXT,
            app_name TEXT,
            start_time TEXT,
            end_time TEXT,
            synced INTEGER DEFAULT 0
        )
        """)
        self.conn.commit()

    def insert_log(self, log):
        self.conn.execute("""
        INSERT INTO activity_log (window_title, app_name, start_time, end_time)
        VALUES (?, ?, ?, ?)
        """, (
            log["window_title"],
            log["app_name"],
            log["start_time"],
            log["end_time"],
        ))
        self.conn.commit()
        print(f"[LOG] {log}")

    def fetch_unsynced(self, limit):
        cur = self.conn.cursor()
        cur.execute("""
        SELECT id, window_title, app_name, start_time, end_time
        FROM activity_log
        WHERE synced = 0
        LIMIT ?
        """, (limit,))
        return cur.fetchall()

    def mark_synced(self, ids):
        if not ids:
            return
        self.conn.executemany(
            "UPDATE activity_log SET synced = 1 WHERE id = ?",
            [(i,) for i in ids]
        )
        self.conn.commit()

# -----------------------------
# DEVICE AUTH MANAGEMENT
# -----------------------------
class DeviceAuth:
    def __init__(self, api_url, token_file=TOKEN_FILE):
        self.api_url = api_url
        self.token_file = token_file
        self.token_data = self.load_token()

    def load_token(self):
        if os.path.exists(self.token_file):
            with open(self.token_file, "r") as f:
                return json.load(f)
        return {}

    def save_token(self, data):
        with open(self.token_file, "w") as f:
            json.dump(data, f)
        self.token_data = data

    @property
    def token(self):
        return self.token_data.get("token")

    @property
    def expires_at(self):
        ts = self.token_data.get("expires_at")
        return datetime.fromisoformat(ts) if ts else None

    def is_valid(self):
        return self.token and self.expires_at and datetime.now(timezone.utc) < self.expires_at - timedelta(seconds=30)

    def register_device(self, email, password, device_name):
        payload = {"email": email, "password": password, "device_name": device_name}
        try:
            res = requests.post(f"{self.api_url}/api/device/register/", json=payload, timeout=5)
            res.raise_for_status()
            data = res.json()
            self.save_token({
                "token": data["token"],
                "expires_at": data["token_expires_at"],
                "user": data["user"],
                "organization": data["organization"]
            })
            print("[AUTH] Device registered and token saved.")
            return True
        except Exception as e:
            print("[AUTH ERROR] Registration failed:", e)
            return False

    def refresh_token(self):
        if not self.token:
            return False
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            res = requests.post(f"{self.api_url}/api/device/auth/", headers=headers, timeout=5)
            res.raise_for_status()
            data = res.json()
            self.save_token({
                "token": data["token"],
                "expires_at": data["token_expires_at"],
                "user": data.get("user", self.token_data.get("user")),
                "organization": data.get("organization", self.token_data.get("organization"))
            })
            print("[AUTH] Token refreshed.")
            return True
        except Exception as e:
            print("[AUTH ERROR] Token refresh failed:", e)
            return False

# -----------------------------
# SYNC ENGINE
# -----------------------------
class DjangoSync:
    def __init__(self, db: LocalDB, auth: DeviceAuth):
        self.db = db
        self.auth = auth
        self.last_flush = time.time()

    def _headers(self):
        return {"Authorization": f"Bearer {self.auth.token}"}

    def flush(self):
        if not self.auth.is_valid():
            self.auth.refresh_token()
            if not self.auth.is_valid():
                print("[SYNC] Token invalid, cannot flush")
                return

        rows = self.db.fetch_unsynced(SYNC_BATCH_SIZE)
        if not rows:
            return

        payload = []
        ids = []

        for r in rows:
            ids.append(r[0])
            payload.append({
                "window_title": r[1],
                "app_name": r[2],
                "start_time": r[3],
                "end_time": r[4],
            })

        try:
            res = requests.post(f"{self.auth.api_url}/api/activity/", json=payload, headers=self._headers(), timeout=5)
            if 200 <= res.status_code < 300:
                self.db.mark_synced(ids)
                print(f"[SYNC] Uploaded {len(ids)} logs")
            else:
                print(f"[SYNC ERROR] Status {res.status_code} - {res.text}")
        except Exception as e:
            print("[SYNC ERROR]", e)

    def signal(self, event_type: str):
        if not self.auth.is_valid():
            self.auth.refresh_token()
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = [{"window_title": f"__agent_{event_type}__", "app_name": "__agent__",
                    "start_time": now_utc,
                    "end_time": now_utc}]
        try:
            res = requests.post(f"{self.auth.api_url}/api/device/lifecycle/", json=payload, headers=self._headers(), timeout=5)
            print(f"[SIGNAL] {event_type.upper()} sent, status {getattr(res,'status_code','fail')}")
        except Exception as e:
            print(f"[SIGNAL ERROR] {event_type.upper()} -", e)

# -----------------------------
# TRACKER AGENT
# -----------------------------
class TrackerAgent:
    def __init__(self, db, sync: DjangoSync):
        self.db = db
        self.sync = sync
        self.running = False
        self.last_window = None
        self.last_time = None

    def start(self):
        self.running = True
        self.sync.signal("start")
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._sync_loop, daemon=True).start()
        print("[AGENT] Started")

    def stop(self):
        if self.last_window and self.last_time:
            now_iso = datetime.now(timezone.utc).isoformat()
            self.db.insert_log({
                "window_title": self.last_window,
                "app_name": self.last_window.split(" - ")[0],
                "start_time": self.last_time,
                "end_time": now_iso,
            })
        self.running = False
        self.sync.signal("stop")

    def _loop(self):
        last_flush = time.time()
        while self.running:
            current = get_active_window()
            now_iso = datetime.now(timezone.utc).isoformat()

            # First observation
            if self.last_window is None:
                self.last_window = current
                self.last_time = now_iso
                time.sleep(TRACK_INTERVAL)
                continue

            # Context switch detected
            if current != self.last_window or (time.time() - last_flush) > ACTIVE_FLUSH_INTERVAL:
                log = {
                    "window_title": self.last_window,
                    "app_name": self.last_window.split(" - ")[0],
                    "start_time": self.last_time,
                    "end_time": now_iso,
                }
                self.db.insert_log(log)

                # Start new context
                self.last_window = current
                self.last_time = now_iso
                last_flush = time.time()

            time.sleep(TRACK_INTERVAL)

    def _sync_loop(self):
        while self.running:
            self.sync.flush()
            time.sleep(SYNC_INTERVAL)

# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    db = LocalDB(DB_PATH)
    auth = DeviceAuth(DJANGO_API_URL)

    # If no valid token, prompt user
    if not auth.is_valid():
        print("No valid token found. Please sign in:")
        email = input("Email: ")
        password = input("Password: ")
        device_name = input("Device name: ")
        if not auth.register_device(email, password, device_name):
            print("Failed to authenticate device. Exiting.")
            exit(1)

    sync = DjangoSync(db, auth)
    agent = TrackerAgent(db, sync)

    try:
        agent.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
