#!/usr/bin/env python3
"""
Shift+M → screenshot → NVIDIA NIM vision → speak the MCQ answer.
NIM_API_KEY is imported directly from assistant.py.
"""

import base64
import platform
import re
import requests
import subprocess
import tempfile
import threading
import urllib3
from pathlib import Path

from PIL import ImageGrab
from pynput import keyboard, mouse

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def _load_key(var: str) -> str:
    src = Path(__file__).parent / "assistant.py"
    match = re.search(rf'{var}\s*=\s*"([^"]+)"', src.read_text())
    return match.group(1) if match else ""

NIM_API_KEY    = _load_key("NIM_API_KEY")
GROQ_API_KEY   = _load_key("GROQ_API_KEY")
GEMINI_API_KEY = _load_key("GEMINI_API_KEY")

# ── Screen size & mouse controller ──────────────────────────────
try:
    if platform.system() == "Windows":
        import ctypes
        SCREEN_W = ctypes.windll.user32.GetSystemMetrics(0)
        SCREEN_H = ctypes.windll.user32.GetSystemMetrics(1)
    else:
        import tkinter as tk
        _root = tk.Tk(); _root.withdraw()
        SCREEN_W = _root.winfo_screenwidth()
        SCREEN_H = _root.winfo_screenheight()
        _root.destroy()
except Exception:
    SCREEN_W, SCREEN_H = 1440, 900

_mouse = mouse.Controller()
MARGIN = 5  # pixels from edge

CORNER_MAP = {
    "A": (MARGIN, MARGIN),                     # Top Left
    "B": (SCREEN_W - MARGIN, MARGIN),           # Top Right
    "C": (MARGIN, SCREEN_H - MARGIN),           # Bottom Left
    "D": (SCREEN_W - MARGIN, SCREEN_H - MARGIN),# Bottom Right
}

CORNER_LABEL = {
    "A": "↖ Top-Left",
    "B": "↗ Top-Right",
    "C": "↙ Bottom-Left",
    "D": "↘ Bottom-Right",
}


def move_to_corner(letter: str) -> None:
    """Move the mouse cursor to the screen corner for the given answer."""
    letter = letter.upper()
    if letter in CORNER_MAP:
        x, y = CORNER_MAP[letter]
        _mouse.position = (x, y)
        print(f"[screenshot_mcq] 🖱  Cursor → {CORNER_LABEL[letter]}  ({x}, {y})")
    else:
        print(f"[screenshot_mcq] Unknown option '{letter}', cursor not moved.")

# Primary: Gemini — reliable, fast, good vision
GEMINI_MODEL = "gemini-2.0-flash"

# Fallback 1: NIM
NIM_URL   = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_MODEL = "meta/llama-3.2-11b-vision-instruct"

# Fallback 2: Groq
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.6-27b"

SYSTEM_PROMPT = (
    "Look at the screenshot. There is a multiple-choice question. "
    "Determine the correct answer. Reply with ONLY the single letter: A, B, C, or D. "
    "Nothing else. No explanation. No punctuation. Just the letter."
)

_current_keys: set = set()
_lock = threading.Lock()
_running = False  # prevents overlapping calls

MAX_IMG_DIM = 1024  # downscale screenshots to reduce payload


def capture_screenshot() -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    img = ImageGrab.grab()
    # Downscale to reduce base64 size and API load
    img = img.convert("RGB")
    img.thumbnail((MAX_IMG_DIM, MAX_IMG_DIM))
    img.save(tmp.name, "JPEG", quality=70)
    return tmp.name


def image_to_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode()


def _call(url: str, api_key: str, model: str, b64: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is the correct answer?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            },
        ],
        "max_tokens": 5,
        "temperature": 0.0,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    import time as _time
    for attempt in range(3):
        session = requests.Session()
        try:
            r = session.post(url, headers=headers, json=payload, timeout=30, verify=False)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.HTTPError:
            if r.status_code in (502, 503, 429) and attempt < 2:
                wait = (attempt + 1) * 2
                print(f"[screenshot_mcq] Server busy ({r.status_code}), retrying in {wait}s...")
                _time.sleep(wait)
                continue
            raise
        finally:
            session.close()
    raise RuntimeError("All retries failed")


def _call_gemini(b64: str) -> str:
    """Call Gemini API (different format from OpenAI-compatible APIs)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{
            "parts": [
                {"text": SYSTEM_PROMPT + "\nWhat is the correct answer?"},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
            ]
        }],
        "generationConfig": {"maxOutputTokens": 5, "temperature": 0.0},
    }
    import time as _time
    for attempt in range(3):
        session = requests.Session()
        try:
            r = session.post(url, json=payload, timeout=30)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except requests.exceptions.HTTPError:
            if r.status_code in (502, 503, 429) and attempt < 2:
                wait = (attempt + 1) * 2
                print(f"[screenshot_mcq] Gemini busy ({r.status_code}), retrying in {wait}s...")
                _time.sleep(wait)
                continue
            raise
        finally:
            session.close()
    raise RuntimeError("Gemini retries failed")


def ask_llm(image_path: str) -> str:
    b64 = image_to_b64(image_path)
    # Try Gemini first (most reliable), then NIM, then Groq
    if GEMINI_API_KEY:
        try:
            print("[screenshot_mcq] Trying Gemini...")
            return _call_gemini(b64)
        except Exception as e:
            print(f"[screenshot_mcq] Gemini failed: {e}")
    if NIM_API_KEY:
        try:
            print("[screenshot_mcq] Trying NIM...")
            return _call(NIM_URL, NIM_API_KEY, NIM_MODEL, b64)
        except Exception as e:
            print(f"[screenshot_mcq] NIM failed: {e}")
    if GROQ_API_KEY:
        try:
            print("[screenshot_mcq] Trying Groq...")
            return _call(GROQ_URL, GROQ_API_KEY, GROQ_MODEL, b64)
        except Exception as e:
            print(f"[screenshot_mcq] Groq failed: {e}")
    return "No working API."


def extract_letter(response: str) -> str | None:
    """Pull A/B/C/D from any response format — strict to loose."""
    text = response.strip().upper()
    # Best case: response is just the letter
    if text in ("A", "B", "C", "D"):
        return text
    # "Answer: B" or "Answer: B)" etc.
    m = re.search(r"ANSWER[:\s]*([A-D])", text)
    if m:
        return m.group(1)
    # Find first standalone A/B/C/D
    m = re.search(r"\b([A-D])\b", text)
    if m:
        return m.group(1)
    return None


def speak(text: str) -> None:
    subprocess.run(["say", text], check=False)


def handle_hotkey() -> None:
    global _running
    with _lock:
        if _running:
            return
        _running = True

    try:
        print("[screenshot_mcq] Hotkey triggered — capturing screen...")
        path = capture_screenshot()
        print(f"[screenshot_mcq] Screenshot saved to {path}")

        raw = ask_llm(path)
        print(f"[screenshot_mcq] Raw response: {raw}")

        letter = extract_letter(raw)
        if letter:
            move_to_corner(letter)
            speak(letter)
        else:
            print(f"[screenshot_mcq] Could not extract answer from: {raw}")
            speak("Could not determine the answer")
    except Exception as e:
        print(f"[screenshot_mcq] ERROR: {e}")
        speak(f"Error: {e}")
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass
        with _lock:
            _running = False


def on_press(key) -> None:
    _current_keys.add(key)
    shift_held = (
        keyboard.Key.shift in _current_keys
        or keyboard.Key.shift_l in _current_keys
        or keyboard.Key.shift_r in _current_keys
    )
    try:
        char = key.char
    except AttributeError:
        char = None

    if shift_held and char and char.lower() == "m":
        threading.Thread(target=handle_hotkey, daemon=True).start()


def on_release(key) -> None:
    _current_keys.discard(key)


def main() -> None:
    print(
        f"[screenshot_mcq] Listening for Shift+M\n"
        f"  Primary : Gemini {GEMINI_MODEL}\n"
        f"  Fallback: NIM {NIM_MODEL} → Groq {GROQ_MODEL}\n"
        f"  Screen  : {SCREEN_W}x{SCREEN_H}\n"
        f"  A=↖ Top-Left  B=↗ Top-Right  C=↙ Bottom-Left  D=↘ Bottom-Right\n"
        f"  Press Ctrl+C to quit."
    )

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


if __name__ == "__main__":
    main()
