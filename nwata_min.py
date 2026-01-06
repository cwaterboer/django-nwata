import time
import sqlite3
import threading
import platform
import requests
import json
import os
import sys
from datetime import datetime, timezone, timedelta

from PyQt5.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QAction,
    QDialog,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)
from PyQt5.QtGui import QIcon, QCursor
from PyQt5.QtCore import Qt
try:
    import PyQt5.QtSvg  # Ensure SVG support gets bundled in PyInstaller
except Exception:
    pass

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
# UTIL: RESOURCE PATH FOR BUNDLED APPS
# -----------------------------
def resource_path(relative_path: str):
    """Resolve path to resources for PyInstaller bundles.
    Uses sys._MEIPASS when running from a frozen executable, otherwise project root.
    """
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


def _resolve_icon_path():
    """Try multiple locations to find the tray icon image.
    Returns (path, QIcon) or (None, QIcon()) if not found.
    """
    candidates = []
    # Preferred packaged path
    candidates.append(resource_path("assets/chart-no-axes-column.png"))
    # Executable dir (PyInstaller onefile extracts resources, but just in case)
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(exe_dir, "assets", "chart-no-axes-column.png"))
    # Project relative (dev run)
    candidates.append(os.path.join(os.path.abspath("."), "assets", "chart-no-axes-column.png"))

    for p in candidates:
        if os.path.exists(p):
            try:
                icon = QIcon(p)
                if not icon.isNull():
                    return p, icon
            except Exception:
                pass

    # Fallback to theme/icon if available
    theme_icon = QIcon.fromTheme("applications-system")
    if not theme_icon.isNull():
        return None, theme_icon
    return None, QIcon()

# -----------------------------
# OS WINDOW DETECTION
# -----------------------------
import subprocess

_APPKIT_AVAILABLE = False

if platform.system() == "Windows":
    try:
        import win32gui
    except ImportError:
        print("[WARNING] win32gui not installed. Windows window detection disabled.")
elif platform.system() == "Darwin":
    try:
        from AppKit import NSWorkspace
        _APPKIT_AVAILABLE = True
    except ImportError:
        print("[WARNING] AppKit/pyobjc not installed. macOS window detection will use fallback.")


def get_active_window():
    """Get the currently active window title."""
    try:
        if platform.system() == "Windows":
            return win32gui.GetWindowText(win32gui.GetForegroundWindow())
        elif platform.system() == "Darwin" and _APPKIT_AVAILABLE:
            app = NSWorkspace.sharedWorkspace().activeApplication()
            return app.get("NSApplicationName", "Unknown")
        elif platform.system() == "Darwin":
            # macOS fallback: use 'lsappinfo'
            result = subprocess.run(
                ["lsappinfo", "info", "-only", "name"],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return "Unknown"
        elif platform.system() == "Linux":
            # Linux: use xdotool to get active window name
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return "Unknown"
        else:
            return "Unknown"
    except Exception as e:
        print(f"[WINDOW_DETECTION_ERROR] {e}")
        return "Unknown"


# -----------------------------
# LOCAL DATABASE
# -----------------------------
class LocalDB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self.conn.execute(
            """
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            window_title TEXT,
            app_name TEXT,
            start_time TEXT,
            end_time TEXT,
            synced INTEGER DEFAULT 0
        )
        """
        )
        self.conn.commit()

    def insert_log(self, log):
        self.conn.execute(
            """
        INSERT INTO activity_log (window_title, app_name, start_time, end_time)
        VALUES (?, ?, ?, ?)
        """,
            (
                log["window_title"],
                log["app_name"],
                log["start_time"],
                log["end_time"],
            ),
        )
        self.conn.commit()
        print(f"[LOG] {log}")

    def fetch_unsynced(self, limit):
        cur = self.conn.cursor()
        cur.execute(
            """
        SELECT id, window_title, app_name, start_time, end_time
        FROM activity_log
        WHERE synced = 0
        LIMIT ?
        """,
            (limit,),
        )
        return cur.fetchall()

    def mark_synced(self, ids):
        if not ids:
            return
        self.conn.executemany(
            "UPDATE activity_log SET synced = 1 WHERE id = ?", [(i,) for i in ids]
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
        return (
            self.token
            and self.expires_at
            and datetime.now(timezone.utc) < self.expires_at - timedelta(seconds=30)
        )

    def register_device(self, email, password, device_name):
        payload = {"email": email, "password": password, "device_name": device_name}
        try:
            res = requests.post(
                f"{self.api_url}/api/device/register/", json=payload, timeout=5
            )
            res.raise_for_status()
            data = res.json()
            self.save_token(
                {
                    "token": data["token"],
                    "expires_at": data["token_expires_at"],
                    "user": data["user"],
                    "organization": data["organization"],
                }
            )
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
            res = requests.post(
                f"{self.api_url}/api/device/auth/", headers=headers, timeout=5
            )
            res.raise_for_status()
            data = res.json()
            self.save_token(
                {
                    "token": data["token"],
                    "expires_at": data["token_expires_at"],
                    "user": data.get("user", self.token_data.get("user")),
                    "organization": data.get(
                        "organization", self.token_data.get("organization")
                    ),
                }
            )
            print("[AUTH] Token refreshed.")
            return True
        except Exception as e:
            print("[AUTH ERROR] Token refresh failed:", e)
            return False

    def clear(self):
        self.token_data = {}
        if os.path.exists(self.token_file):
            os.remove(self.token_file)


# -----------------------------
# SYNC ENGINE
# -----------------------------
class DjangoSync:
    def __init__(self, db: LocalDB, auth: DeviceAuth):
        self.db = db
        self.auth = auth

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
            payload.append(
                {
                    "window_title": r[1],
                    "app_name": r[2],
                    "start_time": r[3],
                    "end_time": r[4],
                }
            )

        try:
            res = requests.post(
                f"{self.auth.api_url}/api/activity/",
                json=payload,
                headers=self._headers(),
                timeout=5,
            )
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
        payload = {
            "event": event_type,
            "timestamp": now_utc,
            "payload": {"agent_version": "1.0", "timestamp": now_utc},
        }
        try:
            res = requests.post(
                f"{self.auth.api_url}/api/device/lifecycle/",
                json=payload,
                headers=self._headers(),
                timeout=5,
            )
            print(
                f"[SIGNAL] {event_type.upper()} sent, status {getattr(res,'status_code','fail')}"
            )
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
        if self.running:
            return
        self.running = True
        self.sync.signal("start")
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._sync_loop, daemon=True).start()
        print("[AGENT] Started")

    def stop(self):
        if not self.running:
            return
        if self.last_window and self.last_time:
            now_iso = datetime.now(timezone.utc).isoformat()
            self.db.insert_log(
                {
                    "window_title": self.last_window,
                    "app_name": self.last_window.split(" - ")[0],
                    "start_time": self.last_time,
                    "end_time": now_iso,
                }
            )
        self.running = False
        self.sync.signal("stop")

    def _loop(self):
        last_flush = time.time()
        while self.running:
            current = get_active_window()
            now_iso = datetime.now(timezone.utc).isoformat()

            if self.last_window is None:
                self.last_window = current
                self.last_time = now_iso
                time.sleep(TRACK_INTERVAL)
                continue

            if current != self.last_window or (time.time() - last_flush) > ACTIVE_FLUSH_INTERVAL:
                log = {
                    "window_title": self.last_window,
                    "app_name": self.last_window.split(" - ")[0],
                    "start_time": self.last_time,
                    "end_time": now_iso,
                }
                self.db.insert_log(log)

                self.last_window = current
                self.last_time = now_iso
                last_flush = time.time()

            time.sleep(TRACK_INTERVAL)

    def _sync_loop(self):
        while self.running:
            self.sync.flush()
            time.sleep(SYNC_INTERVAL)


# -----------------------------
# LOGIN DIALOG
# -----------------------------
class LoginDialog(QDialog):
    def __init__(self, auth: DeviceAuth):
        super().__init__()
        self.auth = auth
        self.setWindowTitle("Nwata Login")
        self.setFixedSize(320, 180)
        self.token_acquired = False

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Email"))
        self.email_input = QLineEdit()
        layout.addWidget(self.email_input)

        layout.addWidget(QLabel("Password"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)

        layout.addWidget(QLabel("Device Name"))
        self.device_input = QLineEdit()
        layout.addWidget(self.device_input)

        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self.handle_login)
        layout.addWidget(self.login_btn)

        self.setLayout(layout)

    def handle_login(self):
        email = self.email_input.text().strip()
        password = self.password_input.text().strip()
        device_name = self.device_input.text().strip()

        if not email or not password or not device_name:
            QMessageBox.warning(self, "Input Error", "All fields are required")
            return

        if self.auth.register_device(email, password, device_name):
            self.token_acquired = True
            QMessageBox.information(self, "Success", f"Logged in as {email}")
            self.accept()
        else:
            QMessageBox.critical(self, "Login Failed", "Unable to authenticate device")


# -----------------------------
# TRAY APPLICATION
# -----------------------------
class TrayApp:
    def __init__(self, db: LocalDB, agent: TrackerAgent, sync: DjangoSync, auth: DeviceAuth):
        self.db = db
        self.agent = agent
        self.sync = sync
        self.auth = auth

        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        resolved_path, icon = _resolve_icon_path()
        if resolved_path:
            print(f"[TRAY] Using icon: {resolved_path}")
        else:
            print("[TRAY] Using fallback icon (theme/default)")

        self.tray_icon = QSystemTrayIcon(self.app)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Nwata Tracker")
        self.menu = QMenu()
        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.show()

        self.update_menu(pre_auth=not self.auth.is_valid())

    def update_menu(self, pre_auth=False):
        self.menu.clear()

        if pre_auth:
            login_action = QAction("Login", self.menu)
            login_action.triggered.connect(self.handle_login)
            self.menu.addAction(login_action)

            quit_action = QAction("Quit", self.menu)
            quit_action.triggered.connect(self.app.quit)
            self.menu.addAction(quit_action)
        else:
            start_action = QAction("Start Tracking", self.menu)
            start_action.setEnabled(not self.agent.running)
            start_action.triggered.connect(self.start_tracking)
            self.menu.addAction(start_action)

            stop_action = QAction("Stop Tracking", self.menu)
            stop_action.setEnabled(self.agent.running)
            stop_action.triggered.connect(self.stop_tracking)
            self.menu.addAction(stop_action)

            sync_action = QAction("Force Sync", self.menu)
            sync_action.triggered.connect(self.force_sync)
            self.menu.addAction(sync_action)

            logout_action = QAction("Logout", self.menu)
            logout_action.triggered.connect(self.logout)
            self.menu.addAction(logout_action)

            quit_action = QAction("Quit", self.menu)
            quit_action.triggered.connect(self.quit_app)
            self.menu.addAction(quit_action)

    def handle_login(self):
        dialog = LoginDialog(self.auth)
        if dialog.exec_() == QDialog.Accepted and dialog.token_acquired:
            self.update_menu(pre_auth=False)

    def start_tracking(self):
        if not self.auth.is_valid():
            QMessageBox.warning(None, "Auth Error", "Token invalid. Please login again.")
            self.update_menu(pre_auth=True)
            return
        self.agent.start()
        self.update_menu(pre_auth=False)

    def stop_tracking(self):
        self.agent.stop()
        self.update_menu(pre_auth=False)

    def force_sync(self):
        self.sync.flush()

    def logout(self):
        self.agent.stop()
        self.sync.flush()
        self.auth.clear()
        QMessageBox.information(None, "Logged out", "Device token cleared.")
        self.update_menu(pre_auth=True)

    def quit_app(self):
        self.agent.stop()
        self.sync.flush()
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec_())


# -----------------------------
# ENTRY POINT
# -----------------------------
if __name__ == "__main__":
    db = LocalDB(DB_PATH)
    auth = DeviceAuth(DJANGO_API_URL)
    sync = DjangoSync(db, auth)
    agent = TrackerAgent(db, sync)

    tray = TrayApp(db, agent, sync, auth)
    tray.run()
