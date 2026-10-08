#!/usr/bin/env python3
"""
Auto Typer — types your clipboard content keystroke by keystroke.
Handles online code editors (autocomplete popups, bracket insertion, etc.)

Usage:
    python auto_typer.py [OPTIONS]

Controls:
    Shift+A   → Start typing
    Shift+P   → Pause / Resume
    Shift+S   → Stop entirely

Options:
    --delay FLOAT     Delay between keystrokes in seconds (default: 0.05)
    --newline TEXT    'press' (Enter key) | 'skip' (ignore) | 'space' (default: press)
    --escape          Press Escape before each word to dismiss autocomplete popups
                      (recommended for online code editors like CipherSchools, LeetCode)
    --word-delay F    Extra delay between words when --escape is used (default: 0.05)

Requirements:
    pip install pyautogui pyperclip pynput

Examples:
    python auto_typer.py                          # basic usage
    python auto_typer.py --escape                 # for online code editors
    python auto_typer.py --escape --delay 0.07    # slower, more reliable
    python auto_typer.py --delay 0.1              # slow typing without escape

Note:
    On Linux/Mac run with sudo:  sudo python auto_typer.py
"""

import argparse
import sys
import time
import threading

try:
    import pyautogui
except ImportError:
    print("Missing dependency: pyautogui")
    print("Install it with:  pip install pyautogui")
    sys.exit(1)

try:
    import pyperclip
except ImportError:
    print("Missing dependency: pyperclip")
    print("Install it with:  pip install pyperclip")
    sys.exit(1)

try:
    from pynput import keyboard
except ImportError:
    print("Missing dependency: pynput")
    print("Install it with:  pip install pynput")
    sys.exit(1)


# ── Shared state ──────────────────────────────────────────────────────────────
state = {
    "active":  False,
    "paused":  False,
    "stopped": False,
}
state_lock = threading.Lock()


def on_start():
    with state_lock:
        if not state["stopped"] and not state["active"]:
            state["active"] = True
            print("\n▶  Typing started!  (Shift+P = pause  |  Shift+S = stop)")


def on_pause():
    with state_lock:
        if state["active"] and not state["stopped"]:
            state["paused"] = not state["paused"]
            label = "⏸  Paused" if state["paused"] else "▶  Resumed"
            print(f"\n{label}")


def on_stop():
    with state_lock:
        state["stopped"] = True
        print("\n⏹  Stopped by user.")


def register_hotkeys():
    listener = keyboard.GlobalHotKeys({
        '<shift>+a': on_start,
        '<shift>+A': on_start,
        '<shift>+p': on_pause,
        '<shift>+P': on_pause,
        '<shift>+s': on_stop,
        '<shift>+S': on_stop,
    })
    listener.start()
    # Keep a reference to prevent garbage collection if necessary
    global _listener
    _listener = listener


# ── Argument parsing ──────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="Type clipboard content automatically, character by character."
    )
    parser.add_argument(
        "--delay", type=float, default=0.05, metavar="FLOAT",
        help="Delay between keystrokes in seconds (default: 0.05)",
    )
    parser.add_argument(
        "--newline", choices=["press", "skip", "space"], default="press",
        help="Newline handling: press=Enter, skip=ignore, space=replace (default: press)",
    )
    parser.add_argument(
        "--escape", action="store_true",
        help="Press Escape before each word to dismiss autocomplete (for code editors)",
    )
    parser.add_argument(
        "--word-delay", type=float, default=0.05, metavar="FLOAT",
        help="Extra pause between words when --escape is used (default: 0.05)",
    )
    return parser.parse_args()


# ── Helpers ───────────────────────────────────────────────────────────────────
def check_stopped():
    with state_lock:
        return state["stopped"]


def wait_if_paused():
    """Spin-wait while paused. Returns True if stopped during pause."""
    while True:
        with state_lock:
            if state["stopped"]:
                return True
            if not state["paused"]:
                return False
        time.sleep(0.1)


def type_char(char: str):
    """Type a single character, falling back to clipboard paste for unicode."""
    try:
        pyautogui.write(char, interval=0)
    except Exception:
        pyperclip.copy(char)
        pyautogui.hotkey("ctrl", "v")


# ── Core typer ────────────────────────────────────────────────────────────────
def type_text(text: str, delay: float, newline_mode: str,
              use_escape: bool, word_delay: float):
    total = len(text)
    typed = 0
    pyautogui.PAUSE = 0

    # Split into tokens: words and non-word separators
    # We type word-by-word (with Escape before each word) when --escape is on
    i = 0
    while i < len(text):
        if check_stopped():
            break
        if wait_if_paused():
            break

        char = text[i]

        # ── Newline ──
        if char == "\n":
            if newline_mode == "press":
                pyautogui.press("enter")
            elif newline_mode == "space":
                pyautogui.write(" ", interval=0)
            typed += 1
            i += 1
            time.sleep(delay)

        # ── Tab ──
        elif char == "\t":
            pyautogui.press("tab")
            typed += 1
            i += 1
            time.sleep(delay)

        # ── Word (sequence of non-whitespace chars) ──
        elif use_escape and char not in (" ", "\n", "\t"):
            # Collect the full word
            j = i
            while j < len(text) and text[j] not in (" ", "\n", "\t"):
                j += 1
            word = text[i:j]

            # Press Escape to dismiss any autocomplete popup
            pyautogui.press("escape")
            time.sleep(0.03)

            # Type word character by character
            for wchar in word:
                if check_stopped():
                    break
                if wait_if_paused():
                    break
                type_char(wchar)
                typed += 1
                time.sleep(delay)

            i = j
            time.sleep(word_delay)  # small pause after word

        # ── Space or regular char (no escape mode) ──
        else:
            type_char(char)
            typed += 1
            i += 1
            time.sleep(delay)

        # Progress bar every 100 chars
        if typed % 100 == 0 or typed == total:
            pct = typed / total * 100
            bar = "#" * int(pct // 5) + "-" * (20 - int(pct // 5))
            print(f"  [{bar}] {pct:5.1f}%  ({typed}/{total})", end="\r", flush=True)

    print(f"\n\n✓ Done — typed {typed} of {total} characters.")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    args = parse_args()

    try:
        text = pyperclip.paste()
    except pyperclip.PyperclipException as e:
        print(f"Clipboard error: {e}")
        sys.exit(1)

    if not text:
        print("Clipboard is empty. Copy some text first, then run the script.")
        sys.exit(1)

    preview = text[:120].replace("\n", "↵")
    print(f"\n{'─'*52}")
    print(f"  Clipboard content ({len(text)} chars)")
    print(f"  Preview : {preview}{'…' if len(text) > 120 else ''}")
    print(f"{'─'*52}")
    print(f"  Keystroke delay  : {args.delay}s")
    print(f"  Newline mode     : {args.newline}")
    print(f"  Escape mode      : {'ON ✓ (dismisses autocomplete)' if args.escape else 'OFF'}")
    if args.escape:
        print(f"  Word delay       : {args.word_delay}s")
    print(f"{'─'*52}")
    print(f"\n  Shift+A  →  Start typing")
    print(f"  Shift+P  →  Pause / Resume")
    print(f"  Shift+S  →  Stop entirely")
    print(f"\nWaiting for Shift+A …")

    register_hotkeys()

    while True:
        with state_lock:
            if state["active"] or state["stopped"]:
                break
        time.sleep(0.05)

    with state_lock:
        if state["stopped"]:
            sys.exit(0)

    try:
        type_text(text, args.delay, args.newline, args.escape, args.word_delay)
    except KeyboardInterrupt:
        print("\n\n⚠  Aborted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
