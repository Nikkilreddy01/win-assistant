# ==============================================================================
# KALI LINUX SETUP INSTRUCTIONS:
# 1. sudo apt update && sudo apt install python3-pip python3-tk scrot xclip tesseract-ocr
# 2. pip install pynput pyperclip requests Pillow pytesseract
# NOTE: Kali uses X11 (XFCE) by default, so global hotkeys and screenshots work natively!
# ==============================================================================

import os
import time
import json
from datetime import date
import base64
import subprocess
import threading
import pyperclip
import pytesseract
from pynput import keyboard, mouse
from PIL import ImageGrab
import requests
api_session = requests.Session()
from io import BytesIO
import random
import platform

# Initial Screen Bounds (must run on main thread)
try:
    if platform.system() == "Windows":
        import ctypes
        SCREEN_WIDTH = ctypes.windll.user32.GetSystemMetrics(0)
        SCREEN_HEIGHT = ctypes.windll.user32.GetSystemMetrics(1)
    else:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        SCREEN_WIDTH = root.winfo_screenwidth()
        SCREEN_HEIGHT = root.winfo_screenheight()
        root.destroy()
except Exception:
    SCREEN_WIDTH, SCREEN_HEIGHT = 1440, 900

mouse_controller = mouse.Controller()

_DEFAULT_KEY = base64.b64decode("QVEuQWI4Uk42TEJWd0lqREVBSUdURHZXYk9DX29wcWdGeXh6R21naXd2M1BfWFhDSmhCOWc=").decode()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", _DEFAULT_KEY)

# ─── PROVIDER ROTATION LIST ───────────────────────────────────────────────────
# All are vision-capable. Tool tries top-to-bottom, auto-rotates on any failure.
PROVIDERS = [
    {
        "name":    "Gemini 3.7 Flash (Vertex AI)",
        "type":    "gemini",
        "key":     GEMINI_API_KEY,
        "url":     "https://aiplatform.googleapis.com/v1beta1/projects/934443841297/locations/global/publishers/google/models/gemini-3.7-flash:generateContent",
        "timeout": 60,
    },
]

current_provider_idx = 0


def first_gemini_provider_idx():
    for idx, provider in enumerate(PROVIDERS):
        if provider.get('type') == 'gemini':
            return idx
    return 0

# ─── OPTIONS ──────────────────────────────────────────────────────────────────
TYPING_SPEED_FACTOR = 1.5
TRIGGER_MARGIN      = 150
INPUT_MODE          = 0       # 0 = Screenshot | 1 = OCR (Tesseract) | 2 = Accessibility
INPUT_MODE_NAMES    = ["Screenshot", "OCR (Tesseract)", "Accessibility"]
INDENT_MODE         = 0       # 0 = Auto-Indent (OneCompiler/LeetCode) | 1 = Exact-Indent (CodeChef/Plain IDEs)
INDENT_MODE_NAMES   = ["Auto-Indent (OneCompiler/LeetCode)", "Exact-Indent (CodeChef/Plain IDEs)"]
ONE_INCH_PX         = 96      # 1 inch at 96 DPI — mouse answer offset from corners

def toggle_indent_mode():
    global INDENT_MODE
    INDENT_MODE = (INDENT_MODE + 1) % len(INDENT_MODE_NAMES)
    play_sound("Hero")
    print(f"\n>> Indent Mode switched to: {INDENT_MODE_NAMES[INDENT_MODE]}")
    print_status()

# ─── STATE ────────────────────────────────────────────────────────────────────
ghost_typing_active   = False
ghost_typing_thread   = None
ghost_typing_reset_flag = False

explanation_typing_active   = False
explanation_typing_thread   = None
explanation_typing_reset_flag = False
ghost_typing_offset = 0
explanation_typing_offset = 0
ghost_typing_offset = 0
explanation_typing_offset = 0
ghost_typing_content = ""
explanation_typing_content = ""

state_lock            = threading.Lock()
session_active       = True
session_history      = []   # OpenAI format — universal across all providers

# ─── RATE LIMIT TRACKING ──────────────────────────────────────────────────────
# Tracks which provider indices are RPD-exhausted (daily limit hit)
rpd_exhausted       = {}    # {provider_idx: date_string} — keys exhausted for the day

def is_provider_exhausted(idx):
    """Check if a provider's daily limit is hit. Auto-resets on a new day."""
    if idx in rpd_exhausted:
        if rpd_exhausted[idx] == str(date.today()):
            return True
        else:
            del rpd_exhausted[idx]  # New day, reset
    return False

def mark_provider_exhausted(idx, name):
    """Mark a provider as RPD-exhausted for today."""
    rpd_exhausted[idx] = str(date.today())
    print(f"\n⛔ [{name}] Daily limit (RPD) hit — disabled until tomorrow.")

def parse_429_error(response):
    """Parse Gemini 429 response to determine if it's RPM or RPD."""
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



latest_mcq_req_id   = 0
latest_code_req_id  = 0
latest_essay_req_id = 0
req_lock = threading.Lock()

mcq_count   = 0
code_count  = 0
essay_count = 0


# ─── SOUND ────────────────────────────────────────────────────────────────────

def play_sound(sound_name):
    if platform.system() == "Windows":
        import winsound
        sound_map = {
            "Pop": "SystemDefault", "Hero": "SystemAsterisk", "Ping": "SystemAsterisk",
            "Purr": "SystemDefault", "Basso": "SystemHand",   "Glass": "SystemExclamation",
            "Tink": "SystemExit",   "Submarine": "SystemQuestion"
        }
        try:
            winsound.PlaySound(sound_map.get(sound_name, "SystemDefault"),
                               winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass
    elif platform.system() == "Darwin":
        os.system(f'afplay "/System/Library/Sounds/{sound_name}.aiff" &')
    else:
        # Linux fallback (Kali) to avoid afplay crashes
        print("\a", end="", flush=True)


# ─── STATUS DISPLAY ───────────────────────────────────────────────────────────

def print_status():
    provider = PROVIDERS[current_provider_idx]['name']
    mode     = INPUT_MODE_NAMES[INPUT_MODE]
    indent   = INDENT_MODE_NAMES[INDENT_MODE]
    session  = "ON" if session_active else "OFF"
    print(f"\n┌─────────────────────────────────────────┐")
    print(f"│  Provider : {provider:<29}│")
    print(f"│  Mode     : {mode:<29}│")
    print(f"│  Indent   : {indent:<29}│")
    print(f"│  Session  : {session:<29}│")
    print(f"│  Solved   : MCQ={mcq_count}  Code={code_count}  Essay={essay_count:<10}│")
    print(f"└─────────────────────────────────────────┘")


# ─── UNIFIED AI CALLER ────────────────────────────────────────────────────────

def _img_to_base64(img):
    img.thumbnail((1920, 1920))
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _call_gemini(provider, prompt, img_b64):
    """Calls Gemini REST API (its own format)."""
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

    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    key = provider['key']
    # Pass the API key using x-goog-api-key header (works for both AIza and AQ. key formats)
    url = provider['url']
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": key
    }

    r = api_session.post(url, headers=headers,
                      json=payload, verify=False, timeout=provider["timeout"])
    r.raise_for_status()
    return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()


def _call_openai(provider, prompt, img_b64, system_prompt=None):
    """Calls any OpenAI-compatible API (NIM, Groq, etc.)."""
    if img_b64:
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
        ]
    else:
        content = prompt

    current_msg = {"role": "user", "content": content}

    if session_active and session_history:
        messages = list(session_history) + [current_msg]
    else:
        messages = [current_msg]

    if system_prompt:
        messages = [{"role": "system", "content": system_prompt}] + messages

    payload = {"model": provider["model"], "messages": messages, "max_tokens": 2048}
    headers = {"Authorization": f"Bearer {provider['key']}", "Content-Type": "application/json"}

    r = api_session.post(provider["url"], headers=headers, json=payload, timeout=provider["timeout"])
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content'].strip()


def extract_mcq_letter(text):
    """Pulls out just A/B/C/D from a response even if the model over-explains."""
    import re
    text = text.strip()
    # First character is the answer (e.g. "A", "A.", "A)")
    if text and text[0].upper() in "ABCD":
        return text[0].upper()
    # Look for "answer is X" or "option X" or standalone letter
    match = re.search(r'\b(?:answer(?:\s+is)?|option)\s*[:\-]?\s*([ABCD])\b', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    # Last resort: find any standalone A/B/C/D
    match = re.search(r'\b([ABCD])\b', text)
    if match:
        return match.group(1).upper()
    return text


def call_ai(prompt, img=None, system_prompt=None, provider_types=None):
    """
    Unified entry point. Converts screenshot to base64 once, then tries each
    provider in order. On HTTP error or timeout, rotates to the next provider
    automatically. Saves successful provider as the new starting point.
    """
    global current_provider_idx, session_history

    img_b64 = _img_to_base64(img) if img else None
    if provider_types is None:
        candidate_indices = list(range(len(PROVIDERS)))
    else:
        allowed_types = set(provider_types)
        candidate_indices = [
            idx for idx, provider in enumerate(PROVIDERS)
            if provider.get('type') in allowed_types
        ]

    if not candidate_indices:
        print(">> No providers available for the current mode.")
        return "Error"

    if current_provider_idx not in candidate_indices:
        current_provider_idx = candidate_indices[0]

    skipped = 0
    for attempt in range(len(candidate_indices)):
        idx = candidate_indices[(candidate_indices.index(current_provider_idx) + attempt) % len(candidate_indices)]
        p   = PROVIDERS[idx]

        # Skip providers that hit their daily limit
        if is_provider_exhausted(idx):
            print(f">> [{p['name']}] ⛔ RPD exhausted — skipping...")
            skipped += 1
            continue

        print(f">> [{p['name']}] processing...")

        try:
            if p["type"] == "gemini":
                result = _call_gemini(p, prompt, img_b64)
            else:
                result = _call_openai(p, prompt, img_b64, system_prompt)

            # Persist successful provider so next call starts here
            if p['type'] == 'gemini':
                current_provider_idx = idx
            else:
                current_provider_idx = first_gemini_provider_idx()
            actual_failures = attempt - skipped
            if actual_failures > 0:
                print(f">> Switched to [{p['name']}] after {actual_failures} failure(s).")

            # Append to session (text only — no images in history)
            if session_active:
                session_history.append({"role": "user",      "content": prompt})
                session_history.append({"role": "assistant", "content": result})

            return result

        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            # Smart 429 handling — detect RPM vs RPD
            if code == 429 and e.response is not None:
                limit_type = parse_429_error(e.response)
                if limit_type == "RPD":
                    mark_provider_exhausted(idx, p['name'])
                    print(f">> [{p['name']}] HTTP 429 (daily limit) — skipping...")
                elif limit_type == "RPM":
                    print(f">> [{p['name']}] HTTP 429 (per-minute limit) — rotating...")
                else:
                    print(f">> [{p['name']}] HTTP 429 (unknown limit) — rotating...")
            elif code == 503 and e.response is not None:
                try:
                    err_msg = e.response.json().get("error", {}).get("message", "")
                    print(f">> [{p['name']}] HTTP 503 (Service Unavailable): {err_msg} — pausing for 2s, then rotating...")
                except Exception:
                    print(f">> [{p['name']}] HTTP 503 — pausing for 2s, then rotating...")
                import time
                time.sleep(2)
            else:
                print(f">> [{p['name']}] HTTP {code} — rotating...")
        except requests.exceptions.RequestException as e:
            print(f">> [{p['name']}] error: {e} — rotating...")
        except (KeyError, IndexError) as e:
            print(f">> [{p['name']}] bad response: {e} — rotating...")

    print(">> All providers exhausted. No answer.")
    return "Error"


# ─── TEXT EXTRACTION ──────────────────────────────────────────────────────

def extract_text_ocr(img):
    return pytesseract.image_to_string(img).strip()


def extract_text_accessibility():
    """Extract text from the focused window using macOS Accessibility API via AppleScript."""
    script = '''
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        tell frontApp
            set allText to ""
            tell front window
                set uiElements to entire contents
                repeat with elem in uiElements
                    try
                        set elemValue to value of elem
                        if elemValue is not missing value and elemValue is not "" then
                            set allText to allText & elemValue & linefeed
                        end if
                    end try
                    try
                        set elemName to name of elem
                        if elemName is not missing value and elemName is not "" then
                            set allText to allText & elemName & linefeed
                        end if
                    end try
                end repeat
            end tell
        end tell
        return allText
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', script],
                                capture_output=True, text=True, timeout=15)
        text = result.stdout.strip()
        if not text and result.stderr:
            print(f"[Accessibility] Error: {result.stderr.strip()}")
        return text
    except subprocess.TimeoutExpired:
        print("[Accessibility] Timed out reading UI elements.")
        return ""
    except Exception as e:
        print(f"[Accessibility] Error: {e}")
        return ""


def toggle_input_mode():
    global INPUT_MODE
    INPUT_MODE = (INPUT_MODE + 1) % len(INPUT_MODE_NAMES)
    play_sound("Glass")
    print(f"\n>> Mode switched to: {INPUT_MODE_NAMES[INPUT_MODE]}")
    print_status()


# ─── TASK HANDLERS ────────────────────────────────────────────────────────────

def point_mouse_to_option(option_text):
    margin = ONE_INCH_PX
    opt = option_text.strip().lower()
    if   opt.startswith('a') or 'option a' in opt: x, y = margin, margin
    elif opt.startswith('b') or 'option b' in opt: x, y = SCREEN_WIDTH - margin, margin
    elif opt.startswith('c') or 'option c' in opt: x, y = margin, SCREEN_HEIGHT - margin
    elif opt.startswith('d') or 'option d' in opt: x, y = SCREEN_WIDTH - margin, SCREEN_HEIGHT - margin
    else:                                            x, y = margin, margin

    if platform.system() == "Windows":
        import ctypes
        ctypes.windll.user32.SetCursorPos(int(x), int(y))
    else:
        mouse_controller.position = (x, y)
    play_sound("Hero")


def handle_mcq():
    global latest_mcq_req_id
    with req_lock:
        latest_mcq_req_id += 1
        req_id = latest_mcq_req_id

    print(f"\nAction: MCQ [Req {req_id}]...")
    play_sound("Submarine")

    system_prompt = "You output ONLY a single letter: A, B, C, or D. No explanation. No punctuation. Nothing else."
    if INPUT_MODE == 1:  # OCR
        img = ImageGrab.grab()
        text = extract_text_ocr(img)
        print(f"[OCR] Extracted {len(text)} chars.")
        prompt = f"Below is exam screen text:\n\n{text}\n\nIdentify the top-most MCQ and reply with ONLY the correct letter: A, B, C, or D."
        answer = call_ai(prompt, None, system_prompt, provider_types=["gemini", "openai"])
    elif INPUT_MODE == 2:  # Accessibility
        text = extract_text_accessibility()
        print(f"[Accessibility] Extracted {len(text)} chars.")
        if not text:
            print("[Accessibility] No text found. Falling back to screenshot.")
            img = ImageGrab.grab()
            prompt = (
                "Identify the top-most multiple-choice question in the image and solve it. "
                "Reply with ONLY the correct option letter: A, B, C, or D."
            )
            answer = call_ai(prompt, img, system_prompt, provider_types=["gemini"])
        else:
            prompt = f"Below is exam screen text:\n\n{text}\n\nIdentify the top-most MCQ and reply with ONLY the correct letter: A, B, C, or D."
            answer = call_ai(prompt, None, system_prompt, provider_types=["gemini"])
    else:  # Screenshot
        img = ImageGrab.grab()
        prompt = (
            "Identify the top-most multiple-choice question in the image and solve it. "
            "Reply with ONLY the correct option letter: A, B, C, or D."
        )
        answer = call_ai(prompt, img, system_prompt, provider_types=["gemini", "openai"])

    with req_lock:
        if req_id != latest_mcq_req_id:
            return

    if answer != "Error":
        answer = extract_mcq_letter(answer)

    print(f"\n{'='*40}\nMCQ ANSWER [Req {req_id}]: {answer}\n{'='*40}\n")
    if answer != "Error":
        global mcq_count
        mcq_count += 1
        point_mouse_to_option(answer.lower())
def clean_human_explanation(text):
    if not text or text == "Error":
        return text
    import re
    # Remove LaTeX wrappers \( ... \), \[ ... \], $ ... $
    text = re.sub(r'\\\((.*?)\\\)', r'\1', text)
    text = re.sub(r'\\\[(.*?)\\\]', r'\1', text)
    text = re.sub(r'\$(.*?)\$', r'\1', text)
    
    # Remove LaTeX formatting tags & functions
    text = re.sub(r'\\mathcal\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\text\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\mathrm\{([^}]+)\}', r'\1', text)
    text = re.sub(r'\\log', 'log', text)
    text = re.sub(r'\\O', 'O', text)
    
    # Strip any stray backslashes, asterisks for bolding, and backticks
    text = text.replace('\\', '')
    text = text.replace('**', '').replace('__', '').replace('*', '')
    text = text.replace('`', '')
    
    return text.strip()


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
    
    with open("lang.txt", "w", encoding="utf-8") as f:
        f.write(lang)
        
    cleaned_code = '\n'.join(lines).strip()
    return cleaned_code


def handle_coding():
    global latest_code_req_id, session_history
    with req_lock:
        latest_code_req_id += 1
        req_id = latest_code_req_id

    # Clear session history for each new coding/SQL request so past question context never bleeds into new problems!
    session_history = []

    print(f"\nAction: Coding / SQL Query [Req {req_id}]...")
    play_sound("Pop")

    common_instructions = (
        "STEP 1 — IDENTIFY PROBLEM TYPE ON THIS SCREEN:\n"
        "- Is this an SQL database query problem (e.g. table schemas, SELECT, JOIN, GROUP BY, SQL editor)?\n"
        "- OR is this a standard programming algorithm problem (e.g. C++, Python, Java, C#, JS)?\n\n"
        "STEP 2 — SOLVE STRICTLY BASED ON TYPE:\n"
        "- IF SQL PROBLEM: Write ONLY the complete, valid SQL query. Do NOT write any C++, Java, or Python code.\n"
        "- IF PROGRAMMING PROBLEM: Look at the language selector / template code (e.g. C++, Python, Java). Write the solution in THAT EXACT LANGUAGE (default to C++ if C++ template/includes are shown). Do NOT write SQL.\n\n"
        "RULES:\n"
        "1. ABSOLUTELY NO COMMENTS (no #, no //, no /* */, no --).\n"
        "2. If C++, include `using namespace std;`.\n"
        "3. FOR NON-PYTHON LANGUAGES (C++, Java, C#, SQL, JS, etc.): Write lines WITHOUT leading indentation (start at column 1) so web IDE auto-indentation works cleanly without double-padding.\n"
        "4. Return ONLY raw code or SQL query — NO markdown fences, NO explanatory text."
    )

    if INPUT_MODE == 1:  # OCR
        img = ImageGrab.grab()
        text = extract_text_ocr(img)
        print(f"[OCR] Extracted {len(text)} chars.")
        prompt = f"Below is a problem extracted from an exam screen:\n\n{text}\n\n{common_instructions}"
        code = call_ai(prompt, None, provider_types=["gemini"])
    elif INPUT_MODE == 2:  # Accessibility
        text = extract_text_accessibility()
        print(f"[Accessibility] Extracted {len(text)} chars.")
        if not text:
            print("[Accessibility] No text found. Falling back to screenshot.")
            img = ImageGrab.grab()
            prompt = f"Read the problem from this screenshot.\n\n{common_instructions}"
            code = call_ai(prompt, img, provider_types=["gemini"])
        else:
            prompt = f"Below is a problem extracted from an exam screen:\n\n{text}\n\n{common_instructions}"
            code = call_ai(prompt, None, provider_types=["gemini"])
    else:  # Screenshot
        img = ImageGrab.grab()
        prompt = f"Read the problem from this screenshot.\n\n{common_instructions}"
        code = call_ai(prompt, img, provider_types=["gemini", "openai"])

    with req_lock:
        if req_id != latest_code_req_id:
            print(f"--> Discarded stale coding response [Req {req_id}]")
            return

    if code == "Error":
        print(f"\n[Req {req_id}] All providers failed. Clipboard untouched.")
        play_sound("Basso")
        return

    code = strip_markdown(code)
    print(f"\n{'='*40}\nSOLUTION SAVED TO FILE! [Req {req_id}]\n{'='*40}\n")
    global ghost_typing_reset_flag
    with open("code.txt", "w", encoding="utf-8") as f:
        f.write(code + "\n\n")
    ghost_typing_reset_flag = True
    global ghost_typing_offset
    ghost_typing_offset = 0
    play_sound("Ping")
    global code_count
    code_count += 1
    print_status()

    print(">> Fetching structured explanation...")
    exp_prompt = (
        f"Explain the following solution (code or SQL query) as if you are a normal student writing simple, casual study notes.\n\n"
        f"Format strictly in plain text (ABSOLUTELY NO LaTeX, NO backslashes, NO math symbols like \\(, \\), $, \\mathcal, NO bold/markdown):\n"
        f"1. Core Idea: (1 short casual sentence, like a student summary)\n"
        f"2. Steps: (1-2 short casual sentences explaining what it does)\n"
        f"3. Edge Cases / Conditions: (1 short simple sentence, or 'None')\n"
        f"4. Complexity: (Simple plain text like 'Time: O(N), Space: O(1)' or 'SQL: Index scan on primary key')\n\n"
        f"Code/Query:\n{code}\n\n"
        f"CRITICAL: Keep it casual, human-written, and extremely concise. ABSOLUTELY ZERO backslashes or LaTeX math markup."
    )
    explanation = call_ai(exp_prompt, img=None, provider_types=["gemini", "openai"])
    if explanation != "Error":
        explanation = clean_human_explanation(explanation)
        print(f"\n{'='*40}\nEXPLANATION SAVED TO FILE!\n{'='*40}\n")
        global explanation_typing_reset_flag
        with open("explanation.txt", "w", encoding="utf-8") as f:
            f.write(explanation + "\n\n")
        explanation_typing_reset_flag = True
        global explanation_typing_offset
        explanation_typing_offset = 0
        play_sound("Pop")


def handle_bug_report():
    global latest_code_req_id
    with req_lock:
        latest_code_req_id += 1
        req_id = latest_code_req_id

    print(f"\nAction: Bug Report [Req {req_id}]...")
    play_sound("Pop")

    if not session_active:
        print("[Warning] Session is NOT active! The AI won't remember the previous code. Press Right Shift + S to start a session before generating the initial code next time.")

    if INPUT_MODE == 1:  # OCR
        img = ImageGrab.grab()
        text = extract_text_ocr(img)
        print(f"[OCR] Extracted {len(text)} chars.")
        prompt = (
            f"Below is a test case failure or error message from an exam screen:\n\n{text}\n\n"
            "You previously provided a code solution for the problem. Diagnose the issue and write the complete, bug-free, and corrected solution.\n"
            "RULES:\n1. Accurate, optimal, concise.\n2. ABSOLUTELY NO COMMENTS (no #, no //, no /* */).\n"
            "3. If C++, include `using namespace std;`.\n4. Return ONLY raw code."
        )
        code = call_ai(prompt, None, provider_types=["gemini"])
    elif INPUT_MODE == 2:  # Accessibility
        text = extract_text_accessibility()
        print(f"[Accessibility] Extracted {len(text)} chars.")
        if not text:
            print("[Accessibility] No text found. Falling back to screenshot.")
            img = ImageGrab.grab()
            prompt = (
                "You previously provided a code solution for the problem. Read the test case failure or error message from this screenshot. "
                "Diagnose the issue and write the complete, bug-free, and corrected solution.\n"
                "RULES:\n1. Code must be accurate, optimal, and concise.\n2. ABSOLUTELY NO COMMENTS (no #, no //, no /* */).\n"
                "3. If C++, include `using namespace std;`.\n4. Return ONLY raw code — no markdown fences."
            )
            code = call_ai(prompt, img, provider_types=["gemini"])
        else:
            prompt = (
                f"Below is a test case failure or error message from an exam screen:\n\n{text}\n\n"
                "You previously provided a code solution for the problem. Diagnose the issue and write the complete, bug-free, and corrected solution.\n"
                "RULES:\n1. Accurate, optimal, concise.\n2. ABSOLUTELY NO COMMENTS (no #, no //, no /* */).\n"
                "3. If C++, include `using namespace std;`.\n4. Return ONLY raw code."
            )
            code = call_ai(prompt, None, provider_types=["gemini"])
    else:  # Screenshot
        img = ImageGrab.grab()
        prompt = (
            "You previously provided a code solution for the problem. Read the test case failure or error message from this screenshot. "
            "Diagnose the issue and write the complete, bug-free, and corrected solution.\n"
            "RULES:\n1. Code MUST look completely human-written to bypass AI detectors. Avoid overly formal variable names, standard AI structures, or textbook perfection. Write it like a normal student would.\n"
            "2. ABSOLUTELY NO COMMENTS (no #, no //, no /* */).\n3. If C++, include `using namespace std;`.\n4. Return ONLY raw code — no markdown fences."
        )
        code = call_ai(prompt, img, provider_types=["gemini", "openai"])

    with req_lock:
        if req_id != latest_code_req_id:
            print(f"--> Discarded stale bug report response [Req {req_id}]")
            return

    if code == "Error":
        print(f"\n[Req {req_id}] All providers failed. Clipboard untouched.")
        play_sound("Basso")
        return

    code = strip_markdown(code)
    print(f"\n{'='*40}\nBUG FIXED SOLUTION SAVED TO FILE! [Req {req_id}]\n{'='*40}\n")
    global ghost_typing_reset_flag, ghost_typing_offset
    with open("code.txt", "w", encoding="utf-8") as f:
        f.write(code + "\n\n")
    ghost_typing_reset_flag = True
    ghost_typing_offset = 0
    play_sound("Ping")
    global code_count
    code_count += 1
    print_status()


def handle_essay():
    global latest_essay_req_id
    with req_lock:
        latest_essay_req_id += 1
        req_id = latest_essay_req_id

    print(f"\nAction: Essay [Req {req_id}]...")
    play_sound("Pop")

    if INPUT_MODE == 1:  # OCR
        img = ImageGrab.grab()
        text = extract_text_ocr(img)
        print(f"[OCR] Extracted {len(text)} chars.")
        prompt = (
            f"Below is an essay or short-answer prompt extracted from an exam screen:\n\n{text}\n\n"
            "Write a high-quality, human-sounding response. "
            "Plain paragraphs only — no bullet points, no bold, no markdown. Return ONLY the essay text."
        )
        essay = call_ai(prompt, None, provider_types=["gemini"])
    elif INPUT_MODE == 2:  # Accessibility
        text = extract_text_accessibility()
        print(f"[Accessibility] Extracted {len(text)} chars.")
        if not text:
            print("[Accessibility] No text found. Falling back to screenshot.")
            img = ImageGrab.grab()
            prompt = (
                "You are an expert student. Read the essay or short-answer prompt from this screenshot. "
                "Write a high-quality, human-sounding response. "
                "Use plain paragraphs only — no bullet points, no bold, no markdown. "
                "Return ONLY the essay text."
            )
            essay = call_ai(prompt, img, provider_types=["gemini"])
        else:
            prompt = (
                f"Below is an essay or short-answer prompt extracted from an exam screen:\n\n{text}\n\n"
                "Write a high-quality, human-sounding response. "
                "Plain paragraphs only — no bullet points, no bold, no markdown. Return ONLY the essay text."
            )
            essay = call_ai(prompt, None, provider_types=["gemini"])
    else:  # Screenshot
        img = ImageGrab.grab()
        prompt = (
            "You are an expert student. Read the essay or short-answer prompt from this screenshot. "
            "Write a high-quality, human-sounding response. "
            "Use plain paragraphs only — no bullet points, no bold, no markdown. "
            "Return ONLY the essay text."
        )
        essay = call_ai(prompt, img, provider_types=["gemini", "openai"])

    with req_lock:
        if req_id != latest_essay_req_id:
            return

    if essay == "Error":
        print(f"\n[Req {req_id}] All providers failed. Clipboard untouched.")
        play_sound("Basso")
        return

    print(f"\n{'='*40}\nESSAY SAVED TO FILE! [Req {req_id}]\n{'='*40}\n")
    global ghost_typing_reset_flag
    with open("code.txt", "w", encoding="utf-8") as f:
        f.write(essay + "\n\n")
    ghost_typing_reset_flag = True
    play_sound("Ping")
    global essay_count
    essay_count += 1
    print_status()


# ─── GHOST TYPING ─────────────────────────────────────────────────────────────

def reset_ghost_typing():
    """Reset typing progress back to the beginning (0%)."""
    global ghost_typing_offset, ghost_typing_reset_flag, ghost_typing_active
    with state_lock:
        ghost_typing_active = False
    ghost_typing_offset = 0
    ghost_typing_reset_flag = True
    print("\n[Ghost Typing] ⏪ Rewound to beginning (0%). Press Right Shift + P to type from start.")
    play_sound("Hero")


def type_text():
    global ghost_typing_active, ghost_typing_reset_flag, ghost_typing_offset
    ctrl = keyboard.Controller()

    # Release any shift keys currently held or stuck in pynput state
    try:
        ctrl.release(keyboard.Key.shift)
        ctrl.release(keyboard.Key.shift_l)
        ctrl.release(keyboard.Key.shift_r)
    except Exception:
        pass

    # Give user 200ms to release physical Shift + P keys so characters are typed with correct case & symbols
    time.sleep(0.20)

    # Delete the stray 'P' or 'p' typed into the editor when Shift + P was pressed
    try:
        ctrl.press(keyboard.Key.backspace)
        ctrl.release(keyboard.Key.backspace)
        time.sleep(0.04)
    except Exception:
        pass

    try:
        if not os.path.exists("code.txt"):
            return

        with open("code.txt", "r", encoding="utf-8") as f:
            full_text = f.read()

        # Normalize carriage returns
        full_text = full_text.replace('\r\n', '\n').replace('\r', '\n')

        # In Auto-Indent mode (0), strip leading indentation for non-python so auto-indenting editors (OneCompiler) don't double-indent.
        # In Exact-Indent mode (1), preserve all indentation for plain editors (CodeChef).
        lang = "cpp"
        if os.path.exists("lang.txt"):
            try:
                with open("lang.txt", "r", encoding="utf-8") as lf:
                    lang = lf.read().strip()
            except Exception:
                pass

        if INDENT_MODE == 0 and lang != "python":
            full_text = '\n'.join(line.lstrip() for line in full_text.split('\n'))

        if ghost_typing_reset_flag or ghost_typing_offset >= len(full_text):
            ghost_typing_reset_flag = False
            ghost_typing_offset = 0

        total_len = len(full_text)
        print(f"\n[Ghost Typing] Resumed/Started ({ghost_typing_offset}/{total_len} chars) [{INDENT_MODE_NAMES[INDENT_MODE]}] at {TYPING_SPEED_FACTOR:.2f}x speed.")

        scale = 1.0 / max(0.1, TYPING_SPEED_FACTOR)

        while ghost_typing_offset < total_len:
            if not ghost_typing_active:
                break

            char = full_text[ghost_typing_offset]

            try:
                if char == '\n':
                    # Dismiss autocomplete / suggestion popups before pressing Enter in Editor 3
                    ctrl.press(keyboard.Key.esc)
                    ctrl.release(keyboard.Key.esc)
                    time.sleep(0.012)
                    ctrl.press(keyboard.Key.enter)
                    ctrl.release(keyboard.Key.enter)
                    time.sleep(max(0.025, 0.045 * scale))
                elif char == '\t':
                    ctrl.type('    ')
                    time.sleep(max(0.01, 0.02 * scale))
                elif char == '&':
                    with ctrl.pressed(keyboard.Key.shift):
                        ctrl.press('7')
                        ctrl.release('7')
                elif char == '|':
                    with ctrl.pressed(keyboard.Key.shift):
                        ctrl.press('\\')
                        ctrl.release('\\')
                else:
                    ctrl.type(char)
            except Exception:
                pass

            ghost_typing_offset += 1

            # Dynamic typing speed delay according to TYPING_SPEED_FACTOR
            if char in ['\n', '\r']:
                delay = max(0.01, random.uniform(0.03, 0.06) * scale)
            elif char in [' ', '\t']:
                delay = max(0.003, random.uniform(0.012, 0.03) * scale)
            elif char in ['(', ')', '{', '}', '[', ']', ';', ':', '=', '+', '-', '*', '/', '<', '>', '&', '|', '!']:
                delay = max(0.004, random.uniform(0.02, 0.04) * scale)
            else:
                delay = max(0.002, random.uniform(0.01, 0.028) * scale)

            time.sleep(delay)

    except Exception as e:
        print(f"\n[Ghost Typing] Error: {e}")

    with state_lock:
        ghost_typing_active = False

    if 'full_text' in locals() and ghost_typing_offset >= len(full_text):
        ghost_typing_offset = 0
        print("\n[Ghost Typing] Finished (100%). Reset to start.")
        play_sound("Purr")
    else:
        print(f"\n[Ghost Typing] Paused at {ghost_typing_offset}/{len(full_text) if 'full_text' in locals() else '?'}. (Press Shift+R to reset to start, Shift+P to resume).")


last_toggle_time = 0

def toggle_ghost_typing():
    global ghost_typing_active, ghost_typing_thread, last_toggle_time

    with state_lock:
        now = time.time()
        if now - last_toggle_time < 0.2:
            return
        last_toggle_time = now

        if ghost_typing_active:
            ghost_typing_active = False
            return

        if not os.path.exists("code.txt"):
            open("code.txt", "w", encoding="utf-8").close()
        
        global ghost_typing_content, explanation_typing_active, ghost_typing_reset_flag, ghost_typing_offset
        
        if explanation_typing_active:
            explanation_typing_active = False
            
        with open("code.txt", "r", encoding="utf-8") as f:
            current_content = f.read()

        if current_content != ghost_typing_content:
            ghost_typing_reset_flag = True
            ghost_typing_offset = 0
            ghost_typing_content = current_content

        ghost_typing_active = True
        ghost_typing_thread = threading.Thread(target=type_text)
        ghost_typing_thread.start()


def type_explanation_text():
    global explanation_typing_active, explanation_typing_reset_flag, explanation_typing_offset
    ctrl = keyboard.Controller()

    # Release shift keys
    try:
        ctrl.release(keyboard.Key.shift)
        ctrl.release(keyboard.Key.shift_l)
        ctrl.release(keyboard.Key.shift_r)
    except Exception:
        pass

    # Give user 200ms to release physical Shift + E keys
    time.sleep(0.20)

    # Delete stray 'E' / 'e'
    try:
        ctrl.press(keyboard.Key.backspace)
        ctrl.release(keyboard.Key.backspace)
        time.sleep(0.04)
    except Exception:
        pass

    try:
        if not os.path.exists("explanation.txt"):
            return

        with open("explanation.txt", "r", encoding="utf-8") as f:
            full_text = f.read()

        full_text = full_text.replace('\r\n', '\n').replace('\r', '\n')

        if explanation_typing_reset_flag or explanation_typing_offset >= len(full_text):
            explanation_typing_reset_flag = False
            explanation_typing_offset = 0

        total_len = len(full_text)
        print(f"\n[Explanation Typing] Resumed/Started ({explanation_typing_offset}/{total_len} chars) at {TYPING_SPEED_FACTOR:.2f}x speed.")

        scale = 1.0 / max(0.1, TYPING_SPEED_FACTOR)

        while explanation_typing_offset < total_len:
            if not explanation_typing_active:
                break

            char = full_text[explanation_typing_offset]

            try:
                if char == '\n':
                    # Dismiss autocomplete / suggestion popups before Enter
                    ctrl.press(keyboard.Key.esc)
                    ctrl.release(keyboard.Key.esc)
                    time.sleep(0.012)
                    ctrl.press(keyboard.Key.enter)
                    ctrl.release(keyboard.Key.enter)
                    time.sleep(max(0.025, 0.045 * scale))
                elif char == '\t':
                    ctrl.type('    ')
                    time.sleep(max(0.01, 0.02 * scale))
                else:
                    ctrl.type(char)
            except Exception:
                pass

            explanation_typing_offset += 1

            # Dynamic typing speed delay according to TYPING_SPEED_FACTOR
            if char in ['\n', '\r']:
                delay = max(0.01, random.uniform(0.03, 0.06) * scale)
            elif char in [' ', '\t']:
                delay = max(0.003, random.uniform(0.012, 0.03) * scale)
            elif char in ['(', ')', '{', '}', '[', ']', ';', ':', '=', '+', '-', '*', '/']:
                delay = max(0.004, random.uniform(0.02, 0.04) * scale)
            else:
                delay = max(0.002, random.uniform(0.01, 0.028) * scale)

            time.sleep(delay)

    except Exception as e:
        print(f"\n[Explanation Typing] Error: {e}")

    with state_lock:
        explanation_typing_active = False

    if 'full_text' in locals() and explanation_typing_offset >= len(full_text):
        explanation_typing_offset = 0
        print("\n[Explanation Typing] Finished (100%). Reset to start.")
        play_sound("Purr")
    else:
        print(f"\n[Explanation Typing] Paused at {explanation_typing_offset}/{len(full_text) if 'full_text' in locals() else '?'}.")


def toggle_explanation_typing():
    global explanation_typing_active, explanation_typing_thread, last_toggle_time

    with state_lock:
        now = time.time()
        if now - last_toggle_time < 0.2:
            return
        last_toggle_time = now

        if explanation_typing_active:
            explanation_typing_active = False
            return

        if not os.path.exists("explanation.txt"):
            open("explanation.txt", "w", encoding="utf-8").close()
        
        global explanation_typing_content, ghost_typing_active, explanation_typing_reset_flag, explanation_typing_offset
        
        if ghost_typing_active:
            ghost_typing_active = False
            
        with open("explanation.txt", "r", encoding="utf-8") as f:
            current_content = f.read()

        if current_content != explanation_typing_content:
            explanation_typing_reset_flag = True
            explanation_typing_offset = 0
            explanation_typing_content = current_content

        explanation_typing_active = True
        explanation_typing_thread = threading.Thread(target=type_explanation_text)
        explanation_typing_thread.start()


def clear_clipboard():
    global ghost_typing_active, explanation_typing_active, ghost_typing_offset, explanation_typing_offset
    with state_lock:
        ghost_typing_active   = False
        explanation_typing_active = False
    ghost_typing_offset = 0
    explanation_typing_offset = 0
    pyperclip.copy("")
    with open("code.txt", "w", encoding="utf-8") as f:
        f.write("")
    with open("explanation.txt", "w", encoding="utf-8") as f:
        f.write("")
    print("\n[Clipboard, code.txt, and explanation.txt] Cleared.")
    play_sound("Basso")


# ─── SESSION MANAGEMENT ───────────────────────────────────────────────────────

def start_session():
    global session_active, session_history
    session_active  = True
    session_history = []
    print("\n[Session] STARTED — AI will remember conversation context.")
    play_sound("Hero")
    print_status()


def end_session():
    global session_active, session_history
    session_active  = False
    session_history = []
    print("\n[Session] ENDED — Memory cleared.")
    play_sound("Glass")
    print_status()


def quit_session():
    global session_active, session_history
    session_active  = False
    session_history = []
    play_sound("Tink")
    print_status()


def switch_provider():
    global current_provider_idx
    current_provider_idx = (current_provider_idx + 1) % len(PROVIDERS)
    
    try:
        w, h = SCREEN_WIDTH, SCREEN_HEIGHT
        positions = {
            0: (0, 0),                 # Top Left
            1: (w - 1, 0),             # Top Right
            2: (0, h - 1),             # Bottom Left
            3: (w - 1, h - 1),         # Bottom Right
            4: (0, h // 2),            # Middle Left
            5: (w - 1, h // 2)         # Middle Right
        }
        if current_provider_idx in positions:
            mouse_controller.position = positions[current_provider_idx]
    except Exception:
        pass

    play_sound("Ping")
    print_status()


# ─── MOUSE & KEYBOARD ─────────────────────────────────────────────────────────

current_keys        = set()
lock                = threading.Lock()


def on_click(x, y, button, pressed):
    if not pressed:
        return
    if button == mouse.Button.right:
        print(f"[Debug] Right-Click at: ({x}, {y}) | Zone: {TRIGGER_MARGIN}px | Provider: {PROVIDERS[current_provider_idx]['name']}")
            
        # Bottom-Left: Essay
        if x <= TRIGGER_MARGIN and y >= SCREEN_HEIGHT - TRIGGER_MARGIN:
            threading.Thread(target=handle_essay).start()
            
        # Bottom-Right: Clear Clipboard
        elif x >= SCREEN_WIDTH - TRIGGER_MARGIN and y >= SCREEN_HEIGHT - TRIGGER_MARGIN:
            clear_clipboard()


def on_press(key):
    global TYPING_SPEED_FACTOR
    with lock:
        try:
            current_keys.add(key)
            if any(k in current_keys for k in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r)):
                if key == keyboard.Key.up:
                    TYPING_SPEED_FACTOR += 0.25
                    print(f"\n[Speed] {TYPING_SPEED_FACTOR:.2f}x")
                    play_sound("Ping")
                    current_keys.discard(key)
                elif key == keyboard.Key.down:
                    TYPING_SPEED_FACTOR = max(0.5, TYPING_SPEED_FACTOR - 0.25)
                    print(f"\n[Speed] {TYPING_SPEED_FACTOR:.2f}x")
                    play_sound("Pop")
                    current_keys.discard(key)
                else:
                    char = getattr(key, 'char', None)
                    if char:
                        char = char.lower()
                        if char == 's':
                            start_session();    current_keys.clear()
                        elif char == 'd':
                            quit_session();     current_keys.clear()
                        elif char == 'p':
                            threading.Thread(target=toggle_ghost_typing).start(); current_keys.clear()
                        elif char == 'r':
                            reset_ghost_typing(); current_keys.clear()
                        elif char == 'b':
                            threading.Thread(target=handle_bug_report).start(); current_keys.clear()
                        elif char == 'e':
                            threading.Thread(target=toggle_explanation_typing).start(); current_keys.clear()
                        elif char == 'o':
                            switch_provider();  current_keys.clear()
                        elif char == 'l' or char == 'L':
                            toggle_input_mode();  current_keys.clear()
                        elif char == 'i':
                            toggle_indent_mode(); current_keys.clear()
                        elif char == 'c':
                            threading.Thread(target=handle_coding).start(); current_keys.clear()
                        elif char == 'm':
                            threading.Thread(target=handle_mcq).start(); current_keys.clear()
        except (AttributeError, KeyError):
            pass


def on_release(key):
    with lock:
        current_keys.discard(key)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    active_provider = PROVIDERS[current_provider_idx]['name']
    print(f"""
=============================================
   EXAM ASSISTANT LAUNCHED
=============================================
[MOUSE TRIGGERS — Right-Click]
  Bottom-Left  : 1x = Essay solution (saved to code.txt)
  Bottom-Right : 1x = Clear Clipboard & code.txt

[KEYBOARD]
  Right Shift + C       : Get Coding Solution & Explanation
  Right Shift + M       : Get MCQ Answer
  Right Shift + S/D     : Start / End session
  Right Shift + B       : Bug Report / Fix test cases
  Right Shift + P       : Toggle Ghost Typing (Code)
  Right Shift + R       : Reset / Rewind Typing to 0%
  Right Shift + I       : Toggle Indent Mode (Auto vs Exact)
  Right Shift + E       : Toggle Ghost Typing (Explanation)
  Right Shift + O       : Cycle to next provider
  Right Shift + L       : Toggle OCR / Screenshot mode
  Right Shift + Up/Down : Typing speed

[PROVIDERS — auto-rotates on failure]
""" + "\n".join(f"  {'*' if i == current_provider_idx else ' '} [{i+1}] {p['name']}"
                for i, p in enumerate(PROVIDERS)) + f"""

  Active: {active_provider}
=============================================
""")
    play_sound("Submarine")
    print_status()

    mouse_listener = mouse.Listener(on_click=on_click)
    mouse_listener.start()

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
