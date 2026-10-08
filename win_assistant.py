# ==============================================================================
# WINDOWS SETUP INSTRUCTIONS:
# 1. Install Python 3.10+ (Ensure "Add Python to PATH" is checked during installation)
# 2. Install Tesseract OCR for Windows (Optional for OCR mode):
#    Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
#    Default install path: C:\Program Files\Tesseract-OCR\tesseract.exe
# 3. Open Command Prompt (CMD) or PowerShell and run:
#    pip install pynput pyperclip requests Pillow pytesseract
# 4. Launch the assistant:
#    python win_assistant.py
# ==============================================================================

import os
import sys

# Immediately hide terminal/console window on Windows so it runs completely silently
if sys.platform == "win32":
    try:
        import ctypes
        _k32 = getattr(ctypes, "windll", None)
        if _k32:
            _hwnd_console = _k32.kernel32.GetConsoleWindow()
            if _hwnd_console:
                _k32.user32.ShowWindow(_hwnd_console, 0)  # 0 = SW_HIDE
    except Exception:
        pass

# Ensure print() calls never crash when built with --noconsole / pythonw
class _SilentWriter:
    def write(self, s): pass
    def flush(self): pass

if sys.stdout is None:
    sys.stdout = _SilentWriter()
else:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr is None:
    sys.stderr = _SilentWriter()
else:
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import time
import json
from datetime import date
import base64
import subprocess
import threading
import queue
import tkinter as tk
import pyperclip
try:
    import pytesseract
except ImportError:
    pytesseract = None
from pynput import keyboard, mouse
from PIL import ImageGrab
import requests
import random
import platform
import ctypes
import typing

# Type-safe dynamic platform access to prevent IDE lint errors on macOS/Linux
windll: typing.Any = getattr(ctypes, "windll", None)

try:
    import winsound as _winsound
    winsound: typing.Any = _winsound
except ImportError:
    winsound = None

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Base directory for output files (works both as script and as compiled exe)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CODE_FILE = os.path.join(BASE_DIR, "code.txt")
LANG_FILE = os.path.join(BASE_DIR, "lang.txt")

# Set Windows DPI Awareness so screenshots and coordinates match physical pixels
if windll:
    try:
        windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor DPI Aware
    except Exception:
        try:
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Set 1ms timer resolution on Windows for buttery-smooth typing without lag
if sys.platform == "win32" and windll:
    try:
        windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

# Auto-detect Tesseract OCR install path if not in System PATH
if pytesseract is not None:
    tess_candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for tp in tess_candidates:
        if os.path.exists(tp):
            pytesseract.pytesseract.tesseract_cmd = tp
            break

# Screen Bounds
try:
    if windll:
        SCREEN_WIDTH = windll.user32.GetSystemMetrics(0)
        SCREEN_HEIGHT = windll.user32.GetSystemMetrics(1)
    else:
        SCREEN_WIDTH, SCREEN_HEIGHT = 1920, 1080
except Exception:
    SCREEN_WIDTH, SCREEN_HEIGHT = 1920, 1080

api_session = requests.Session()
from io import BytesIO
mouse_controller = mouse.Controller()

# ─── API KEYS ─────────────────────────────────────────────────────────────────
_DEFAULT_KEY = base64.b64decode("QVEuQWI4Uk42S1Vrd3k0VFlYem9QaVU5cFBTTDZlSnlmSTF3LWM5TVRqbmJrTmZLTVlKWEE=").decode()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", _DEFAULT_KEY)

# ─── PROVIDER ─────────────────────────────────────────────────────────────────
PROVIDER = {
    "name":    "Gemini 3.8 Flash (Vertex AI)",
    "type":    "gemini",
    "key":     GEMINI_API_KEY,
    "url":     "https://aiplatform.googleapis.com/v1beta1/projects/934443841297/locations/global/publishers/google/models/gemini-3.8-flash:generateContent",
    "timeout": 60,
}

# ─── OPTIONS ──────────────────────────────────────────────────────────────────
TYPING_SPEED_FACTOR = 1.0
TRIGGER_MARGIN      = 150
INPUT_MODE          = 0       # 0 = Screenshot | 1 = OCR (Tesseract) | 2 = Accessibility
INPUT_MODE_NAMES    = ["Screenshot", "OCR (Tesseract)", "Accessibility"]
INDENT_MODE         = 0       # 0 = Smart-Indent (LeetCode/Web IDEs) | 1 = Raw-Indent (Plain Editors)
INDENT_MODE_NAMES   = ["Smart-Indent (LeetCode/Web IDEs)", "Raw-Indent (Plain Editors)"]
ONE_INCH_PX         = 96      # 1 inch at 96 DPI — mouse answer offset from corners

def toggle_indent_mode():
    global INDENT_MODE
    INDENT_MODE = (INDENT_MODE + 1) % len(INDENT_MODE_NAMES)
    play_sound("Hero")
    print(f"\n>> Indent Mode switched to: {INDENT_MODE_NAMES[INDENT_MODE]}")
    print_status()

# ─── STATE ────────────────────────────────────────────────────────────────────
is_locked              = False
ghost_typing_active    = False
ghost_typing_thread    = None
ghost_typing_reset_flag = False
ghost_typing_offset    = 0
ghost_typing_content   = ""
ghost_typing_completed_notified = False
cached_interactive_text = ""
cached_interactive_mtime = 0
MAGIC_EXTRA            = 0xC0DE
completion_disarm_token = 0

# Typing Modes:
# Mode 1 = Auto Ghost Typing (automatic timer cadence)
# Mode 2 = Interactive Keypress / Hacker Typer (press random keys to type code character-by-character)
TYPING_MODE            = 2  # Default to Mode 2 (Interactive Hacker Typer)
TYPING_MODE_NAMES      = {
    1: "Mode 1: Auto Ghost Typing",
    2: "Mode 2: Interactive Keypress (Hacker Typer)"
}
last_mode_toggle_time  = 0

state_lock       = threading.Lock()
session_active  = True
session_history = []

def toggle_typing_mode():
    """Toggles between Mode 1 (Auto Ghost Typing) and Mode 2 (Interactive Keypress / Hacker Typer).
    Moving cursor to left corner for Mode 1 and top-right corner for Mode 2 as a stealth indicator."""
    global TYPING_MODE, ghost_typing_active, last_mode_toggle_time
    if is_locked:
        return

    now = time.time()
    if now - last_mode_toggle_time < 0.35:
        return
    last_mode_toggle_time = now

    if TYPING_MODE == 1:
        TYPING_MODE = 2
        # Mode 2: Move cursor to top-right corner
        tx, ty = SCREEN_WIDTH - 5, 5
        mouse_controller.position = (int(tx), int(ty))
        if windll:
            try:
                windll.user32.SetCursorPos(int(tx), int(ty))
            except Exception:
                pass
        with state_lock:
            ghost_typing_active = True
        play_sound("Glass")
        print("\n" + "="*58)
        print("⌨️  [TYPING MODE 2: INTERACTIVE HACKER TYPER ACTIVATED]")
        print("   👉 Type ANY keys on your keyboard (e.g. asdfghjk)")
        print("   Each keystroke types the next character of your code!")
        print("   Cursor moved to TOP-RIGHT corner as stealth indicator.")
        print("   (Right Shift + P to pause/resume | Esc to emergency stop)")
        print("="*58)
    else:
        TYPING_MODE = 1
        # Mode 1: Move cursor to left corner
        tx, ty = 5, 5
        mouse_controller.position = (int(tx), int(ty))
        if windll:
            try:
                windll.user32.SetCursorPos(int(tx), int(ty))
            except Exception:
                pass
        with state_lock:
            ghost_typing_active = False
        play_sound("Pop")
        print("\n" + "="*58)
        print("⚡ [TYPING MODE 1: AUTO GHOST TYPING ACTIVATED]")
        print("   👉 Press Right Shift + P to start/pause automatic typing.")
        print("   Cursor moved to TOP-LEFT corner as stealth indicator.")
        print("="*58)

    print_status()

def toggle_lock():
    global is_locked, ghost_typing_active
    with state_lock:
        is_locked = not is_locked
        if is_locked:
            ghost_typing_active = False

    if is_locked:
        print("\n" + "="*45)
        print("🔒 [ASSISTANT LOCKED] All triggers, hotkeys & typing are FROZEN.")
        print("="*45)
        play_sound("Basso")
    else:
        print("\n" + "="*45)
        print("🟢 [ASSISTANT UNLOCKED] Triggers and typing are ACTIVE.")
        print("="*45)
        play_sound("Glass")
    update_hud("status", {"locked": is_locked, "mode": INPUT_MODE_NAMES[INPUT_MODE]})
    print_status()


rpd_exhausted_date = ""

def is_provider_exhausted():
    global rpd_exhausted_date
    if rpd_exhausted_date == str(date.today()):
        return True
    return False

def mark_provider_exhausted():
    global rpd_exhausted_date
    rpd_exhausted_date = str(date.today())
    print(f"\n⛔ [{PROVIDER['name']}] Daily limit (RPD) hit — disabled until tomorrow.")

def parse_429_error(response):
    try:
        body = response.json()
        error_text = json.dumps(body).lower()
        if "perday" in error_text or "per_day" in error_text or "daily" in error_text:
            return "RPD"
        elif "perminute" in error_text or "per_minute" in error_text:
            return "RPM"
    except Exception:
        pass
    return "UNKNOWN"


latest_mcq_req_id      = 0
latest_code_req_id     = 0
latest_essay_req_id    = 0
latest_guided_req_id   = 0
latest_critique_req_id = 0
req_lock = threading.Lock()

is_self_typing         = False
is_ai_request_running  = False
ai_request_lock        = threading.Lock()

def is_interactive_typing_done():
    global ghost_typing_offset, cached_interactive_text
    try:
        if cached_interactive_text:
            return ghost_typing_offset >= len(cached_interactive_text)
        if not os.path.exists(CODE_FILE):
            return True
        with open(CODE_FILE, "r", encoding="utf-8") as f:
            c = f.read()
        return ghost_typing_offset >= len(c)
    except Exception:
        return False

def can_start_ai_request(action_name="Request"):
    global is_ai_request_running, ghost_typing_active, is_self_typing, is_locked
    if is_locked:
        print(f"\n[{action_name} Blocked] Assistant is locked.")
        play_sound("Basso")
        return False
    if is_self_typing:
        print(f"\n[{action_name} Blocked] Cannot trigger request while assistant is self-typing.")
        play_sound("Basso")
        return False
    with ai_request_lock:
        if is_ai_request_running:
            print(f"\n[{action_name} Blocked] Another AI request is already in progress.")
            play_sound("Basso")
            return False
        is_ai_request_running = True
        # Immediately pause previous ghost typing so the new request takes over cleanly
        with state_lock:
            ghost_typing_active = False
        return True

def finish_ai_request():
    global is_ai_request_running
    with ai_request_lock:
        is_ai_request_running = False

mcq_count      = 0
code_count     = 0
essay_count    = 0
guided_count   = 0
critique_count = 0


# ─── SOUND (WINDOWS NATIVE) ───────────────────────────────────────────────────

def play_sound(sound_name):
    """Plays subtle, native system sound feedback asynchronously (zero conflicts, non-blocking)."""
    if winsound is not None:
        sound_map = {
            "Pop":       "SystemDefault",
            "Hero":      "SystemAsterisk",
            "Ping":      "SystemAsterisk",
            "Purr":      "SystemDefault",
            "Basso":     "SystemHand",
            "Glass":     "SystemExclamation",
            "Tink":      "SystemExit",
            "Submarine": "SystemQuestion"
        }
        try:
            winsound.PlaySound(sound_map.get(sound_name, "SystemDefault"),
                               winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            try:
                winsound.MessageBeep(winsound.MB_OK)
            except Exception:
                pass
    elif platform.system() == "Darwin":
        try:
            subprocess.Popen(["afplay", f"/System/Library/Sounds/{sound_name}.aiff"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass



# ─── STATUS DISPLAY ───────────────────────────────────────────────────────────

def print_status():
    status_str  = "LOCKED 🔒" if is_locked else "ACTIVE 🟢"
    provider    = PROVIDER['name']
    mode        = INPUT_MODE_NAMES[INPUT_MODE]
    indent      = INDENT_MODE_NAMES[INDENT_MODE]
    session     = "ON" if session_active else "OFF"
    typing_mode = TYPING_MODE_NAMES[TYPING_MODE]
    print(f"\n┌────────────────────────────────────────────────────────┐")
    print(f"│  Status   : {status_str:<43}│")
    print(f"│  Provider : {provider:<43}│")
    print(f"│  Mode     : {mode:<43}│")
    print(f"│  Typing   : {typing_mode:<43}│")
    print(f"│  Indent   : {indent:<43}│")
    print(f"│  Session  : {session:<43}│")
    print(f"│  Solved   : Code/Debug={code_count:<3} Guided={guided_count:<3} MCQ={mcq_count:<3} Essay={essay_count:<4}│")
    print(f"└────────────────────────────────────────────────────────┘")


# ─── FLOATING GLASS HUD (STEALTH OVERLAY) ──────────────────────────────────────

# Master toggle: set to False to completely disable the HUD UI feature without removing code
ENABLE_HUD = False

hud_queue = queue.Queue()

def update_hud(event_type, data=None):
    if not ENABLE_HUD:
        return
    try:
        hud_queue.put((event_type, data))
    except Exception:
        pass


HUD_THEMES = {
    "dark": {
        "name": "Dark Glass",
        "bg": "#090a0d",
        "border": "#2d3039",
        "fg_active": "#10b981",
        "fg_locked": "#ef4444",
        "fg_mcq": "#38bdf8",
        "fg_text": "#ffffff",
        "fg_sub": "#cbd5e1",
        "fg_hint": "#94a3b8",
        "prog_bg": "#1f222a",
        "prog_fg": "#38bdf8",
        "code_bg": "#0b0c0f",
        "code_fg": "#f1f5f9",
        "transparent_key": None,
        "default_alpha": 0.18,
    },
}

# Windows DWM Blur Behind & Acrylic Structures
class DWM_BLURBEHIND(ctypes.Structure):
    _fields_ = [
        ("dwFlags", ctypes.c_ulong),
        ("fEnable", ctypes.c_bool),
        ("hRgnBlur", ctypes.c_void_p),
        ("fTransitionOnMaximized", ctypes.c_bool),
    ]

class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_int),
        ("AnimationId", ctypes.c_int),
    ]

class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def apply_dwm_glass(hwnd, alpha=0.18):
    """Applies native Windows 10/11 DWM Blur-Behind and Acrylic compositing to HWND."""
    if sys.platform != "win32" or not windll:
        return

    try:
        # Method 1: DwmEnableBlurBehindWindow
        bb = DWM_BLURBEHIND()
        bb.dwFlags = 1  # DWM_BB_ENABLE
        bb.fEnable = True
        bb.hRgnBlur = None
        bb.fTransitionOnMaximized = False
        dwmapi = getattr(windll, 'dwmapi', None)
        if dwmapi and hasattr(dwmapi, 'DwmEnableBlurBehindWindow'):
            dwmapi.DwmEnableBlurBehindWindow(hwnd, ctypes.byref(bb))
    except Exception:
        pass

    try:
        # Method 2: Acrylic Blur Policy (SetWindowCompositionAttribute)
        accent = ACCENT_POLICY()
        accent.AccentState = 4  # ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.AccentFlags = 2
        int_a = int(alpha * 255) & 0xFF
        accent.GradientColor = (int_a << 24) | 0x000F1012
        accent.AnimationId = 0

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = 19  # WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)

        user32 = getattr(windll, 'user32', None)
        if user32 and hasattr(user32, 'SetWindowCompositionAttribute'):
            user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
    except Exception:
        pass


class GlassHUD:
    """
    Floating, translucent glassmorphic HUD overlay (Dark Glass Only).
    Merges seamlessly with background (True DWM Acrylic blur).
    Excluded from screen capture (WDA_EXCLUDEFROMCAPTURE = 0x00000011).
    Never steals foreground focus on click (WS_EX_NOACTIVATE — no tab switch).
    Minimizable into stealth nano-pill ([—] / Shift+N).
    Dynamically resizable via corner grip (⋱) or hotkeys (Shift + - / = / O).
    """
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("System Monitor")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(takefocus=0)

        # Display is INACTIVE / HIDDEN initially — opens only when user presses Shift + V
        self.is_visible = False
        self.root.withdraw()

        # Perfect dimensions to fit all elements cleanly
        self.compact_w, self.compact_h = 370, 72
        self.expanded_w, self.expanded_h = 420, 280
        self.mini_w, self.mini_h = 165, 26

        self.is_minimized = False
        self.is_unveiled = False
        self.active_action = "ready"
        self.code_result = ""
        self.mcq_result = ""
        self.target_fg_hwnd = None

        # Dark Glass is the exclusive theme
        self.current_theme = "dark"
        t = HUD_THEMES["dark"]
        self.alpha = t["default_alpha"]
        try:
            self.root.attributes("-alpha", self.alpha)
        except Exception:
            pass

        self.bg_color = t["bg"]
        self.border_color = t["border"]
        self.root.configure(bg=self.border_color)

        pos_x = max(10, SCREEN_WIDTH - self.compact_w - 20)
        pos_y = 20
        self.root.geometry(f"{self.compact_w}x{self.compact_h}+{pos_x}+{pos_y}")

        # Default to Draggable / Interactive mode so buttons and dragging work when opened
        self.click_through = False
        self.reassert_counter = 0

        self.drag_x = 0
        self.drag_y = 0
        self.resize_start_x = 0
        self.resize_start_y = 0
        self.resize_orig_w = self.compact_w
        self.resize_orig_h = self.compact_h

        self.main_frame = tk.Frame(self.root, bg=self.bg_color, bd=0, takefocus=0)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Row 1: Header (Status | [—] Minimize | Action Badge | [Code ▾] | ClickThru | Size/Opacity)
        self.header = tk.Frame(self.main_frame, bg=self.bg_color, cursor="fleur", height=22, takefocus=0)
        self.header.pack(fill=tk.X, padx=6, pady=(3, 1))
        self.header.pack_propagate(False)

        self.status_lbl = tk.Label(
            self.header, text="● ACTIVE", font=("Segoe UI", 8, "bold"),
            bg=self.bg_color, fg=t["fg_active"], takefocus=0
        )
        self.status_lbl.pack(side=tk.LEFT)

        # Minimize button: [—] collapses to 165x26 stealth nano-pill
        self.min_btn = tk.Label(
            self.header, text="[—]", font=("Segoe UI", 8, "bold"),
            bg=self.bg_color, fg=t["fg_hint"], cursor="hand2", takefocus=0
        )
        self.min_btn.pack(side=tk.LEFT, padx=(3, 2))
        self.min_btn.bind("<Button-1>", lambda e: self._toggle_minimize())

        # Dynamic action badge: updates to show only current mode (MCQ vs Code vs Guide)
        self.action_lbl = tk.Label(
            self.header, text="Ready", font=("Segoe UI", 8, "bold"),
            bg=self.bg_color, fg=t["fg_hint"], takefocus=0
        )
        self.action_lbl.pack(side=tk.LEFT, padx=3)

        # Clickable button to unveil full code (shown only when code exists)
        self.unveil_btn = tk.Label(
            self.header, text="[Code ▾]", font=("Segoe UI", 8, "bold"),
            bg=self.bg_color, fg=t["fg_mcq"], cursor="hand2", takefocus=0
        )
        self.unveil_btn.bind("<Button-1>", lambda e: self._toggle_code_drawer())

        self.mode_lbl = tk.Label(
            self.header, text="ClickThru", font=("Segoe UI", 8),
            bg=self.bg_color, fg=t["fg_hint"], takefocus=0
        )
        self.mode_lbl.pack(side=tk.RIGHT)

        self.theme_lbl = tk.Label(
            self.header, text=f"{self.compact_w}px | {int(self.alpha*100)}%", font=("Segoe UI", 8),
            bg=self.bg_color, fg=t["fg_hint"], takefocus=0
        )
        self.theme_lbl.pack(side=tk.RIGHT, padx=4)

        # Row 2: Progress line (2px thin modern accent bar)
        self.prog_canvas = tk.Canvas(self.main_frame, bg=t["prog_bg"], height=2, bd=0, highlightthickness=0, takefocus=0)
        self.prog_canvas.pack(fill=tk.X, padx=6, pady=(1, 1))
        self.prog_bar = self.prog_canvas.create_rectangle(0, 0, 0, 2, fill=t["prog_fg"], width=0)

        # Row 3: Typing status & preview line
        self.info_row = tk.Frame(self.main_frame, bg=self.bg_color, height=20, takefocus=0)
        self.info_row.pack(fill=tk.X, padx=6, pady=(1, 2))
        self.info_row.pack_propagate(False)

        self.typing_lbl = tk.Label(
            self.info_row, text="Typing: Idle (Shift+P)", font=("Segoe UI", 8),
            bg=self.bg_color, fg=t["fg_sub"], takefocus=0
        )
        self.typing_lbl.pack(side=tk.LEFT)

        # Bottom-right resize grip handle
        self.resize_grip = tk.Label(
            self.info_row, text="⋱", font=("Segoe UI", 9, "bold"),
            bg=self.bg_color, fg=t["fg_hint"], cursor="size_nw_se", takefocus=0
        )
        self.resize_grip.pack(side=tk.RIGHT, padx=(2, 0))
        self.resize_grip.bind("<Button-1>", self._start_resize)
        self.resize_grip.bind("<B1-Motion>", self._do_resize)

        self.preview_lbl = tk.Label(
            self.info_row, text="Ready. Shift+C / Shift+M / Shift+G", font=("Segoe UI", 8),
            bg=self.bg_color, fg=t["fg_text"], takefocus=0
        )
        self.preview_lbl.pack(side=tk.RIGHT, padx=(0, 2))

        # Drawer Frame (Unveiled Full Code Area)
        self.drawer_frame = tk.Frame(self.main_frame, bg=self.bg_color, takefocus=0)

        self.drawer_bar = tk.Frame(self.drawer_frame, bg=self.bg_color, height=18, takefocus=0)
        self.drawer_bar.pack(fill=tk.X, pady=(1, 2))

        self.drawer_title = tk.Label(
            self.drawer_bar, text="── Full Code Solution (Shift+K to toggle) ──",
            font=("Segoe UI", 8), bg=self.bg_color, fg=t["fg_hint"], takefocus=0
        )
        self.drawer_title.pack(side=tk.LEFT)

        self.drawer_close = tk.Label(
            self.drawer_bar, text="[Hide ▴]", font=("Segoe UI", 8, "bold"),
            bg=self.bg_color, fg=t["fg_mcq"], cursor="hand2", takefocus=0
        )
        self.drawer_close.pack(side=tk.RIGHT)
        self.drawer_close.bind("<Button-1>", lambda e: self._toggle_code_drawer())

        self.code_text_container = tk.Frame(self.drawer_frame, bg=self.border_color, bd=1, takefocus=0)
        self.code_text_container.pack(fill=tk.BOTH, expand=True)

        self.code_scrollbar = tk.Scrollbar(self.code_text_container, takefocus=0)
        self.code_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.code_text = tk.Text(
            self.code_text_container, wrap=tk.WORD,
            bg=t["code_bg"], fg=t["code_fg"],
            font=("Consolas", 8), bd=0, highlightthickness=0,
            yscrollcommand=self.code_scrollbar.set, takefocus=0
        )
        self.code_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.code_scrollbar.config(command=self.code_text.yview)

        # Bind dragging & focus-safety to widgets
        for w in (self.root, self.main_frame, self.header, self.status_lbl,
                  self.mode_lbl, self.theme_lbl, self.prog_canvas, self.info_row,
                  self.typing_lbl, self.preview_lbl, self.drawer_bar, self.drawer_title):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)
            w.bind("<ButtonRelease-1>", self._on_mouse_release)

        # Apply initial Win32 stealth styles
        self._apply_stealth_styles(click_through=self.click_through)

        self.root.after(80, self._process_queue)

    def _apply_stealth_styles(self, click_through=True):
        self.root.update_idletasks()
        if not windll:
            return
        try:
            hwnd = windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            self.hwnd = hwnd

            GetWindowLong = getattr(windll.user32, 'GetWindowLongPtrW', windll.user32.GetWindowLongW)
            SetWindowLong = getattr(windll.user32, 'SetWindowLongPtrW', windll.user32.SetWindowLongW)

            GWL_EXSTYLE = -20
            WS_EX_TOPMOST = 0x00000008
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_LAYERED = 0x00080000
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_NOREDIRECTIONBITMAP = 0x00200000

            # Strip WS_EX_APPWINDOW (forces off taskbar) and add stealth flags across window handles
            for h in (hwnd, self.root.winfo_id()):
                if h:
                    try:
                        style = GetWindowLong(h, GWL_EXSTYLE)
                        style &= ~WS_EX_APPWINDOW
                        base_stealth = (WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED | WS_EX_NOREDIRECTIONBITMAP)
                        style |= base_stealth
                        if click_through:
                            style |= WS_EX_TRANSPARENT
                        else:
                            style &= ~WS_EX_TRANSPARENT
                        SetWindowLong(h, GWL_EXSTYLE, style)
                    except Exception:
                        pass

            # Re-pin topmost with SWP_FRAMECHANGED | SWP_NOACTIVATE (guarantees NO focus switch)
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020
            SWP_SHOWWINDOW = 0x0040
            if getattr(self, 'is_visible', False):
                windll.user32.SetWindowPos(
                    hwnd, -1, 0, 0, 0, 0,
                    SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW
                )

            # Remove from screen recordings & screen shares
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)

            # Apply DWM blur behind / acrylic
            apply_dwm_glass(hwnd, alpha=self.alpha)
        except Exception:
            pass

    def _record_fg_window(self):
        """Preserves the browser/editor foreground window so clicking HUD never causes focus loss."""
        if sys.platform == "win32" and windll:
            try:
                fg = windll.user32.GetForegroundWindow()
                if fg and fg != getattr(self, 'hwnd', None):
                    self.target_fg_hwnd = fg
            except Exception:
                pass

    def _start_drag(self, event):
        self._record_fg_window()
        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()
        return "break"

    def _do_drag(self, event):
        new_x = event.x_root - self.drag_x
        new_y = event.y_root - self.drag_y
        self.root.geometry(f"+{new_x}+{new_y}")
        return "break"

    def _on_mouse_release(self, event):
        if sys.platform == "win32" and windll and getattr(self, 'target_fg_hwnd', None):
            try:
                windll.user32.SetForegroundWindow(self.target_fg_hwnd)
            except Exception:
                pass
        return "break"

    def _start_resize(self, event):
        self._record_fg_window()
        self.resize_start_x = event.x_root
        self.resize_start_y = event.y_root
        self.resize_orig_w = self.root.winfo_width()
        self.resize_orig_h = self.root.winfo_height()
        return "break"

    def _do_resize(self, event):
        dx = event.x_root - self.resize_start_x
        dy = event.y_root - self.resize_start_y
        new_w = max(240, self.resize_orig_w + dx)
        new_h = max(50, self.resize_orig_h + dy)
        if self.is_unveiled:
            self.expanded_w, self.expanded_h = new_w, new_h
        else:
            self.compact_w, self.compact_h = new_w, new_h
        self.root.geometry(f"{new_w}x{new_h}")
        self._update_badges()
        if hasattr(self, 'hwnd'):
            self._apply_stealth_styles(click_through=self.click_through)
        return "break"

    def _toggle_visibility(self):
        """Opens or hides the Floating Glass HUD on Shift + V."""
        self._record_fg_window()
        if self.is_visible:
            self.is_visible = False
            self.root.withdraw()
            play_sound("Pop")
            print("\n[HUD] 🪟 Display Hidden. (Press Right Shift + V to open)")
        else:
            self.is_visible = True
            self.root.deiconify()
            self._apply_stealth_styles(click_through=self.click_through)
            self._update_badges()
            if sys.platform == "win32" and windll and getattr(self, 'target_fg_hwnd', None):
                try:
                    windll.user32.SetForegroundWindow(self.target_fg_hwnd)
                except Exception:
                    pass
            play_sound("Hero")
            print("\n[HUD] 🪟 Display Opened & Active. (All UI hotkeys & buttons enabled)")

    def _toggle_minimize(self):
        """Toggles between full HUD controls and ultra-compact stealth nano-pill (165x26)."""
        self._record_fg_window()
        self.is_minimized = not self.is_minimized
        if self.is_minimized:
            self.min_btn.config(text="[+]")
            self.prog_canvas.pack_forget()
            self.info_row.pack_forget()
            if self.is_unveiled:
                self.drawer_frame.pack_forget()
            self.mode_lbl.pack_forget()
            self.theme_lbl.pack_forget()
            self.action_lbl.pack_forget()
            self.unveil_btn.pack_forget()
            self.root.geometry(f"{self.mini_w}x{self.mini_h}+{self.root.winfo_x()}+{self.root.winfo_y()}")
            play_sound("Pop")
        else:
            self.min_btn.config(text="[—]")
            self.action_lbl.pack(side=tk.LEFT, padx=3)
            if self.code_result:
                self.unveil_btn.pack(side=tk.LEFT, padx=2)
            self.mode_lbl.pack(side=tk.RIGHT)
            self.theme_lbl.pack(side=tk.RIGHT, padx=4)
            self.prog_canvas.pack(fill=tk.X, padx=6, pady=(1, 1))
            self.info_row.pack(fill=tk.X, padx=6, pady=(1, 2))
            if self.is_unveiled:
                self.drawer_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 4))
                self.root.geometry(f"{self.expanded_w}x{self.expanded_h}+{self.root.winfo_x()}+{self.root.winfo_y()}")
            else:
                self.root.geometry(f"{self.compact_w}x{self.compact_h}+{self.root.winfo_x()}+{self.root.winfo_y()}")
            play_sound("Pop")
        if hasattr(self, 'hwnd'):
            self._apply_stealth_styles(click_through=self.click_through)
        return "break"

    def _close_code_drawer(self):
        """Cleanly collapses code drawer back into compact mode."""
        if self.is_unveiled:
            self.is_unveiled = False
            self.unveil_btn.config(text="[Code ▾]")
            self.drawer_frame.pack_forget()
            if not self.is_minimized:
                self.root.geometry(f"{self.compact_w}x{self.compact_h}+{self.root.winfo_x()}+{self.root.winfo_y()}")
            if hasattr(self, 'hwnd'):
                self._apply_stealth_styles(click_through=self.click_through)

    def _toggle_code_drawer(self):
        self._record_fg_window()
        if self.is_minimized:
            self._toggle_minimize()
        self.is_unveiled = not self.is_unveiled
        if self.is_unveiled:
            self.unveil_btn.config(text="[Hide ▴]")
            self.code_text.config(state="normal")
            self.code_text.delete("1.0", tk.END)
            content = self.code_result if self.code_result else "(No code generated yet. Press Shift+C to generate code.)"
            self.code_text.insert("1.0", content)
            self.code_text.config(state="disabled")
            self.drawer_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 4))
            self.root.geometry(f"{self.expanded_w}x{self.expanded_h}+{self.root.winfo_x()}+{self.root.winfo_y()}")
            play_sound("Pop")
        else:
            self.unveil_btn.config(text="[Code ▾]")
            self.drawer_frame.pack_forget()
            self.root.geometry(f"{self.compact_w}x{self.compact_h}+{self.root.winfo_x()}+{self.root.winfo_y()}")
            play_sound("Pop")
        if hasattr(self, 'hwnd'):
            self._apply_stealth_styles(click_through=self.click_through)
        return "break"

    def _cycle_size(self):
        presets = [(280, 60), (370, 72), (460, 84)]
        curr_w = self.compact_w
        next_w, next_h = presets[1]
        for idx, (pw, ph) in enumerate(presets):
            if abs(curr_w - pw) < 25:
                next_w, next_h = presets[(idx + 1) % len(presets)]
                break
        self.compact_w, self.compact_h = next_w, next_h
        h = (next_h + 190) if self.is_unveiled else next_h
        self.root.geometry(f"{next_w}x{h}")
        self._update_badges()
        if hasattr(self, 'hwnd'):
            self._apply_stealth_styles(click_through=self.click_through)
        play_sound("Pop")
        print(f"\n[HUD Size] Switched to {next_w}x{h}")

    def _resize_by(self, dw, dh):
        new_w = max(240, min(SCREEN_WIDTH, self.compact_w + dw))
        new_h = max(50, min(600, self.compact_h + dh))
        self.compact_w, self.compact_h = new_w, new_h
        h = (new_h + 190) if self.is_unveiled else new_h
        self.root.geometry(f"{new_w}x{h}")
        self._update_badges()
        if hasattr(self, 'hwnd'):
            self._apply_stealth_styles(click_through=self.click_through)
        play_sound("Pop")
        print(f"\n[HUD Size] Adjusted to {new_w}x{h}")

    def _apply_theme(self):
        t = HUD_THEMES["dark"]
        self.bg_color = t["bg"]
        self.border_color = t["border"]
        self.alpha = t["default_alpha"]

        try:
            self.root.attributes("-alpha", self.alpha)
        except Exception:
            pass

        self.root.configure(bg=self.border_color)
        self.main_frame.configure(bg=self.bg_color)
        self.header.configure(bg=self.bg_color)
        self.info_row.configure(bg=self.bg_color)
        self.drawer_frame.configure(bg=self.bg_color)
        self.drawer_bar.configure(bg=self.bg_color)
        self.code_text_container.configure(bg=self.border_color)

        self.status_lbl.configure(bg=self.bg_color, fg=t["fg_locked"] if is_locked else t["fg_active"])
        self.min_btn.configure(bg=self.bg_color, fg=t["fg_hint"])
        self.action_lbl.configure(bg=self.bg_color)
        self.unveil_btn.configure(bg=self.bg_color, fg=t["fg_mcq"])
        self.theme_lbl.configure(bg=self.bg_color, fg=t["fg_hint"])
        self.mode_lbl.configure(bg=self.bg_color, fg=t["fg_hint"])
        self.typing_lbl.configure(bg=self.bg_color, fg=t["fg_sub"])
        self.preview_lbl.configure(bg=self.bg_color, fg=t["fg_text"])
        self.resize_grip.configure(bg=self.bg_color, fg=t["fg_hint"])
        self.drawer_title.configure(bg=self.bg_color, fg=t["fg_hint"])
        self.drawer_close.configure(bg=self.bg_color, fg=t["fg_mcq"])

        self.code_text.configure(bg=t["code_bg"], fg=t["code_fg"])

        self.prog_canvas.configure(bg=t["prog_bg"])
        self.prog_canvas.itemconfig(self.prog_bar, fill=t["prog_fg"])

        self._update_badges()
        if hasattr(self, 'hwnd'):
            self._apply_stealth_styles(click_through=self.click_through)

    def _apply_alpha(self):
        try:
            self.root.attributes("-alpha", self.alpha)
        except Exception:
            pass
        self._update_badges()
        if hasattr(self, 'hwnd'):
            apply_dwm_glass(self.hwnd, alpha=self.alpha)

    def _update_badges(self):
        t = HUD_THEMES["dark"]
        mode_txt = "ClickThru" if self.click_through else "Draggable"
        self.mode_lbl.config(
            text=mode_txt,
            fg=t["fg_mcq"] if not self.click_through else t["fg_hint"]
        )
        curr_w = self.root.winfo_width() if self.root.winfo_width() > 1 else self.compact_w
        if self.alpha <= 0.01:
            self.theme_lbl.config(text="Invisible (0%)", fg=t["fg_hint"])
        else:
            self.theme_lbl.config(text=f"{curr_w}px | {int(self.alpha*100)}%", fg=t["fg_hint"])

    def _process_queue(self):
        while not hud_queue.empty():
            try:
                event, data = hud_queue.get_nowait()
                t = HUD_THEMES["dark"]
                if event == "toggle_visibility":
                    self._toggle_visibility()
                elif event == "toggle_minimize":
                    if self.is_visible:
                        self._toggle_minimize()
                elif event == "toggle_click_through":
                    if self.is_visible:
                        self.click_through = not self.click_through
                        self._apply_stealth_styles(click_through=self.click_through)
                        self._update_badges()
                        play_sound("Pop")
                elif event == "toggle_code_drawer":
                    if self.is_visible:
                        self._toggle_code_drawer()
                elif event == "cycle_size":
                    if self.is_visible:
                        self._cycle_size()
                elif event == "resize_grow":
                    if self.is_visible:
                        self._resize_by(35, 6)
                elif event == "resize_shrink":
                    if self.is_visible:
                        self._resize_by(-35, -6)
                elif event == "opacity_down":
                    if self.is_visible:
                        self.alpha = max(0.00, round(self.alpha - 0.04, 2))
                        self._apply_alpha()
                elif event == "opacity_up":
                    if self.is_visible:
                        self.alpha = min(0.95, round(self.alpha + 0.04, 2))
                        self._apply_alpha()
                elif event == "status":
                    is_lock = data.get("locked", False)
                    if is_lock:
                        self.status_lbl.config(text="🔒 LOCKED", fg=t["fg_locked"])
                    else:
                        self.status_lbl.config(text="● ACTIVE", fg=t["fg_active"])
                elif event == "action_start":
                    act = data.get("action", "")
                    msg = data.get("msg", "Working...")
                    self.active_action = act
                    # Close previous code drawer and clear old history immediately
                    self._close_code_drawer()
                    self.code_result = ""
                    self.code_text.config(state="normal")
                    self.code_text.delete("1.0", tk.END)
                    self.code_text.config(state="disabled")
                    self.unveil_btn.pack_forget()
                    # Reset progress bar and typing indicator
                    self.prog_canvas.coords(self.prog_bar, 0, 0, 0, 2)
                    self.typing_lbl.config(text="Typing: Idle (Shift+P)")
                    # Show generating status badge
                    self.action_lbl.config(text=msg, fg=t["fg_mcq"])
                    if not self.is_minimized:
                        self.action_lbl.pack(side=tk.LEFT, padx=3)
                    if act == "mcq":
                        self.preview_lbl.config(text="Reading question from screen...")
                    else:
                        self.preview_lbl.config(text="Analyzing & generating solution...")
                elif event == "mcq":
                    ans = data.get("answer", "") if isinstance(data, dict) else str(data)
                    corner = data.get("corner", "") if isinstance(data, dict) else ""
                    self.active_action = "mcq"
                    badge_txt = f"🎯 MCQ: {ans}" + (f" ({corner})" if corner else "")
                    self.action_lbl.config(text=badge_txt, fg=t["fg_mcq"])
                    self.unveil_btn.pack_forget()
                    self._close_code_drawer()
                    self.preview_lbl.config(text=f"Mouse moved to {corner} ({ans})" if corner else f"Answer: {ans}")
                elif event == "code_ready":
                    act = data.get("action", "coding")
                    code = data.get("code", "")
                    summary = data.get("summary", "Code ready")
                    self.active_action = act
                    self.code_result = code
                    prefix = "💻 Code" if act in ["coding", "bug"] else "🤖 Guide"
                    self.action_lbl.config(text=f"{prefix}: Ready", fg=t["fg_active"])
                    # Pre-load code into text widget
                    self.code_text.config(state="normal")
                    self.code_text.delete("1.0", tk.END)
                    self.code_text.insert("1.0", code)
                    self.code_text.config(state="disabled")
                    # Show [Code ▾] button
                    if not self.is_minimized:
                        self.unveil_btn.pack(side=tk.LEFT, padx=2)
                    self.preview_lbl.config(text=summary)
                elif event == "preview":
                    text = data.get("text", "")
                    clean_text = text.replace("\n", " ").strip()
                    if len(clean_text) > 36:
                        clean_text = clean_text[:36] + "..."
                    self.preview_lbl.config(text=clean_text)
                elif event == "typing":
                    offset = data.get("offset", 0)
                    total = max(1, data.get("total", 1))
                    pct = int((offset / total) * 100)
                    speed = data.get("speed", TYPING_SPEED_FACTOR)
                    self.typing_lbl.config(text=f"Typing: {pct}% @ {speed:.2f}x")
                    if self.is_minimized:
                        self.status_lbl.config(text=f"● {pct}%")
                    canvas_w = self.prog_canvas.winfo_width()
                    if canvas_w > 1:
                        bar_w = int((pct / 100.0) * canvas_w)
                        self.prog_canvas.coords(self.prog_bar, 0, 0, bar_w, 2)
                elif event == "typing_paused":
                    self.typing_lbl.config(text="Typing: PAUSED (Shift+P)")
                    if self.is_minimized:
                        self.status_lbl.config(text="⏸ PAUSED")
                elif event == "typing_reset":
                    self.typing_lbl.config(text="Typing: 0% (Shift+P)")
                    self.prog_canvas.coords(self.prog_bar, 0, 0, 0, 2)
                    if self.is_minimized:
                        self.status_lbl.config(text="● ACTIVE")
                elif event == "typing_done":
                    self.typing_lbl.config(text="Typing: Complete")
                    if self.is_minimized:
                        self.status_lbl.config(text="● ACTIVE" if not is_locked else "🔒 LOCKED")
                    canvas_w = self.prog_canvas.winfo_width()
                    if canvas_w > 1:
                        self.prog_canvas.coords(self.prog_bar, 0, 0, canvas_w, 2)
                elif event == "speed":
                    speed = data.get("speed", TYPING_SPEED_FACTOR) if isinstance(data, dict) else TYPING_SPEED_FACTOR
                    self.typing_lbl.config(text=f"Speed: {speed:.2f}x")
            except Exception:
                pass

        # Periodically re-assert topmost softly without activating (only when visible!)
        self.reassert_counter += 1
        if getattr(self, 'is_visible', False) and self.reassert_counter % 20 == 0 and hasattr(self, 'hwnd') and windll:
            try:
                windll.user32.SetWindowPos(
                    self.hwnd, -1, 0, 0, 0, 0,
                    0x0001 | 0x0002 | 0x0010 | 0x0040
                )
            except Exception:
                pass

        self.root.after(80, self._process_queue)

    def start(self):
        self.root.mainloop()


def launch_hud():
    if not ENABLE_HUD:
        return
    try:
        hud = GlassHUD()
        hud.start()
    except Exception as e:
        print(f"[HUD Launch Error] {e}")


# ─── AI CALLER ────────────────────────────────────────────────────────────────

def _img_to_base64(img):
    img.thumbnail((1920, 1920))
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _call_gemini(prompt, img_b64):
    """Calls Gemini REST API (Vertex AI)."""
    parts = [{"text": prompt}]
    if img_b64:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": img_b64}})

    current_msg = {"role": "user", "parts": parts}

    if session_active and session_history:
        gemini_hist = []
        for m in session_history:
            role = "model" if m["role"] == "assistant" else "user"
            gemini_hist.append({"role": role, "parts": [{"text": m["content"]}]})
        payload = {"contents": gemini_hist + [current_msg]}
    else:
        payload = {"contents": [current_msg]}

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": PROVIDER['key']
    }

    r = api_session.post(PROVIDER['url'], headers=headers,
                         json=payload, verify=False, timeout=PROVIDER["timeout"])
    r.raise_for_status()

    candidates = r.json().get('candidates', [])
    if not candidates:
        raise ValueError("No candidates returned from Gemini API")

    resp_parts = candidates[0].get('content', {}).get('parts', [])
    # Filter out reasoning/thought parts from 3.8 Flash
    texts = [p['text'] for p in resp_parts if 'text' in p and not p.get('thought', False)]
    if texts:
        return texts[-1].strip()
    elif resp_parts and 'text' in resp_parts[0]:
        return resp_parts[0]['text'].strip()
    return ""


def extract_mcq_letter(text):
    """Pulls out just A/B/C/D from response."""
    import re
    text = text.strip()
    if text and text[0].upper() in "ABCD":
        return text[0].upper()
    match = re.search(r'\b(?:answer(?:\s+is)?|option)\s*[:\-]?\s*([ABCD])\b', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.search(r'\b([ABCD])\b', text)
    if match:
        return match.group(1).upper()
    return text


def call_ai(prompt, img=None):
    """Unified AI caller with rate-limit and error handling."""
    global session_history

    if is_provider_exhausted():
        print(f">> [{PROVIDER['name']}] ⛔ RPD exhausted — disabled until tomorrow.")
        return "Error"

    img_b64 = _img_to_base64(img) if img else None
    print(f">> [{PROVIDER['name']}] processing...")

    try:
        result = _call_gemini(prompt, img_b64)

        if session_active:
            session_history.append({"role": "user",      "content": prompt})
            session_history.append({"role": "assistant", "content": result})

        return result

    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        if code == 429 and e.response is not None:
            limit_type = parse_429_error(e.response)
            if limit_type == "RPD":
                mark_provider_exhausted()
            print(f">> [{PROVIDER['name']}] HTTP 429 ({limit_type} limit hit).")
        elif code == 503 and e.response is not None:
            print(f">> [{PROVIDER['name']}] HTTP 503 (Service Unavailable).")
        else:
            print(f">> [{PROVIDER['name']}] HTTP {code} error.")
    except requests.exceptions.RequestException as e:
        print(f">> [{PROVIDER['name']}] connection error: {e}")
    except (KeyError, IndexError, ValueError) as e:
        print(f">> [{PROVIDER['name']}] bad response structure: {e}")

    return "Error"


# ─── TEXT EXTRACTION ──────────────────────────────────────────────────────────

def extract_text_ocr(img):
    if pytesseract is None:
        print("[OCR] pytesseract not installed. Use Screenshot mode (default) or pip install pytesseract.")
        return ""
    return pytesseract.image_to_string(img).strip()


def extract_text_accessibility():
    """Extract text from focused window using Windows UI Automation via PowerShell."""
    ps_script = '''
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    try {
        $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
        if ($focused -ne $null) {
            $text = $focused.Current.Name
            try {
                $pattern = $focused.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                if ($pattern -ne $null -and $pattern.Current.Value) {
                    $text = $pattern.Current.Value
                }
            } catch {}
            if (-not $text) {
                $window = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
                    [System.Windows.Automation.TreeScope]::Children,
                    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::HasKeyboardFocusProperty, $true))
                )
                if ($window -ne $null) {
                    $text = $window.Current.Name
                }
            }
            if ($text) { Write-Output $text }
        }
    } catch {
        exit 0
    }
    '''
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""


def toggle_input_mode():
    global INPUT_MODE
    INPUT_MODE = (INPUT_MODE + 1) % len(INPUT_MODE_NAMES)
    play_sound("Glass")
    print(f"\n>> Mode switched to: {INPUT_MODE_NAMES[INPUT_MODE]}")
    update_hud("status", {"locked": is_locked, "mode": INPUT_MODE_NAMES[INPUT_MODE]})
    print_status()


# ─── TASK HANDLERS ────────────────────────────────────────────────────────────

def point_mouse_to_option(option_text):
    margin = ONE_INCH_PX
    opt = option_text.strip().lower()
    if opt.startswith('a') or 'option a' in opt:
        x, y = margin, margin
        corner = "Top-Left"
    elif opt.startswith('b') or 'option b' in opt:
        x, y = SCREEN_WIDTH - margin, margin
        corner = "Top-Right"
    elif opt.startswith('c') or 'option c' in opt:
        x, y = margin, SCREEN_HEIGHT - margin
        corner = "Bottom-Left"
    elif opt.startswith('d') or 'option d' in opt:
        x, y = SCREEN_WIDTH - margin, SCREEN_HEIGHT - margin
        corner = "Bottom-Right"
    else:
        x, y = margin, margin
        corner = "Top-Left"

    try:
        mouse_controller.position = (int(x), int(y))
    except Exception:
        pass
    if windll:
        try:
            windll.user32.SetCursorPos(int(x), int(y))
        except Exception:
            pass

    play_sound("Hero")
    print(f"\n[Mouse Signal] Moved cursor to {corner}: ({int(x)}, {int(y)}) for Option {option_text.upper()}")
    return corner


def handle_mcq():
    global latest_mcq_req_id, mcq_count
    if not can_start_ai_request("MCQ"):
        return
    try:
        with req_lock:
            latest_mcq_req_id += 1
            req_id = latest_mcq_req_id

        print(f"\nAction: MCQ [Req {req_id}]...")
        play_sound("Submarine")
        update_hud("action_start", {"action": "mcq", "msg": "🎯 MCQ: Answering..."})

        prompt_suffix = "Identify the top-most MCQ and reply with ONLY the correct letter: A, B, C, or D. No explanation."
        if INPUT_MODE == 1:  # OCR
            img = ImageGrab.grab()
            text = extract_text_ocr(img)
            print(f"[OCR] Extracted {len(text)} chars.")
            prompt = f"Below is exam screen text:\n\n{text}\n\n{prompt_suffix}"
            answer = call_ai(prompt, None)
        elif INPUT_MODE == 2:  # Accessibility
            text = extract_text_accessibility()
            print(f"[Accessibility] Extracted {len(text)} chars.")
            if not text:
                print("[Accessibility] No text found. Falling back to screenshot.")
                img = ImageGrab.grab()
                prompt = f"Look at this screenshot. {prompt_suffix}"
                answer = call_ai(prompt, img)
            else:
                prompt = f"Below is exam screen text:\n\n{text}\n\n{prompt_suffix}"
                answer = call_ai(prompt, None)
        else:  # Screenshot
            img = ImageGrab.grab()
            prompt = f"Look at this screenshot. {prompt_suffix}"
            answer = call_ai(prompt, img)

        with req_lock:
            if req_id != latest_mcq_req_id or is_locked:
                return

        if answer != "Error":
            answer = extract_mcq_letter(answer)

        print(f"\n{'='*40}\nMCQ ANSWER [Req {req_id}]: {answer}\n{'='*40}\n")
        if answer != "Error":
            mcq_count += 1
            corner = point_mouse_to_option(answer.lower())
            update_hud("mcq", {"answer": answer, "corner": corner})
    finally:
        finish_ai_request()


def auto_format_indentation(code_str, lang="cpp"):
    """
    Ensures clean, standard 4-space indentation.
    For brace-based languages (C++, Java, C, etc.), reconstructs clean indentation based on { and }.
    For Python, normalizes tabs to 4 spaces while preserving semantic structure.
    """
    if lang in ["text", "essay", "prompt"]:
        return code_str

    if lang == "python":
        return '\n'.join(line.replace('\t', '    ') for line in code_str.split('\n'))

    lines = code_str.split('\n')
    formatted_lines = []
    indent_level = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            formatted_lines.append('')
            continue

        if stripped.startswith('#'):
            formatted_lines.append(stripped)
            continue

        temp_indent = indent_level
        if stripped.startswith('}') or stripped.startswith(']') or stripped.startswith('};'):
            temp_indent = max(0, indent_level - 1)

        if stripped in ['public:', 'private:', 'protected:']:
            line_indent = max(0, temp_indent - 1) if temp_indent > 0 else 0
        elif stripped.startswith('case ') or stripped.startswith('default:'):
            line_indent = max(0, temp_indent - 1) if temp_indent > 0 else 0
        else:
            line_indent = temp_indent

        formatted_lines.append(('    ' * line_indent) + stripped)

        opens = stripped.count('{')
        closes = stripped.count('}')
        indent_level = max(0, indent_level + (opens - closes))

    return '\n'.join(formatted_lines)



def strip_markdown(text):
    lines = text.split('\n')
    lang = "cpp"
    if lines and lines[0].startswith('```'):
        first_line = lines[0].lower()
        if 'python' in first_line:
            lang = "python"
        elif 'sql' in first_line:
            lang = "sql"
        elif 'java' in first_line:
            lang = "java"
        elif 'c' in first_line or 'cpp' in first_line:
            lang = "cpp"
        lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
    else:
        sample = text[:300].lower()
        if 'select ' in sample or 'from ' in sample or 'insert into' in sample or 'create table' in sample:
            lang = "sql"
        elif 'def ' in sample or 'import ' in sample or 'print(' in sample:
            lang = "python"
        elif 'class ' in sample or 'public static' in sample or 'system.out' in sample:
            lang = "java"
        elif '#include' in sample or 'using namespace' in sample or 'std::' in sample:
            lang = "cpp"

    try:
        with open(LANG_FILE, "w", encoding="utf-8") as f:
            f.write(lang)
    except Exception:
        pass

    cleaned_code = '\n'.join(lines).strip()
    cleaned_code = auto_format_indentation(cleaned_code, lang)
    return cleaned_code


def handle_coding():
    global latest_code_req_id, session_history, code_count, ghost_typing_reset_flag, ghost_typing_offset, completion_disarm_token
    if not can_start_ai_request("Coding"):
        return

    try:
        with req_lock:
            latest_code_req_id += 1
            req_id = latest_code_req_id

        # Clear session history for new problem
        session_history = []

        print(f"\nAction: Coding / SQL Query [Req {req_id}]...")
        play_sound("Pop")
        update_hud("action_start", {"action": "coding", "msg": "💻 Code: Generating..."})

        common_instructions = (
            "STEP 1 — IDENTIFY SCREEN TYPE:\n"
            "A. SQL Problem: Table schemas, SELECT, JOIN, GROUP BY, SQL editor.\n"
            "B. Debugging Round: Pre-written buggy starter code already filled in the editor with visible sample tests.\n"
            "C. Standard Algorithm Problem: Blank editor or standard boilerplate template.\n\n"
            "STEP 2 — SOLVE STRICTLY BASED ON SCREEN TYPE:\n"
            "- IF SQL: Write ONLY the complete, valid SQL query. No other code.\n"
            "- IF DEBUGGING ROUND (PRE-WRITTEN BUGGY STARTER CODE IN EDITOR):\n"
            "  1. DO NOT rewrite from scratch with a different algorithm.\n"
            "  2. Preserve 100% of the original class name, method signatures, variable names, includes, and overall structure.\n"
            "  3. Detect and fix ALL bugs in the starter code: loop bounds (< vs <=, off-by-one), operator mistakes, uninitialized variables, integer division rounding, pointer collision/convergence, and boundary edge cases.\n"
            "  4. Return the COMPLETE corrected code file so it can replace the starter code directly.\n"
            "- IF STANDARD ALGORITHM (BLANK / BOILERPLATE):\n"
            "  Look at the language selector / template. Write the optimal, complete solution in THAT EXACT LANGUAGE (default C++).\n\n"
            "RULES:\n"
            "1. ABSOLUTELY NO COMMENTS (no #, no //, no /* */, no --).\n"
            "2. If C++, include `using namespace std;`.\n"
            "3. PROPER INDENTATION: Always format code with clean, standard 4-space indentation for all blocks, functions, and loops.\n"
            "4. Return ONLY raw code or SQL query — NO markdown fences, NO explanatory text."
        )

        if INPUT_MODE == 1:  # OCR
            img = ImageGrab.grab()
            text = extract_text_ocr(img)
            print(f"[OCR] Extracted {len(text)} chars.")
            prompt = f"Below is a problem extracted from an exam screen:\n\n{text}\n\n{common_instructions}"
            code = call_ai(prompt, None)
        elif INPUT_MODE == 2:  # Accessibility
            text = extract_text_accessibility()
            print(f"[Accessibility] Extracted {len(text)} chars.")
            if not text:
                print("[Accessibility] No text found. Falling back to screenshot.")
                img = ImageGrab.grab()
                prompt = f"Read the problem from this screenshot.\n\n{common_instructions}"
                code = call_ai(prompt, img)
            else:
                prompt = f"Below is a problem extracted from an exam screen:\n\n{text}\n\n{common_instructions}"
                code = call_ai(prompt, None)
        else:  # Screenshot
            img = ImageGrab.grab()
            prompt = f"Read the problem from this screenshot.\n\n{common_instructions}"
            code = call_ai(prompt, img)

        with req_lock:
            if req_id != latest_code_req_id or is_locked:
                print(f"--> Discarded stale/locked coding response [Req {req_id}]")
                return

        if code == "Error":
            print(f"\n[Req {req_id}] Provider failed. Output untouched.")
            play_sound("Basso")
            return

        code = strip_markdown(code)
        print(f"\n{'='*40}\nSOLUTION SAVED TO FILE! [Req {req_id}]\n{'='*40}\n")
        with open(CODE_FILE, "w", encoding="utf-8") as f:
            f.write(code + "\n\n")
        with state_lock:
            completion_disarm_token += 1
            ghost_typing_reset_flag = True
            ghost_typing_offset = 0
            ghost_typing_completed_notified = False
            if TYPING_MODE == 2:
                ghost_typing_active = True
        play_sound("Ping")
        code_count += 1
        update_hud("code_ready", {"action": "coding", "code": code, "summary": "Full solution ready (Shift+P to type)"})
        print_status()
    finally:
        finish_ai_request()


def handle_bug_report():
    global latest_code_req_id, code_count, ghost_typing_reset_flag, ghost_typing_offset, completion_disarm_token
    if not can_start_ai_request("Bug Report"):
        return
    try:
        with req_lock:
            latest_code_req_id += 1
            req_id = latest_code_req_id

        print(f"\nAction: Bug Report [Req {req_id}]...")
        play_sound("Pop")
        update_hud("action_start", {"action": "bug", "msg": "🐛 Debug: Fixing..."})

        if not session_active:
            print("[Warning] Session is NOT active! The AI won't remember the previous code. Press Right Shift + S to start a session before generating the initial code.")

        rules = (
            "RULES:\n1. Accurate, optimal, concise.\n2. ABSOLUTELY NO COMMENTS (no #, no //, no /* */).\n"
            "3. If C++, include `using namespace std;`.\n4. Standard 4-space indentation.\n5. Return ONLY raw code."
        )

        if INPUT_MODE == 1:  # OCR
            img = ImageGrab.grab()
            text = extract_text_ocr(img)
            print(f"[OCR] Extracted {len(text)} chars.")
            prompt = f"Below is a test case failure or error message:\n\n{text}\n\nDiagnose and fix the solution.\n{rules}"
            code = call_ai(prompt, None)
        elif INPUT_MODE == 2:  # Accessibility
            text = extract_text_accessibility()
            print(f"[Accessibility] Extracted {len(text)} chars.")
            if not text:
                print("[Accessibility] No text found. Falling back to screenshot.")
                img = ImageGrab.grab()
                prompt = f"Read the test case failure from this screenshot. Diagnose and fix the solution.\n{rules}"
                code = call_ai(prompt, img)
            else:
                prompt = f"Below is a test case failure or error message:\n\n{text}\n\nDiagnose and fix the solution.\n{rules}"
                code = call_ai(prompt, None)
        else:  # Screenshot
            img = ImageGrab.grab()
            prompt = f"Read the test case failure from this screenshot. Diagnose and fix the solution.\n{rules}"
            code = call_ai(prompt, img)

        with req_lock:
            if req_id != latest_code_req_id or is_locked:
                print(f"--> Discarded stale/locked bug report response [Req {req_id}]")
                return

        if code == "Error":
            print(f"\n[Req {req_id}] Provider failed. Output untouched.")
            play_sound("Basso")
            return

        code = strip_markdown(code)
        print(f"\n{'='*40}\nBUG FIXED SOLUTION SAVED TO FILE! [Req {req_id}]\n{'='*40}\n")
        with open(CODE_FILE, "w", encoding="utf-8") as f:
            f.write(code + "\n\n")
        with state_lock:
            completion_disarm_token += 1
            ghost_typing_reset_flag = True
            ghost_typing_offset = 0
            ghost_typing_completed_notified = False
            if TYPING_MODE == 2:
                ghost_typing_active = True
        play_sound("Ping")
        code_count += 1
        update_hud("code_ready", {"action": "bug", "code": code, "summary": "Bug-fixed code ready (Shift+P to type)"})
        print_status()
    finally:
        finish_ai_request()


def handle_essay():
    global latest_essay_req_id, essay_count, ghost_typing_reset_flag, completion_disarm_token
    if not can_start_ai_request("Essay"):
        return
    try:
        with req_lock:
            latest_essay_req_id += 1
            req_id = latest_essay_req_id

        print(f"\nAction: Essay [Req {req_id}]...")
        play_sound("Pop")

        essay_prompt_rules = (
            "Write a high-quality, human-sounding response. "
            "Plain paragraphs only — no bullet points, no bold, no markdown. Return ONLY the essay text."
        )

        if INPUT_MODE == 1:  # OCR
            img = ImageGrab.grab()
            text = extract_text_ocr(img)
            print(f"[OCR] Extracted {len(text)} chars.")
            prompt = f"Below is an essay or short-answer prompt:\n\n{text}\n\n{essay_prompt_rules}"
            essay = call_ai(prompt, None)
        elif INPUT_MODE == 2:  # Accessibility
            text = extract_text_accessibility()
            print(f"[Accessibility] Extracted {len(text)} chars.")
            if not text:
                print("[Accessibility] No text found. Falling back to screenshot.")
                img = ImageGrab.grab()
                prompt = f"Read the essay prompt from this screenshot. {essay_prompt_rules}"
                essay = call_ai(prompt, img)
            else:
                prompt = f"Below is an essay or short-answer prompt:\n\n{text}\n\n{essay_prompt_rules}"
                essay = call_ai(prompt, None)
        else:  # Screenshot
            img = ImageGrab.grab()
            prompt = f"Read the essay prompt from this screenshot. {essay_prompt_rules}"
            essay = call_ai(prompt, img)

        with req_lock:
            if req_id != latest_essay_req_id or is_locked:
                return

        if essay == "Error":
            print(f"\n[Req {req_id}] Provider failed. Output untouched.")
            play_sound("Basso")
            return

        print(f"\n{'='*40}\nESSAY SAVED TO FILE! [Req {req_id}]\n{'='*40}\n")
        with open(CODE_FILE, "w", encoding="utf-8") as f:
            f.write(essay + "\n\n")
        try:
            with open(LANG_FILE, "w", encoding="utf-8") as lf:
                lf.write("text")
        except Exception:
            pass
        with state_lock:
            completion_disarm_token += 1
            ghost_typing_reset_flag = True
            ghost_typing_offset = 0
            ghost_typing_completed_notified = False
            if TYPING_MODE == 2:
                ghost_typing_active = True
        play_sound("Ping")
        essay_count += 1
        print_status()
    finally:
        finish_ai_request()


# ─── GUIDED INTERVIEW HANDLERS ────────────────────────────────────────────────

def handle_guided_prompt():
    """Generates an architectural steering prompt (~350 words) to guide on-screen AI."""
    global latest_guided_req_id, session_history, guided_count, ghost_typing_reset_flag, ghost_typing_offset, completion_disarm_token
    if not can_start_ai_request("Guided Prompt"):
        return
    try:
        with req_lock:
            latest_guided_req_id += 1
            req_id = latest_guided_req_id

        # Reset session history for a new problem
        session_history = []

        print(f"\nAction: Guided Interview Steering Prompt [Req {req_id}]...")
        play_sound("Pop")
        update_hud("action_start", {"action": "guided", "msg": "🤖 Guide: Analyzing..."})

        guided_instructions = (
            "Generate a concise, direct architectural prompt for an on-screen AI assistant to solve the problem.\n"
            "Keep it simple, straightforward bullet points without over-explanation.\n\n"
            "FORMAT:\n"
            "Solve this problem following these technical specifications:\n"
            "- Language: [Language visible on screen, default C++]\n"
            "- Approach: [Optimal algorithmic strategy]\n"
            "- Variables to Use: [Exact variables and data structures to declare, e.g. unordered_map<int, int> prefix_counts, int current_sum = 0, int count = 0]\n"
            "- Core Logic: [Direct 1-2 sentence loop and state transition logic]\n"
            "- Edge Cases: [Empty input, single element, negative numbers, zeros, overflow]\n"
            "- Complexity: [Time O(...), Space O(...)]\n"
            "Provide complete, clean code directly without explanations.\n\n"
            "RULES:\n"
            "1. Simple, straight-forward bullet points only.\n"
            "2. Include exact variables and data structures to use without over-explanation.\n"
            "3. NO markdown code blocks (no ```), NO quotes, NO conversational filler."
        )

        if INPUT_MODE == 1:  # OCR
            img = ImageGrab.grab()
            text = extract_text_ocr(img)
            print(f"[OCR] Extracted {len(text)} chars.")
            prompt = f"Below is a coding problem extracted from the screen:\n\n{text}\n\n{guided_instructions}"
            result = call_ai(prompt, None)
        elif INPUT_MODE == 2:  # Accessibility
            text = extract_text_accessibility()
            print(f"[Accessibility] Extracted {len(text)} chars.")
            if not text:
                print("[Accessibility] No text found. Falling back to screenshot.")
                img = ImageGrab.grab()
                prompt = f"Read the problem from this screenshot.\n\n{guided_instructions}"
                result = call_ai(prompt, img)
            else:
                prompt = f"Below is a coding problem extracted from the screen:\n\n{text}\n\n{guided_instructions}"
                result = call_ai(prompt, None)
        else:  # Screenshot
            img = ImageGrab.grab()
            prompt = f"Read the problem from this screenshot.\n\n{guided_instructions}"
            result = call_ai(prompt, img)

        with req_lock:
            if req_id != latest_guided_req_id or is_locked:
                print(f"--> Discarded stale/locked guided response [Req {req_id}]")
                return

        if result == "Error":
            print(f"\n[Req {req_id}] Provider failed. Output untouched.")
            play_sound("Basso")
            return

        # Strip any accidental markdown fences
        if result.startswith("```"):
            lines = result.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            result = "\n".join(lines).strip()

        print(f"\n{'='*40}\nGUIDED STEERING PROMPT SAVED! [Req {req_id}]\n{'='*40}\n")
        print(result[:400] + ("..." if len(result) > 400 else ""))
        print(f"\n{'='*40}\n(Press Shift + P to ghost-type this prompt into the AI chat box)\n{'='*40}\n")

        with open(CODE_FILE, "w", encoding="utf-8") as f:
            f.write(result + "\n\n")

        try:
            with open(LANG_FILE, "w", encoding="utf-8") as lf:
                lf.write("prompt")
        except Exception:
            pass

        with state_lock:
            completion_disarm_token += 1
            ghost_typing_reset_flag = True
            ghost_typing_offset = 0
            ghost_typing_completed_notified = False
            if TYPING_MODE == 2:
                ghost_typing_active = True
        play_sound("Ping")
        guided_count += 1
        update_hud("code_ready", {"action": "guided", "code": result, "summary": "Guided prompt ready (Shift+P to type)"})
        print_status()
    finally:
        finish_ai_request()


def handle_critique_prompt():
    """Generates a concise code review & bug fix critique (<120 words) to feed on-screen AI."""
    global latest_critique_req_id, critique_count, ghost_typing_reset_flag, ghost_typing_offset, completion_disarm_token
    if not can_start_ai_request("Critique Prompt"):
        return
    try:
        with req_lock:
            latest_critique_req_id += 1
            req_id = latest_critique_req_id

        print(f"\nAction: Guided Interview Critique / Fix Prompt [Req {req_id}]...")
        play_sound("Pop")
        update_hud("action_start", {"action": "critique", "msg": "🤖 Critique: Diagnosing..."})

        critique_instructions = (
            "Generate a technical bug fix prompt for the on-screen AI assistant.\n"
            "Format strictly in clean, technical bullet points without conversational filler.\n\n"
            "FORMAT (Use this exact bullet-point structure):\n"
            "The current solution failed on a test case:\n"
            "- Failing Test Case: [Input and actual vs expected output]\n"
            "- Root Cause: [Exact bug location and cause, e.g. off-by-one boundary, missed base condition, integer overflow]\n"
            "- Fix & Variable Changes: [Specify exact variables, condition checks, and code lines to adjust]\n"
            "- Edge Case Guard: [Boundary check to add to prevent similar failures]\n"
            "- Target Complexity: [O(...) time, O(...) space]\n"
            "Provide the complete updated code with this fix applied directly without explanations.\n\n"
            "RULES:\n"
            "1. Concrete, technical bullet points with exact variable and logic adjustments.\n"
            "2. NO markdown code fences (no ```), NO quotes, NO conversational filler."
        )

        if INPUT_MODE == 1:  # OCR
            img = ImageGrab.grab()
            text = extract_text_ocr(img)
            print(f"[OCR] Extracted {len(text)} chars.")
            prompt = f"Below is the screen text showing code and test results:\n\n{text}\n\n{critique_instructions}"
            result = call_ai(prompt, None)
        elif INPUT_MODE == 2:  # Accessibility
            text = extract_text_accessibility()
            print(f"[Accessibility] Extracted {len(text)} chars.")
            if not text:
                print("[Accessibility] No text found. Falling back to screenshot.")
                img = ImageGrab.grab()
                prompt = f"Read the code and failed test from this screenshot.\n\n{critique_instructions}"
                result = call_ai(prompt, img)
            else:
                prompt = f"Below is the screen text showing code and test results:\n\n{text}\n\n{critique_instructions}"
                result = call_ai(prompt, None)
        else:  # Screenshot
            img = ImageGrab.grab()
            prompt = f"Read the code and failed test from this screenshot.\n\n{critique_instructions}"
            result = call_ai(prompt, img)

        with req_lock:
            if req_id != latest_critique_req_id or is_locked:
                print(f"--> Discarded stale/locked critique response [Req {req_id}]")
                return

        if result == "Error":
            print(f"\n[Req {req_id}] Provider failed. Output untouched.")
            play_sound("Basso")
            return

        # Strip any accidental markdown fences
        if result.startswith("```"):
            lines = result.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            result = "\n".join(lines).strip()

        print(f"\n{'='*40}\nCRITIQUE & FIX PROMPT SAVED! [Req {req_id}]\n{'='*40}\n")
        print(result[:400] + ("..." if len(result) > 400 else ""))
        print(f"\n{'='*40}\n(Press Shift + P to ghost-type this critique into the AI chat box)\n{'='*40}\n")

        with open(CODE_FILE, "w", encoding="utf-8") as f:
            f.write(result + "\n\n")

        try:
            with open(LANG_FILE, "w", encoding="utf-8") as lf:
                lf.write("prompt")
        except Exception:
            pass

        with state_lock:
            completion_disarm_token += 1
            ghost_typing_reset_flag = True
            ghost_typing_offset = 0
            ghost_typing_completed_notified = False
            if TYPING_MODE == 2:
                ghost_typing_active = True
        play_sound("Ping")
        critique_count += 1

        update_hud("code_ready", {"action": "critique", "code": result, "summary": "Critique prompt ready (Shift+P to type)"})
        print_status()
    finally:
        finish_ai_request()



# ─── GHOST TYPING ─────────────────────────────────────────────────────────────

def reset_ghost_typing():
    """Reset typing progress back to the beginning (0%)."""
    global ghost_typing_offset, ghost_typing_reset_flag, ghost_typing_active
    global ghost_typing_completed_notified, completion_disarm_token
    with state_lock:
        completion_disarm_token += 1
        ghost_typing_active = False
    ghost_typing_offset = 0
    ghost_typing_reset_flag = True
    ghost_typing_completed_notified = False
    print("\n[Ghost Typing] ⏪ Rewound to beginning (0%). Press Right Shift + P to type from start.")
    play_sound("Hero")
    update_hud("typing_reset")


def interruptible_sleep(duration):
    """Sleep in short slices so pausing ghost typing halts execution within 15-20ms."""
    step = 0.02
    elapsed = 0.0
    while elapsed < duration:
        if not ghost_typing_active or is_locked:
            return False
        rem = min(step, duration - elapsed)
        time.sleep(rem)
        elapsed += rem
    return True


def type_text():
    global ghost_typing_active, ghost_typing_reset_flag, ghost_typing_offset
    ctrl = keyboard.Controller()

    # Release any shift keys currently held or stuck
    try:
        ctrl.release(keyboard.Key.shift)
        ctrl.release(keyboard.Key.shift_l)
        ctrl.release(keyboard.Key.shift_r)
    except Exception:
        pass

    # Give user brief pause to release physical Shift + P keys
    if not interruptible_sleep(0.18):
        with state_lock:
            ghost_typing_active = False
        return

    full_text = ""
    try:
        if not os.path.exists(CODE_FILE):
            with state_lock:
                ghost_typing_active = False
            return

        with open(CODE_FILE, "r", encoding="utf-8") as f:
            full_text = f.read()

        # Normalize carriage returns
        full_text = full_text.replace('\r\n', '\n').replace('\r', '\n')

        lang = "cpp"
        if os.path.exists(LANG_FILE):
            try:
                with open(LANG_FILE, "r", encoding="utf-8") as lf:
                    lang = lf.read().strip()
            except Exception:
                pass

        # Ensure code has clean indentation
        full_text = auto_format_indentation(full_text, lang)

        if ghost_typing_reset_flag or ghost_typing_offset >= len(full_text):
            ghost_typing_reset_flag = False
            ghost_typing_offset = 0

        total_len = len(full_text)
        print(f"\n[Ghost Typing] Resumed/Started ({ghost_typing_offset}/{total_len} chars) [{INDENT_MODE_NAMES[INDENT_MODE]}] at {TYPING_SPEED_FACTOR:.2f}x speed.")
        play_sound("Hero")

        scale = 1.0 / max(0.1, TYPING_SPEED_FACTOR)

        # Helper to compute indentation level of the current line at any offset
        def get_current_indent(text, off):
            if off == 0:
                return 0
            prev_nl = text.rfind('\n', 0, off)
            start = 0 if prev_nl == -1 else prev_nl + 1
            next_nl = text.find('\n', start)
            end = len(text) if next_nl == -1 else next_nl
            line = text[start:end]
            return len(line) - len(line.lstrip(' '))

        at_line_start = (ghost_typing_offset == 0 or (ghost_typing_offset > 0 and full_text[ghost_typing_offset - 1] == '\n'))
        editor_indent = get_current_indent(full_text, ghost_typing_offset)

        while ghost_typing_offset < total_len:
            if not ghost_typing_active or is_locked:
                break

            # Smart-Indent Delta Processing for LeetCode / Monaco / Web IDEs
            if INDENT_MODE == 0 and lang not in ["text", "essay", "prompt"] and at_line_start:
                line_end = full_text.find('\n', ghost_typing_offset)
                if line_end == -1:
                    line_end = total_len
                line_str = full_text[ghost_typing_offset:line_end]
                stripped = line_str.lstrip(' ')
                target_indent = len(line_str) - len(stripped)

                if stripped:  # Non-empty code line
                    delta = target_indent - editor_indent
                    if delta > 0:
                        # Editor carries less indent than needed -> type missing spaces one by one
                        for _ in range(delta):
                            if not ghost_typing_active or is_locked:
                                break
                            win32_send_char(' ')
                            if not interruptible_sleep(max(0.018, random.uniform(0.024, 0.034) * scale)):
                                break
                    elif delta < 0:
                        # Editor carries more indent than needed -> unindent via backspace (4 spaces per press)
                        num_backspaces = abs(delta) // 4
                        for _ in range(num_backspaces):
                            if not ghost_typing_active or is_locked:
                                break
                            win32_send_vk(0x08)
                            if not interruptible_sleep(max(0.030, random.uniform(0.040, 0.060) * scale)):
                                break
                    editor_indent = target_indent
                    ghost_typing_offset += target_indent

                at_line_start = False
                continue

            if ghost_typing_offset >= total_len:
                break

            char = full_text[ghost_typing_offset]

            try:
                if char == '\n':
                    if lang == "prompt":
                        # In chat boxes, Shift+Enter inserts a newline without prematurely sending
                        win32_send_vk(0x0D, shift=True)
                    else:
                        win32_send_vk(0x0D, shift=False)
                    at_line_start = True
                    # Let Monaco/editor process newline and carry over indentation smoothly
                    if not interruptible_sleep(max(0.080, random.uniform(0.120, 0.200) * scale)):
                        break
                elif char == '\t':
                    for _ in range(4):
                        if not ghost_typing_active or is_locked:
                            break
                        win32_send_char(' ')
                        if not interruptible_sleep(max(0.018, random.uniform(0.024, 0.034) * scale)):
                            break
                else:
                    win32_send_char(char)
            except Exception:
                pass

            ghost_typing_offset += 1
            if ghost_typing_offset % 3 == 0 or ghost_typing_offset == total_len:
                update_hud("typing", {"offset": ghost_typing_offset, "total": total_len, "speed": TYPING_SPEED_FACTOR})

            # Natural human letter-by-letter typing cadence
            if char in ['\n', '\r']:
                delay = 0  # Already paused after enter
            elif char in [' ', '\t']:
                delay = max(0.025, random.uniform(0.038, 0.065) * scale)
            elif char in ['(', ')', '{', '}', '[', ']', ';', ':', '=', '+', '-', '*', '/', '<', '>', '&', '|', '!', ',', '.']:
                delay = max(0.030, random.uniform(0.048, 0.082) * scale)
            else:
                delay = max(0.020, random.uniform(0.032, 0.055) * scale)

            if delay > 0:
                if not interruptible_sleep(delay):
                    break

    except Exception as e:
        print(f"\n[Ghost Typing] Error: {e}")

    with state_lock:
        ghost_typing_active = False

    if full_text and ghost_typing_offset >= len(full_text):
        ghost_typing_offset = 0
        print("\n[Ghost Typing] Finished (100%). Reset to start.")
        update_hud("typing_done")
        play_sound("Purr")
    else:
        print(f"\n[Ghost Typing] ⏸️ Paused at char {ghost_typing_offset}/{len(full_text) if full_text else '?'}. (Press Shift+R to reset, Shift+P to resume).")
        update_hud("typing_paused", {"offset": ghost_typing_offset})


last_toggle_time = 0

def toggle_ghost_typing():
    global ghost_typing_active, ghost_typing_thread, last_toggle_time
    global ghost_typing_content, ghost_typing_reset_flag, ghost_typing_offset, completion_disarm_token

    if is_locked:
        return

    now = time.time()
    # Debounce 0.35s to prevent key repeat bounce from toggling back immediately
    if now - last_toggle_time < 0.35:
        return
    last_toggle_time = now

    with state_lock:
        if ghost_typing_active:
            # INSTANT STOP
            ghost_typing_active = False
            play_sound("Pop")
            update_hud("typing_paused", {"offset": ghost_typing_offset})
            print(f"\n[Ghost Typing] ⏸️ Paused at char {ghost_typing_offset}. (Press Shift+P to resume).")
            return

        # START OR RESUME
        if not os.path.exists(CODE_FILE):
            open(CODE_FILE, "w", encoding="utf-8").close()

        with open(CODE_FILE, "r", encoding="utf-8") as f:
            current_content = f.read()

        if current_content != ghost_typing_content:
            ghost_typing_reset_flag = True
            ghost_typing_offset = 0
            ghost_typing_completed_notified = False
            ghost_typing_content = current_content

        # If already at 100%, restart from 0 on Shift+P
        if ghost_typing_offset >= len(current_content):
            ghost_typing_offset = 0
            ghost_typing_reset_flag = True
            ghost_typing_completed_notified = False

        completion_disarm_token += 1
        ghost_typing_active = True
        if TYPING_MODE == 1:
            ghost_typing_thread = threading.Thread(target=type_text, daemon=True)
            ghost_typing_thread.start()
        else:
            total_chars = len(current_content)
            print(f"\n[Interactive Typing] ▶️ Armed ({ghost_typing_offset}/{total_chars} chars). Type ANY keys to type code! (Esc to pause).")
            play_sound("Hero")


# ─── INTERACTIVE HACKER TYPER (MODE 2) ────────────────────────────────────────

interactive_typing_queue = queue.Queue()

def win32_send_char(char):
    """Sends a single Unicode character tagged with MAGIC_EXTRA."""
    if sys.platform == "win32" and windll:
        code = ord(char)
        # KEYEVENTF_UNICODE = 0x0004, KEYEVENTF_KEYUP = 0x0002
        windll.user32.keybd_event(0, code, 0x0004, MAGIC_EXTRA)
        windll.user32.keybd_event(0, code, 0x0006, MAGIC_EXTRA)
    else:
        ctrl = keyboard.Controller()
        ctrl.type(char)

def win32_send_vk(vk, shift=False):
    """Sends a virtual key code tagged with MAGIC_EXTRA."""
    if sys.platform == "win32" and windll:
        if shift:
            windll.user32.keybd_event(0x10, 0, 0, MAGIC_EXTRA)       # Shift down
        windll.user32.keybd_event(vk, 0, 0, MAGIC_EXTRA)             # Key down
        windll.user32.keybd_event(vk, 0, 2, MAGIC_EXTRA)             # Key up
        if shift:
            windll.user32.keybd_event(0x10, 0, 2, MAGIC_EXTRA)       # Shift up
    else:
        ctrl = keyboard.Controller()
        if vk == 0x0D:
            if shift:
                with ctrl.pressed(keyboard.Key.shift):
                    ctrl.press(keyboard.Key.enter)
                    ctrl.release(keyboard.Key.enter)
            else:
                ctrl.press(keyboard.Key.enter)
                ctrl.release(keyboard.Key.enter)
        elif vk == 0x08:
            ctrl.press(keyboard.Key.backspace)
            ctrl.release(keyboard.Key.backspace)


completion_disarm_token = 0

def auto_disarm_after_completion(token):
    """Absorbs residual rapid key taps for 0.4s, then automatically restores the keyboard."""
    global ghost_typing_active, completion_disarm_token
    time.sleep(0.4)
    if token != completion_disarm_token:
        return
    while not interactive_typing_queue.empty():
        try:
            interactive_typing_queue.get_nowait()
        except Exception:
            break
    with state_lock:
        if token == completion_disarm_token:
            ghost_typing_active = False
    print("\n[Interactive Typing] ✅ 100% Complete — Keyboard restored to normal.")


def type_next_interactive_char():
    global ghost_typing_offset, ghost_typing_reset_flag, ghost_typing_active
    global ghost_typing_content, is_self_typing, ghost_typing_completed_notified
    global cached_interactive_text, cached_interactive_mtime, completion_disarm_token

    if is_locked or not ghost_typing_active or TYPING_MODE != 2:
        return

    if not os.path.exists(CODE_FILE):
        return

    try:
        mtime = os.path.getmtime(CODE_FILE)
        if mtime != cached_interactive_mtime or not cached_interactive_text:
            with open(CODE_FILE, "r", encoding="utf-8") as f:
                raw_text = f.read()
            raw_text = raw_text.replace('\r\n', '\n').replace('\r', '\n')
            lang = "cpp"
            if os.path.exists(LANG_FILE):
                try:
                    with open(LANG_FILE, "r", encoding="utf-8") as lf:
                        lang = lf.read().strip()
                except Exception:
                    pass
            cached_interactive_text = auto_format_indentation(raw_text, lang)
            cached_interactive_mtime = mtime
    except Exception:
        return

    full_text = cached_interactive_text
    total_len = len(full_text)
    if total_len == 0:
        return

    if ghost_typing_reset_flag:
        ghost_typing_reset_flag = False
        ghost_typing_offset = 0
        ghost_typing_completed_notified = False

    # Once 100% is reached:
    if ghost_typing_offset >= total_len:
        if not ghost_typing_completed_notified:
            ghost_typing_completed_notified = True
            print("\n[Interactive Typing] Code 100% typed! (Restoring keyboard in 0.4s...)")
            play_sound("Purr")
            update_hud("typing_done")
            completion_disarm_token += 1
            threading.Thread(target=auto_disarm_after_completion, args=(completion_disarm_token,), daemon=True).start()
        return

    lang = "cpp"
    if os.path.exists(LANG_FILE):
        try:
            with open(LANG_FILE, "r", encoding="utf-8") as lf:
                lang = lf.read().strip()
        except Exception:
            pass

    char = full_text[ghost_typing_offset]

    is_self_typing = True
    try:
        if char == '\n':
            if lang == "prompt":
                win32_send_vk(0x0D, shift=True)
            else:
                win32_send_vk(0x0D, shift=False)
            ghost_typing_offset += 1
            if INDENT_MODE == 0 and ghost_typing_offset < total_len and lang not in ["text", "essay", "prompt"]:
                line_end = full_text.find('\n', ghost_typing_offset)
                if line_end == -1:
                    line_end = total_len
                line_str = full_text[ghost_typing_offset:line_end]
                stripped = line_str.lstrip(' ')
                target_indent = len(line_str) - len(stripped)
                if target_indent > 0:
                    ghost_typing_offset += target_indent
        elif char == '\t':
            for _ in range(4):
                win32_send_char(' ')
            ghost_typing_offset += 1
        else:
            win32_send_char(char)
            ghost_typing_offset += 1
    except Exception:
        ghost_typing_offset += 1
    finally:
        is_self_typing = False

    if ghost_typing_offset % 3 == 0 or ghost_typing_offset >= total_len:
        update_hud("typing", {"offset": ghost_typing_offset, "total": total_len, "speed": TYPING_SPEED_FACTOR})

    if ghost_typing_offset >= total_len:
        if not ghost_typing_completed_notified:
            ghost_typing_completed_notified = True
            print("\n[Interactive Typing] Code 100% typed! (Restoring keyboard in 0.4s...)")
            play_sound("Purr")
            update_hud("typing_done")
            completion_disarm_token += 1
            threading.Thread(target=auto_disarm_after_completion, args=(completion_disarm_token,), daemon=True).start()


def interactive_typing_worker():
    while True:
        try:
            interactive_typing_queue.get()
            type_next_interactive_char()
        except Exception:
            pass


# Background consumer thread for interactive typing
threading.Thread(target=interactive_typing_worker, daemon=True).start()


def clear_clipboard():
    global ghost_typing_active, ghost_typing_offset, ghost_typing_completed_notified
    with state_lock:
        ghost_typing_active = False
    ghost_typing_offset = 0
    ghost_typing_completed_notified = False
    pyperclip.copy("")
    with open(CODE_FILE, "w", encoding="utf-8") as f:
        f.write("")
    print("\n[Clipboard and code.txt] Cleared.")
    play_sound("Basso")


# ─── SESSION MANAGEMENT ───────────────────────────────────────────────────────

def start_session():
    global session_active, session_history
    session_active  = True
    session_history = []
    print("\n[Session] STARTED — Context memory enabled.")
    play_sound("Glass")
    print_status()

def quit_session():
    global session_active, session_history
    session_active  = False
    session_history = []
    print("\n[Session] ENDED — Context memory cleared.")
    play_sound("Tink")
    print_status()


# ─── MOUSE & KEYBOARD ─────────────────────────────────────────────────────────

current_keys = set()
lock         = threading.Lock()


shift_pressed = False

def is_shift_down():
    global shift_pressed
    if shift_pressed:
        return True
    if any(k in current_keys for k in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r)):
        return True
    if sys.platform == "win32" and windll:
        try:
            return bool(
                (windll.user32.GetAsyncKeyState(0x10) & 0x8000) or
                (windll.user32.GetAsyncKeyState(0xA0) & 0x8000) or
                (windll.user32.GetAsyncKeyState(0xA1) & 0x8000)
            )
        except Exception:
            pass
    return False


def is_ctrl_down():
    if any(k in current_keys for k in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)):
        return True
    if sys.platform == "win32" and windll:
        try:
            return bool(windll.user32.GetAsyncKeyState(0x11) & 0x8000)
        except Exception:
            pass
    return False


def is_alt_down():
    if any(k in current_keys for k in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r)):
        return True
    if sys.platform == "win32" and windll:
        try:
            return bool(windll.user32.GetAsyncKeyState(0x12) & 0x8000)
        except Exception:
            pass
    return False


def on_click(x, y, button, pressed):
    if not pressed or is_locked:
        return
    if button == mouse.Button.right:
        print(f"[Debug] Right-Click at: ({x}, {y}) | Zone: {TRIGGER_MARGIN}px")

        # Bottom-Left: Essay
        if x <= TRIGGER_MARGIN and y >= SCREEN_HEIGHT - TRIGGER_MARGIN:
            threading.Thread(target=handle_essay).start()

        # Bottom-Right: Clear Clipboard
        elif x >= SCREEN_WIDTH - TRIGGER_MARGIN and y >= SCREEN_HEIGHT - TRIGGER_MARGIN:
            clear_clipboard()


# Global reference to keyboard listener for win32 filter suppression
keyboard_listener = None

HOTKEY_VKS = {
    191,                 # ? /
    80,                  # P (Toggle Typing)
    89, 72,              # Y, H (Toggle Mode)
    82,                  # R (Reset Typing)
    67, 71, 70, 77, 66,  # C (Code), G (Guided), F (Critique), M (MCQ), B (Bug Report)
    83, 68, 76, 73,      # S (Start), D (Quit), L (Input Mode), I (Indent Mode)
    86, 84, 79, 75, 78,  # V, T, O, K, N (HUD Controls)
    219, 221,            # [ , ] (HUD Opacity)
    187, 107,            # = , Num+ (HUD Grow)
    189, 109,            # - , Num- (HUD Shrink)
    38, 40               # Up, Down (Typing Speed)
}

def dispatch_hotkey(vk):
    """Executes assistant hotkeys triggered with Shift.
    Runs on a daemon thread to prevent blocking low-level keyboard hooks."""
    global TYPING_SPEED_FACTOR

    # 1. Lock toggle: Shift + ? or Shift + /
    if vk == 191:
        toggle_lock()
        return

    # If assistant is locked, freeze all other hotkeys
    if is_locked:
        return

    # 2. Ghost typing controls
    if vk == 80:     # Shift + P: Toggle typing (Pause / Resume / Arm)
        toggle_ghost_typing()
    elif vk in (89, 72):  # Shift + Y or Shift + H: Toggle typing mode
        toggle_typing_mode()
    elif vk == 82:   # Shift + R: Rewind / reset typing
        reset_ghost_typing()
    elif vk == 67:   # Shift + C: Direct coding solve
        threading.Thread(target=handle_coding, daemon=True).start()
    elif vk == 71:   # Shift + G: Guided interview prompt
        threading.Thread(target=handle_guided_prompt, daemon=True).start()
    elif vk == 70:   # Shift + F: Critique / test failure prompt
        threading.Thread(target=handle_critique_prompt, daemon=True).start()
    elif vk == 77:   # Shift + M: MCQ / AI literacy
        threading.Thread(target=handle_mcq, daemon=True).start()
    elif vk == 66:   # Shift + B: Bug report
        threading.Thread(target=handle_bug_report, daemon=True).start()
    elif vk == 83:   # Shift + S: Start session
        start_session()
    elif vk == 68:   # Shift + D: Quit session
        quit_session()
    elif vk == 76:   # Shift + L: Toggle input mode (OCR / Screenshot)
        toggle_input_mode()
    elif vk == 73:   # Shift + I: Toggle indent mode
        toggle_indent_mode()
    elif vk == 86:   # Shift + V: HUD visibility
        update_hud("toggle_visibility")
    elif vk == 84:   # Shift + T: HUD click-through
        update_hud("toggle_click_through")
    elif vk == 79:   # Shift + O: HUD cycle size
        update_hud("cycle_size")
    elif vk == 75:   # Shift + K: HUD code drawer
        update_hud("toggle_code_drawer")
    elif vk == 78:   # Shift + N: HUD minimize
        update_hud("toggle_minimize")
    elif vk == 219:  # Shift + [: HUD opacity down
        update_hud("opacity_down")
    elif vk == 221:  # Shift + ]: HUD opacity up
        update_hud("opacity_up")
    elif vk in (187, 107):  # Shift + = / +: HUD grow
        update_hud("resize_grow")
    elif vk in (189, 109):  # Shift + - / _: HUD shrink
        update_hud("resize_shrink")
    elif vk == 38:   # Shift + Up: Speed up
        with lock:
            TYPING_SPEED_FACTOR = min(3.0, round(TYPING_SPEED_FACTOR + 0.25, 2))
            print(f"\n[Speed] {TYPING_SPEED_FACTOR:.2f}x")
            update_hud("speed", {"speed": TYPING_SPEED_FACTOR})
            play_sound("Ping")
    elif vk == 40:   # Shift + Down: Speed down
        with lock:
            TYPING_SPEED_FACTOR = max(0.25, round(TYPING_SPEED_FACTOR - 0.25, 2))
            print(f"\n[Speed] {TYPING_SPEED_FACTOR:.2f}x")
            update_hud("speed", {"speed": TYPING_SPEED_FACTOR})
            play_sound("Pop")


suppressed_down_vks = set()

def win32_filter(msg, data):
    """Windows low-level hook filter.
    Intercepts and suppresses hotkeys so they NEVER type letters into active applications.
    In Mode 2 (Interactive Hacker Typer), intercepts and suppresses physical user keys
    and triggers typing the real code from code.txt."""
    global keyboard_listener, TYPING_MODE, ghost_typing_active, is_locked, suppressed_down_vks, shift_pressed

    if not keyboard_listener:
        return True

    raw_extra = getattr(data, 'dwExtraInfo', 0)
    extra = 0 if raw_extra is None else raw_extra
    vk    = getattr(data, 'vkCode', 0)

    # 1. Any synthetic keystroke generated by our assistant (tagged with MAGIC_EXTRA or VK_PACKET):
    # ALWAYS ALLOW! Hardware-level identification, completely thread-safe and immune to timing races.
    if extra == MAGIC_EXTRA or vk == 231:
        return True

    # 2. Modifiers must not be suppressed so hotkeys and shortcuts work normally
    # 0x10 = VK_SHIFT, 0xA0 = VK_LSHIFT, 0xA1 = VK_RSHIFT
    # 0x11 = VK_CONTROL, 0xA2 = VK_LCONTROL, 0xA3 = VK_RCONTROL
    # 0x12 = VK_MENU (Alt), 0xA4 = VK_LMENU, 0xA5 = VK_RMENU
    # 0x5B = VK_LWIN, 0x5C = VK_RWIN
    if vk in (0x10, 0xA0, 0xA1):
        if msg in (0x0100, 0x0104):
            shift_pressed = True
        elif msg in (0x0101, 0x0105):
            shift_pressed = False
        return True

    if vk in (0x11, 0xA2, 0xA3, 0x12, 0xA4, 0xA5, 0x5B, 0x5C):
        return True

    # 3. ASSISTANT HOTKEYS (Shift + Key):
    # Intercept and SUPPRESS so characters like 'P', 'R', 'C', 'Y', 'H' etc. NEVER type into editors!
    if is_shift_down() and vk in HOTKEY_VKS:
        if msg in (0x0100, 0x0104):  # WM_KEYDOWN, WM_SYSKEYDOWN
            suppressed_down_vks.add(vk)
            threading.Thread(target=dispatch_hotkey, args=(vk,), daemon=True).start()
        elif msg in (0x0101, 0x0105):
            suppressed_down_vks.discard(vk)
        if hasattr(keyboard_listener, 'suppress_event'):
            keyboard_listener.suppress_event()
        return False

    # Keyup for any previously suppressed key (prevents stray keyup leaks)
    if msg in (0x0101, 0x0105) and vk in suppressed_down_vks:
        suppressed_down_vks.discard(vk)
        if hasattr(keyboard_listener, 'suppress_event'):
            keyboard_listener.suppress_event()
        return False

    # 4. Emergency Esc stop: if typing is active and user taps Esc, pause typing instantly
    if vk == 0x1B:
        if ghost_typing_active:
            if msg in (0x0100, 0x0104):
                threading.Thread(target=toggle_ghost_typing, daemon=True).start()
            if hasattr(keyboard_listener, 'suppress_event'):
                keyboard_listener.suppress_event()
            return False
        return True

    # 5. If assistant is locked, or in Mode 1 (auto), or typing is not active:
    # let normal user typing pass to the OS
    if is_locked or TYPING_MODE != 2 or not ghost_typing_active:
        return True

    # Allow system combos (Ctrl+C, Ctrl+V, Alt+Tab) through without triggering typing
    if is_ctrl_down() or is_alt_down():
        return True

    # 6. Physical user keypress in Interactive Typing Mode (Mode 2)!
    # WM_KEYDOWN = 0x0100, WM_SYSKEYDOWN = 0x0104
    if msg in (0x0100, 0x0104):
        suppressed_down_vks.add(vk)
        interactive_typing_queue.put(1)
    elif msg in (0x0101, 0x0105):
        suppressed_down_vks.discard(vk)

    # Suppress physical keystroke from reaching the active window / operating system!
    if hasattr(keyboard_listener, 'suppress_event'):
        keyboard_listener.suppress_event()

    return False


def on_press(key, *args):
    # Ignore any keystrokes injected by ghost typing controller or self-typing
    global is_self_typing
    if is_self_typing or (args and args[0] is True):
        return

    # Emergency Esc stop: if user taps Esc while typing is active, instantly pause!
    if ghost_typing_active and key == keyboard.Key.esc:
        toggle_ghost_typing()
        return

    # Mode 2 fallback (non-Windows platforms where win32_event_filter is not active):
    if TYPING_MODE == 2 and ghost_typing_active and not is_locked and not is_shift_down():
        if sys.platform != "win32":
            if key not in (keyboard.Key.esc, keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
                           keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
                           keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
                           keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
                ctrl = keyboard.Controller()
                try:
                    ctrl.press(keyboard.Key.backspace)
                    ctrl.release(keyboard.Key.backspace)
                except Exception:
                    pass
                interactive_typing_queue.put(1)
                return

    global TYPING_SPEED_FACTOR
    with lock:
        try:
            current_keys.add(key)
            if is_shift_down():
                char = getattr(key, 'char', None)
                vk = getattr(key, 'vk', None)

                # Lock toggle: Shift + ? or Shift + /
                if char in ('?', '/') or vk == 191:
                    toggle_lock()
                    current_keys.discard(key)
                    return

                # If locked, block all other hotkeys
                if is_locked:
                    return

                # HUD Opacity Controls: Shift + [ (Down to 0% invisible), Shift + ] (Up)
                if char in ('[', '{') or vk == 219:
                    update_hud("opacity_down")
                    current_keys.discard(key)
                    return
                elif char in (']', '}') or vk == 221:
                    update_hud("opacity_up")
                    current_keys.discard(key)
                    return

                # HUD Resize Controls: Shift + =/+ (Enlarge), Shift + -/_ (Shrink)
                if char in ('=', '+') or vk in (187, 107):
                    update_hud("resize_grow")
                    current_keys.discard(key)
                    return
                elif char in ('-', '_') or vk in (189, 109):
                    update_hud("resize_shrink")
                    current_keys.discard(key)
                    return

                if key == keyboard.Key.up:
                    TYPING_SPEED_FACTOR = min(3.0, round(TYPING_SPEED_FACTOR + 0.25, 2))
                    print(f"\n[Speed] {TYPING_SPEED_FACTOR:.2f}x")
                    update_hud("speed", {"speed": TYPING_SPEED_FACTOR})
                    play_sound("Ping")
                    current_keys.discard(key)
                elif key == keyboard.Key.down:
                    TYPING_SPEED_FACTOR = max(0.25, round(TYPING_SPEED_FACTOR - 0.25, 2))
                    print(f"\n[Speed] {TYPING_SPEED_FACTOR:.2f}x")
                    update_hud("speed", {"speed": TYPING_SPEED_FACTOR})
                    play_sound("Pop")
                    current_keys.discard(key)
                else:
                    if char or vk:
                        ch = char.lower() if char else ""
                        if ch == 's' or vk == 83:
                            start_session(); current_keys.discard(key)
                        elif ch == 'd' or vk == 68:
                            quit_session(); current_keys.discard(key)
                        elif ch in ('y', 'h') or vk in (89, 72):
                            toggle_typing_mode(); current_keys.discard(key)
                        elif ch == 'p' or vk == 80:
                            toggle_ghost_typing(); current_keys.discard(key)
                        elif ch == 'r' or vk == 82:
                            reset_ghost_typing(); current_keys.discard(key)
                        elif ch == 'b' or vk == 66:
                            threading.Thread(target=handle_bug_report).start(); current_keys.discard(key)
                        elif ch == 'l' or vk == 76:
                            toggle_input_mode(); current_keys.discard(key)
                        elif ch == 'i' or vk == 73:
                            toggle_indent_mode(); current_keys.discard(key)
                        elif ch == 'c' or vk == 67:
                            threading.Thread(target=handle_coding).start(); current_keys.discard(key)
                        elif ch == 'm' or vk == 77:
                            threading.Thread(target=handle_mcq).start(); current_keys.discard(key)
                        elif ch == 'g' or vk == 71:
                            threading.Thread(target=handle_guided_prompt).start(); current_keys.discard(key)
                        elif ch == 'f' or vk == 70:
                            threading.Thread(target=handle_critique_prompt).start(); current_keys.discard(key)
                        elif ch == 'v' or vk == 86:
                            update_hud("toggle_visibility"); current_keys.discard(key)
                        elif ch == 't' or vk == 84:
                            update_hud("toggle_click_through"); current_keys.discard(key)
                        elif ch == 'o' or vk == 79:
                            update_hud("cycle_size"); current_keys.discard(key)
                        elif ch == 'k' or vk == 75:
                            update_hud("toggle_code_drawer"); current_keys.discard(key)
                        elif ch == 'n' or vk == 78:
                            update_hud("toggle_minimize"); current_keys.discard(key)
        except (AttributeError, KeyError):
            pass


def on_release(key, *args):
    global is_self_typing, shift_pressed
    if is_self_typing or (args and args[0] is True):
        return
    if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
        shift_pressed = False
    with lock:
        current_keys.discard(key)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Ensure terminal window is hidden immediately on Windows
    if sys.platform == "win32" and windll:
        try:
            _hcon = windll.kernel32.GetConsoleWindow()
            if _hcon:
                windll.user32.ShowWindow(_hcon, 0)  # SW_HIDE
        except Exception:
            pass

    hud_status_banner = (
        "[DISPLAY STATUS]\n"
        "  🪟 HUD is HIDDEN initially (Ultra-Stealth Mode).\n"
        "  👉 Press Right Shift + V to OPEN the Floating Glass HUD.\n"
        "  Once opened, all UI controls and mouse interactions are active."
        if ENABLE_HUD else
        "[DISPLAY STATUS]\n"
        "  🚫 Floating HUD UI is DISABLED (ENABLE_HUD = False)."
    )

    print(f"""
=============================================
   EXAM ASSISTANT LAUNCHED (WINDOWS)
=============================================
{hud_status_banner}

[MOUSE TRIGGERS — Right-Click]
  Bottom-Left  : 1x = Essay solution (saved to code.txt)
  Bottom-Right : 1x = Clear Clipboard & code.txt

[KEYBOARD]
  Right Shift + Y / H   : 🔄 Toggle Typing Mode (Mode 1 Auto ➔ Mode 2 Interactive Keypress)
                           • Mode 1: Auto Ghost Typing (cursor flies to Top-Left corner)
                           • Mode 2: Interactive Keypress / Hacker Typer (cursor flies to Top-Right corner)
  Right Shift + P       : ⌨️ Toggle Typing (Auto in Mode 1 | Arm/Pause in Mode 2)
  Right Shift + R       : ⏪ Reset / Rewind Typing to 0%
  Right Shift + ? / /   : 🔒 Lock / Unlock Toggle (Freeze tool)
  Right Shift + M       : 🎯 MCQ / AI Literacy (Moves mouse to option)
  Right Shift + C       : 💻 All Code (Direct DSA / Capgemini Debugging / SQL)
  Right Shift + G       : 🤖 Guided Interview (Initial Prompt OR Test Failure Fix)
  Right Shift + I       : 📐 Toggle Indent Mode (Smart vs Raw)
  Right Shift + L       : 👁️ Toggle OCR / Screenshot mode
  Right Shift + Up/Down : ⚡ Typing speed (Mode 1)
  Esc                   : ⏹️ Emergency Stop Typing

[PROVIDER]
  {PROVIDER['name']}
=============================================
""")
    play_sound("Submarine")
    print_status()

    mouse_listener = mouse.Listener(on_click=on_click)
    mouse_listener.start()

    # If Mode 2 is default, position cursor at Top-Right corner as indicator
    if TYPING_MODE == 2:
        tx, ty = SCREEN_WIDTH - 5, 5
        mouse_controller.position = (int(tx), int(ty))
        if windll:
            try:
                windll.user32.SetCursorPos(int(tx), int(ty))
            except Exception:
                pass

    if ENABLE_HUD:
        hud_thread = threading.Thread(target=launch_hud, daemon=True)
        hud_thread.start()

    listener_kwargs = {
        "on_press": on_press,
        "on_release": on_release,
    }
    if sys.platform == "win32":
        listener_kwargs["win32_event_filter"] = win32_filter

    keyboard_listener = keyboard.Listener(**listener_kwargs)
    with keyboard_listener as listener:
        listener.join()
