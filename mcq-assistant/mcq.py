#!/usr/bin/env python3
"""
MCQ Assistant — Terminal Edition
Press Shift+M to activate, then A/B/C/D to move cursor to screen corner.
  A → Top Left
  B → Top Right
  C → Bottom Left
  D → Bottom Right
Press Q to quit.
"""

import sys
import subprocess
import threading

try:
    from pynput import keyboard, mouse
except ImportError:
    print("Installing pynput...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pynput", "-q"])
    from pynput import keyboard, mouse


def get_screen_size():
    """Get screen resolution via AppleScript on macOS."""
    script = '''
    tell application "Finder"
        set _bounds to bounds of window of desktop
        set _width to item 3 of _bounds
        set _height to item 4 of _bounds
    end tell
    return (_width as text) & "," & (_height as text)
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        w, h = result.stdout.strip().split(",")
        return int(w), int(h)
    except Exception:
        # Fallback: use system_profiler
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                if "Resolution" in line:
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if p == "x" and i > 0 and i < len(parts) - 1:
                            return int(parts[i - 1]), int(parts[i + 1])
        except Exception:
            pass
        return 1920, 1080  # fallback


MARGIN = 5  # pixels from edge
screen_w, screen_h = get_screen_size()

CORNERS = {
    'a': (MARGIN, MARGIN),                          # Top Left
    'b': (screen_w - MARGIN, MARGIN),               # Top Right
    'c': (MARGIN, screen_h - MARGIN),               # Bottom Left
    'd': (screen_w - MARGIN, screen_h - MARGIN),    # Bottom Right
}

LABELS = {
    'a': '↖  Top Left',
    'b': '↗  Top Right',
    'c': '↙  Bottom Left',
    'd': '↘  Bottom Right',
}

COLORS = {
    'a': '\033[95m',  # Magenta
    'b': '\033[96m',  # Cyan
    'c': '\033[93m',  # Yellow
    'd': '\033[92m',  # Green
}

RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'

armed = False
mouse_ctrl = mouse.Controller()
shift_held = False


def move_cursor(option):
    x, y = CORNERS[option]
    mouse_ctrl.position = (x, y)


def print_status(msg):
    sys.stdout.write(f"\r\033[K  {msg}")
    sys.stdout.flush()


def print_banner():
    print(f"""
{BOLD}  ╔══════════════════════════════════════╗
  ║       MCQ ASSISTANT  (Terminal)      ║
  ╠══════════════════════════════════════╣
  ║  Shift+M  →  Arm answer mode        ║
  ║  A / B / C / D  →  Move to corner   ║
  ║  Q  →  Quit                         ║
  ╠══════════════════════════════════════╣
  ║  A = {COLORS['a']}↖ Top Left{RESET}{BOLD}     B = {COLORS['b']}↗ Top Right{RESET}{BOLD}  ║
  ║  C = {COLORS['c']}↙ Bottom Left{RESET}{BOLD}  D = {COLORS['d']}↘ Bottom Right{RESET}{BOLD} ║
  ╠══════════════════════════════════════╣
  ║  Screen: {screen_w}x{screen_h:<25s}║
  ╚══════════════════════════════════════╝{RESET}
""")
    print_status(f"{DIM}Waiting... Press Shift+M to arm{RESET}")


def on_press(key):
    global armed, shift_held

    try:
        if key == keyboard.Key.shift or key == keyboard.Key.shift_r:
            shift_held = True
            return

        k = None
        if hasattr(key, 'char') and key.char:
            k = key.char.lower()
        elif hasattr(key, 'vk'):
            # Handle Shift+M producing 'M' (uppercase)
            pass

        if k == 'm' and shift_held:
            armed = True
            print_status(f"{BOLD}\033[93m⚡ ARMED — press A / B / C / D{RESET}")
            return

        if k == 'q':
            print_status(f"{BOLD}\033[91m✖  Quitting...{RESET}\n")
            return False  # Stop listener

        if armed and k in CORNERS:
            move_cursor(k)
            color = COLORS[k]
            label = LABELS[k]
            print_status(f"{BOLD}{color}✔  Answer {k.upper()} → {label}{RESET}   {DIM}(Shift+M to arm again){RESET}")
            armed = False

    except Exception:
        pass


def on_release(key):
    global shift_held
    if key == keyboard.Key.shift or key == keyboard.Key.shift_r:
        shift_held = False


def main():
    print_banner()
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
    print()


if __name__ == "__main__":
    main()
