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
MIN_DURATION_S = 0.001  # Minimum 1ms duration to avoid division by zero
MAX_DURATION_S = 28800  # 8 hours max per activity window
MAX_TYPING_RATE = 1000  # Max typing events per minute (realistic bound)
MAX_SCROLL_RATE = 500  # Max scroll events per minute (realistic bound)

# Context schema validation bounds
CONTEXT_CONSTRAINTS = {
    'typing_count': {'min': 0, 'max': 10000},
    'scroll_count': {'min': 0, 'max': 5000},
    'shortcut_count': {'min': 0, 'max': 1000},
    'total_idle_ms': {'min': 0, 'max': None},
    'max_idle_ms': {'min': 0, 'max': None},
    'window_duration_s': {'min': MIN_DURATION_S, 'max': MAX_DURATION_S},
    'typing_rate_per_min': {'min': 0, 'max': MAX_TYPING_RATE},
    'scroll_rate_per_min': {'min': 0, 'max': MAX_SCROLL_RATE},
}

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
            context_data TEXT,
            synced INTEGER DEFAULT 0
        )
        """
        )
        self.conn.commit()
        
        # Migration: Add context_data column if it doesn't exist
        try:
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA table_info(activity_log)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'context_data' not in columns:
                print("[DB] Migrating schema: adding context_data column")
                self.conn.execute("ALTER TABLE activity_log ADD COLUMN context_data TEXT")
                self.conn.commit()
                print("[DB] Migration complete")
        except Exception as e:
            print(f"[DB] Migration check failed: {e}")

    def insert_log(self, log):
        self.conn.execute(
            """
        INSERT INTO activity_log (window_title, app_name, start_time, end_time, context_data)
        VALUES (?, ?, ?, ?, ?)
        """,
            (
                log["window_title"],
                log["app_name"],
                log["start_time"],
                log["end_time"],
                log.get("context_data"),
            ),
        )
        self.conn.commit()
        print(f"[LOG] {log}")

    def fetch_unsynced(self, limit):
        cur = self.conn.cursor()
        cur.execute(
            """
        SELECT id, window_title, app_name, start_time, end_time, context_data
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
# CONTEXT DATA VALIDATION
# -----------------------------
def validate_context_data(context_data):
    """Validate context data against schema constraints.
    
    Args:
        context_data: Dictionary with context metrics or None
        
    Returns:
        Tuple (is_valid, error_message) where is_valid is bool, error_message is str or None
    """
    if context_data is None:
        # None is acceptable (no tracking occurred)
        return True, None
    
    if not isinstance(context_data, dict):
        return False, "context_data must be a dictionary"
    
    # Check each constraint
    for field, constraint in CONTEXT_CONSTRAINTS.items():
        if field not in context_data:
            # Some fields may be optional
            if field in ['typing_count', 'scroll_count', 'shortcut_count', 'window_duration_s']:
                return False, f"missing required field: {field}"
            continue
        
        value = context_data[field]
        
        # Type check: should be numeric
        if not isinstance(value, (int, float)):
            return False, f"{field} must be numeric, got {type(value).__name__}"
        
        # Min constraint
        min_val = constraint.get('min')
        if min_val is not None and value < min_val:
            return False, f"{field} value {value} below minimum {min_val}"
        
        # Max constraint
        max_val = constraint.get('max')
        if max_val is not None and value > max_val:
            return False, f"{field} value {value} exceeds maximum {max_val}"
    
    return True, None


# -----------------------------
# SYNC ENGINE
# -----------------------------
class DjangoSync:
    def __init__(self, db: LocalDB, auth: DeviceAuth):
        self.db = db
        self.auth = auth
        self.validation_errors_count = 0  # Track validation failures for alerts

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
        skipped = 0

        for r in rows:
            context_data = None
            if r[5]:  # context_data column
                try:
                    context_data = json.loads(r[5])
                except Exception as e:
                    print(f"[SYNC WARN] Invalid JSON in context_data: {e}")
                    context_data = None
            
            # Validate context data before adding to payload
            is_valid, error_msg = validate_context_data(context_data)
            if not is_valid:
                self.validation_errors_count += 1
                print(f"[SYNC VALIDATION FAILED] {error_msg} - Log ID {r[0]} skipped")
                skipped += 1
                continue
            
            ids.append(r[0])
            payload.append(
                {
                    "window_title": r[1],
                    "app_name": r[2],
                    "start_time": r[3],
                    "end_time": r[4],
                    "context": context_data,
                }
            )

        if not payload:
            if skipped > 0:
                print(f"[SYNC] No valid logs to sync ({skipped} skipped due to validation)")
            return

        try:
            res = requests.post(
                f"{self.auth.api_url}/api/activity/",
                json=payload,
                headers=self._headers(),
                timeout=5,
            )
            if 200 <= res.status_code < 300:
                self.db.mark_synced(ids)
                print(f"[SYNC] Uploaded {len(ids)} logs with context ({skipped} validation skipped)")
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
# CONTEXT MONITORING
# Context signals aggregated per window/log
# Flushed when window changes
# 
# NOTE: Context stats (typing/scroll) require keyboard/mouse listener integration.
# To enable, install pynput and add:
#   from pynput import keyboard, mouse
#   keyboard.Listener(on_press=lambda k: agent.record_typing()).start()
#   mouse.Listener(on_scroll=lambda x,y,dx,dy: agent.record_scroll()).start()
# -----------------------------
class ContextSignals:
    """Aggregates context signals for a single window log."""
    def __init__(self):
        self.typing_count = 0        # Number of typing events
        self.scroll_count = 0        # Number of scroll events
        self.shortcut_count = 0      # Number of shortcuts in this window
        self.total_idle_ms = 0       # Cumulative idle time (ms)
        self.max_idle_ms = 0         # Longest single idle pause (ms)
        self.last_activity_time = None  # Timestamp of last typing/scroll
    
    def record_typing(self, now):
        """Record a typing event."""
        if self.last_activity_time:
            idle = (now - self.last_activity_time).total_seconds() * 1000
            self.total_idle_ms += idle
            self.max_idle_ms = max(self.max_idle_ms, idle)
        self.typing_count += 1
        self.last_activity_time = now
    
    def record_scroll(self, now):
        """Record a scroll event."""
        if self.last_activity_time:
            idle = (now - self.last_activity_time).total_seconds() * 1000
            self.total_idle_ms += idle
            self.max_idle_ms = max(self.max_idle_ms, idle)
        self.scroll_count += 1
        self.last_activity_time = now
    
    def record_shortcut(self):
        """Record a shortcut in current window."""
        self.shortcut_count += 1
    
    def finalize(self, window_duration_s):
        """Finalize context data with validation and ML-ready features.
        
        Ensures all values are non-negative, within realistic bounds,
        and computes derived metrics for ML models.
        """
        # Safety: ensure duration is within reasonable bounds
        safe_duration_s = max(MIN_DURATION_S, min(window_duration_s, MAX_DURATION_S))
        
        # Context with bounds checking (ensure non-negative)
        context = {
            "typing_count": max(0, self.typing_count),
            "scroll_count": max(0, self.scroll_count),
            "shortcut_count": max(0, self.shortcut_count),
            "total_idle_ms": max(0, int(self.total_idle_ms)),
            "max_idle_ms": max(0, int(self.max_idle_ms)),
            "window_duration_s": safe_duration_s,
        }
        
        # Derived: typing and scroll rates per minute (capped at realistic maximums)
        duration_min = max(0.001, safe_duration_s / 60)  # Avoid division by zero
        context["typing_rate_per_min"] = round(
            min(self.typing_count / duration_min, MAX_TYPING_RATE), 2
        )
        context["scroll_rate_per_min"] = round(
            min(self.scroll_count / duration_min, MAX_SCROLL_RATE), 2
        )
        
        # ML-ready features for backend normalization
        context["activity_events_total"] = (
            context["typing_count"] 
            + context["scroll_count"] 
            + context["shortcut_count"]
        )
        context["idle_ratio"] = min(
            context["total_idle_ms"] / max(safe_duration_s * 1000, 1), 1.0
        )
        context["peak_idle_ratio"] = min(
            context["max_idle_ms"] / max(safe_duration_s * 1000, 1), 1.0
        )
        
        return context


class ContextMonitor:
    """Tracks keyboard, scroll, and other signal events for aggregation per window."""
    def __init__(self):
        self.current_signals = ContextSignals()
        self.lock = threading.Lock()
    
    def record_typing(self):
        """Called when a keyboard/typing event is detected."""
        with self.lock:
            self.current_signals.record_typing(datetime.now(timezone.utc))
    
    def record_scroll(self):
        """Called when a scroll event is detected."""
        with self.lock:
            self.current_signals.record_scroll(datetime.now(timezone.utc))
    
    def record_shortcut(self):
        """Called when a keyboard shortcut is detected in current window."""
        with self.lock:
            self.current_signals.record_shortcut()
    
    def finalize_and_reset(self, window_duration_s):
        """Finalize current window's context, reset for next window."""
        with self.lock:
            context = self.current_signals.finalize(window_duration_s)
            self.current_signals = ContextSignals()
        return context


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
        self.context_monitor = ContextMonitor()

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
            now = datetime.fromisoformat(now_iso.replace('Z', '+00:00')) if 'Z' in now_iso else datetime.fromisoformat(now_iso)
            last = datetime.fromisoformat(self.last_time.replace('Z', '+00:00')) if 'Z' in self.last_time else datetime.fromisoformat(self.last_time)
            duration_s = (now - last).total_seconds()
            context_data = self.context_monitor.finalize_and_reset(duration_s)
            
            self.db.insert_log(
                {
                    "window_title": self.last_window,
                    "app_name": self.last_window.split(" - ")[0],
                    "start_time": self.last_time,
                    "end_time": now_iso,
                    "context_data": json.dumps(context_data),
                }
            )
        self.running = False
        self.sync.signal("stop")

    def _loop(self):
        """Main tracking loop: monitors active window and flushes on change or timeout."""
        last_flush = time.time()
        while self.running:
            now = datetime.now(timezone.utc)
            window = get_active_window()
            
            # Check if window changed or timeout reached
            if window != self.last_window or (time.time() - last_flush > ACTIVE_FLUSH_INTERVAL):
                # Flush previous window
                if self.last_window and self.last_time:
                    now_iso = now.isoformat()
                    last_iso = self.last_time
                    
                    try:
                        now_dt = datetime.fromisoformat(now_iso.replace('Z', '+00:00')) if 'Z' in now_iso else datetime.fromisoformat(now_iso)
                        last_dt = datetime.fromisoformat(last_iso.replace('Z', '+00:00')) if 'Z' in last_iso else datetime.fromisoformat(last_iso)
                        duration_s = (now_dt - last_dt).total_seconds()
                        
                        # Ensure duration is safe (between MIN and MAX)
                        duration_s = max(MIN_DURATION_S, min(duration_s, MAX_DURATION_S))
                        
                        context_data = self.context_monitor.finalize_and_reset(duration_s)
                        
                        self.db.insert_log({
                            "window_title": self.last_window,
                            "app_name": self.last_window.split(" - ")[0] if " - " in self.last_window else self.last_window,
                            "start_time": last_iso,
                            "end_time": now_iso,
                            "context_data": json.dumps(context_data),
                        })
                    except Exception as e:
                        print(f"[AGENT ERROR] Failed to flush window {self.last_window}: {e}")
                
                self.last_window = window
                self.last_time = now.isoformat()
                last_flush = time.time()
            
            time.sleep(TRACK_INTERVAL)


    def _sync_loop(self):
        """Sync loop: periodically flush logs to backend with error handling."""
        sync_error_count = 0
        while self.running:
            try:
                self.sync.flush()
                sync_error_count = 0  # Reset on successful sync
            except Exception as e:
                sync_error_count += 1
                print(f"[SYNC WARN] Sync failed (attempt {sync_error_count}): {e}")
                
                # Alert user if too many validation errors
                if self.sync.validation_errors_count > 5:
                    print(f"[SYNC ALERT] {self.sync.validation_errors_count} logs failed validation. Check data quality.")
                
                if sync_error_count > 10:
                    print("[SYNC CRITICAL] Too many sync failures. Check connection or credentials.")
            
            time.sleep(SYNC_INTERVAL)

    
    # Public signal methods (for integration with keyboard/mouse listeners)
    def record_typing(self):
        """Called by keyboard listener when typing is detected."""
        if self.running:
            self.context_monitor.record_typing()
    
    def record_scroll(self):
        """Called by mouse listener when scrolling is detected."""
        if self.running:
            self.context_monitor.record_scroll()
    
    def record_shortcut(self):
        """Called by keyboard listener when a shortcut is detected in current window."""
        if self.running:
            self.context_monitor.record_shortcut()


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
