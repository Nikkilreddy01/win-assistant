import os

with open("assistant.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add ghost_typing_offset and explanation_typing_offset to globals
old_globals = """explanation_typing_active   = False
explanation_typing_thread   = None
explanation_typing_reset_flag = False"""
new_globals = """explanation_typing_active   = False
explanation_typing_thread   = None
explanation_typing_reset_flag = False
ghost_typing_offset = 0
explanation_typing_offset = 0"""
content = content.replace(old_globals, new_globals)

# 2. Add handle_bug_report function before handle_essay
handle_bug_report_code = """
def handle_bug_report():
    global latest_code_req_id
    with req_lock:
        latest_code_req_id += 1
        req_id = latest_code_req_id

    print(f"\\nAction: Bug Report [Req {req_id}]...")
    play_sound("Pop")

    if not session_active:
        print("[Warning] Session is NOT active! The AI won't remember the previous code. Press Right Shift + S to start a session before generating the initial code next time.")

    if INPUT_MODE == 1:  # OCR
        img = ImageGrab.grab()
        text = extract_text_ocr(img)
        print(f"[OCR] Extracted {len(text)} chars.")
        prompt = (
            f"Below is a test case failure or error message from an exam screen:\\n\\n{text}\\n\\n"
            "You previously provided a code solution for the problem. Diagnose the issue and write the complete, bug-free, and corrected solution.\\n"
            "RULES:\\n1. Accurate, optimal, concise.\\n2. Zero comments.\\n"
            "3. If C++, include `using namespace std;`.\\n4. Return ONLY raw code."
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
                "Diagnose the issue and write the complete, bug-free, and corrected solution.\\n"
                "RULES:\\n1. Code must be accurate, optimal, and concise.\\n2. Zero comments.\\n"
                "3. If C++, include `using namespace std;`.\\n4. Return ONLY raw code — no markdown fences."
            )
            code = call_ai(prompt, img, provider_types=["gemini"])
        else:
            prompt = (
                f"Below is a test case failure or error message from an exam screen:\\n\\n{text}\\n\\n"
                "You previously provided a code solution for the problem. Diagnose the issue and write the complete, bug-free, and corrected solution.\\n"
                "RULES:\\n1. Accurate, optimal, concise.\\n2. Zero comments.\\n"
                "3. If C++, include `using namespace std;`.\\n4. Return ONLY raw code."
            )
            code = call_ai(prompt, None, provider_types=["gemini"])
    else:  # Screenshot
        img = ImageGrab.grab()
        prompt = (
            "You previously provided a code solution for the problem. Read the test case failure or error message from this screenshot. "
            "Diagnose the issue and write the complete, bug-free, and corrected solution.\\n"
            "RULES:\\n1. Code MUST look completely human-written to bypass AI detectors. Avoid overly formal variable names, standard AI structures, or textbook perfection. Write it like a normal student would.\\n"
            "2. Zero comments.\\n3. If C++, include `using namespace std;`.\\n4. Return ONLY raw code — no markdown fences."
        )
        code = call_ai(prompt, img, provider_types=["gemini", "openai"])

    with req_lock:
        if req_id != latest_code_req_id:
            print(f"--> Discarded stale bug report response [Req {req_id}]")
            return

    if code == "Error":
        print(f"\\n[Req {req_id}] All providers failed. Clipboard untouched.")
        play_sound("Basso")
        return

    code = strip_markdown(code)
    print(f"\\n{'='*40}\\nBUG FIXED SOLUTION SAVED TO FILE! [Req {req_id}]\\n{'='*40}\\n")
    global ghost_typing_reset_flag, ghost_typing_offset
    with open("code.txt", "w", encoding="utf-8") as f:
        f.write(code + "\\n\\n")
    ghost_typing_reset_flag = True
    ghost_typing_offset = 0
    play_sound("Ping")
    global code_count
    code_count += 1
    print_status()

def handle_essay():"""
content = content.replace('def handle_essay():', handle_bug_report_code)

# 3. Update handle_coding and handle_essay to set offset to 0
content = content.replace(
    'ghost_typing_reset_flag = True', 
    'ghost_typing_reset_flag = True\n    global ghost_typing_offset\n    ghost_typing_offset = 0'
)
content = content.replace(
    'explanation_typing_reset_flag = True', 
    'explanation_typing_reset_flag = True\n        global explanation_typing_offset\n        explanation_typing_offset = 0'
)

# 4. Rewrite typing functions to remove 3s delay and use offset
old_type_text_section = content[content.find('def type_text():'):content.find('last_toggle_time = 0')]
type_text_replacement = """def type_text():
    global ghost_typing_active, ghost_typing_reset_flag, ghost_typing_offset
    ctrl = keyboard.Controller()

    print("\\n[Ghost Typing] Resumed/Started at ~45 WPM. Typing from code.txt...")
    try:
        with open("code.txt", "r", encoding="utf-8") as f:
            f.seek(ghost_typing_offset)
            while ghost_typing_active:
                if ghost_typing_reset_flag:
                    f.seek(0)
                    ghost_typing_offset = 0
                    ghost_typing_reset_flag = False

                char = f.read(1)
                if not char:
                    break
                
                ghost_typing_offset = f.tell()

                try:
                    ctrl.type(char)
                except Exception:
                    pass

                scale = 1.0 / TYPING_SPEED_FACTOR
                if char in ['\\n', '\\r']:
                    time.sleep(random.uniform(0.5, 1.2) * scale)
                elif char in [' ', '\\t']:
                    time.sleep(random.uniform(0.15, 0.35) * scale)
                elif char in ['(', ')', '{', '}', '[', ']', ';', ':', '=', '+', '-', '*', '/']:
                    time.sleep(random.uniform(0.25, 0.5) * scale)
                else:
                    time.sleep(random.uniform(0.15, 0.32) * scale)

                if random.random() < 0.03:
                    time.sleep(random.uniform(0.5, 1.2) * scale)
    except Exception as e:
        print(f"\\n[Ghost Typing] Error reading file: {e}")

    with state_lock:
        ghost_typing_active   = False
    print("\\n[Ghost Typing] Finished/Stopped.")
    play_sound("Purr")


def type_explanation_text():
    global explanation_typing_active, explanation_typing_reset_flag, explanation_typing_offset
    ctrl = keyboard.Controller()

    print("\\n[Explanation Typing] Resumed/Started at ~45 WPM. Typing from explanation.txt...")
    try:
        with open("explanation.txt", "r", encoding="utf-8") as f:
            f.seek(explanation_typing_offset)
            while explanation_typing_active:
                if explanation_typing_reset_flag:
                    f.seek(0)
                    explanation_typing_offset = 0
                    explanation_typing_reset_flag = False

                char = f.read(1)
                if not char:
                    break
                
                explanation_typing_offset = f.tell()

                try:
                    ctrl.type(char)
                except Exception:
                    pass

                scale = 1.0 / TYPING_SPEED_FACTOR
                if char in ['\\n', '\\r']:
                    time.sleep(random.uniform(0.5, 1.2) * scale)
                elif char in [' ', '\\t']:
                    time.sleep(random.uniform(0.15, 0.35) * scale)
                elif char in ['(', ')', '{', '}', '[', ']', ';', ':', '=', '+', '-', '*', '/']:
                    time.sleep(random.uniform(0.25, 0.5) * scale)
                else:
                    time.sleep(random.uniform(0.15, 0.32) * scale)

                if random.random() < 0.03:
                    time.sleep(random.uniform(0.5, 1.2) * scale)
    except Exception as e:
        print(f"\\n[Explanation Typing] Error reading file: {e}")

    with state_lock:
        explanation_typing_active = False
    print("\\n[Explanation Typing] Finished/Stopped.")
    play_sound("Purr")


"""
content = content.replace(old_type_text_section, type_text_replacement)

# 5. Clear clipboard reset offsets
old_clear_cb = content[content.find('def clear_clipboard():'):content.find('def start_session():')]
clear_cb = """def clear_clipboard():
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
    print("\\n[Clipboard, code.txt, and explanation.txt] Cleared.")
    play_sound("Basso")


# ─── SESSION MANAGEMENT ───────────────────────────────────────────────────────

"""
content = content.replace(old_clear_cb, clear_cb)

# 6. Update on_press keyboard triggers to include bug report
old_on_press = """                        elif char == 'p':
                            threading.Thread(target=toggle_ghost_typing).start(); current_keys.discard(key)"""
new_on_press = """                        elif char == 'p':
                            threading.Thread(target=toggle_ghost_typing).start(); current_keys.discard(key)
                        elif char == 'b':
                            threading.Thread(target=handle_bug_report).start(); current_keys.discard(key)"""
content = content.replace(old_on_press, new_on_press)

# 7. Add Right Shift + B to help menu
old_help_menu = """[KEYBOARD]
  Right Shift + C       : Get Coding Solution & Explanation
  Right Shift + M       : Get MCQ Answer
  Right Shift + S/D     : Start / End session"""
new_help_menu = """[KEYBOARD]
  Right Shift + C       : Get Coding Solution & Explanation
  Right Shift + M       : Get MCQ Answer
  Right Shift + S/D     : Start / End session
  Right Shift + B       : Bug Report / Fix test cases"""
content = content.replace(old_help_menu, new_help_menu)

with open("assistant.py", "w", encoding="utf-8") as f:
    f.write(content)
