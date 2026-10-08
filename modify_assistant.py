import re
import os

with open("assistant.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add global variables
globals_add = """ghost_typing_active   = False
ghost_typing_thread   = None
ghost_typing_reset_flag = False
ghost_typing_offset   = 0
explanation_typing_active   = False
explanation_typing_thread   = None
explanation_typing_reset_flag = False
explanation_typing_offset   = 0"""
content = re.sub(r'ghost_typing_active\s*=\s*False\nghost_typing_thread\s*=\s*None\nghost_typing_reset_flag\s*=\s*False', globals_add, content)

# 2. Update handle_coding() to fetch explanation
coding_end = """    code = strip_markdown(code)
    print(f"\\n{'='*40}\\nCODING SOLUTION SAVED TO FILE! [Req {req_id}]\\n{'='*40}\\n")
    global ghost_typing_reset_flag, ghost_typing_offset, explanation_typing_reset_flag, explanation_typing_offset
    with open("code.txt", "w", encoding="utf-8") as f:
        f.write(code + "\\n\\n")
    ghost_typing_reset_flag = True
    ghost_typing_offset = 0
    play_sound("Ping")
    
    print(">> Fetching 4-line explanation...")
    exp_prompt = f"Explain the following code in exactly 4 short, simple lines:\\n\\n{code}"
    explanation = call_ai(exp_prompt, img=None, provider_types=["gemini", "openai"])
    if explanation != "Error":
        print(f"\\n{'='*40}\\nEXPLANATION SAVED TO FILE!\\n{'='*40}\\n")
        with open("explanation.txt", "w", encoding="utf-8") as f:
            f.write(explanation + "\\n\\n")
        explanation_typing_reset_flag = True
        explanation_typing_offset = 0
        play_sound("Pop")

    global code_count
    code_count += 1
    print_status()"""
content = re.sub(r'    code = strip_markdown\(code\).*?print_status\(\)', coding_end, content, flags=re.DOTALL)

# 3. Update handle_bug_report and handle_essay to reset ghost_typing_offset
content = re.sub(r'ghost_typing_reset_flag = True', r'ghost_typing_reset_flag = True\n    global ghost_typing_offset\n    ghost_typing_offset = 0', content)

# 4. Rewrite type_text and add explanation typing functions
typing_funcs = """def type_text():
    global ghost_typing_active, ghost_typing_reset_flag, ghost_typing_offset
    ctrl = keyboard.Controller()

    print("\\n[Ghost Typing] Started/Resumed at ~45 WPM. Typing from code.txt...")
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

    print("\\n[Explanation Typing] Started/Resumed at ~45 WPM. Typing from explanation.txt...")
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


last_toggle_time = 0

def toggle_ghost_typing():
    global ghost_typing_active, ghost_typing_thread, last_toggle_time

    with state_lock:
        now = time.time()
        if now - last_toggle_time < 0.5:
            return
        last_toggle_time = now

        if ghost_typing_active:
            ghost_typing_active = False
            print("\\n[Ghost Typing] PAUSED.")
        else:
            if not os.path.exists("code.txt"):
                open("code.txt", "w", encoding="utf-8").close()
            ghost_typing_active = True
            ghost_typing_thread = threading.Thread(target=type_text)
            ghost_typing_thread.start()


def toggle_explanation_typing():
    global explanation_typing_active, explanation_typing_thread, last_toggle_time

    with state_lock:
        now = time.time()
        if now - last_toggle_time < 0.5:
            return
        last_toggle_time = now

        if explanation_typing_active:
            explanation_typing_active = False
            print("\\n[Explanation Typing] PAUSED.")
        else:
            if not os.path.exists("explanation.txt"):
                open("explanation.txt", "w", encoding="utf-8").close()
            explanation_typing_active = True
            explanation_typing_thread = threading.Thread(target=type_explanation_text)
            explanation_typing_thread.start()"""

content = re.sub(r'def type_text\(\):.*?def toggle_ghost_typing\(\):.*?ghost_typing_thread\.start\(\)', typing_funcs, content, flags=re.DOTALL)

# 5. Clear clipboard changes
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
    play_sound("Basso")"""
content = re.sub(r'def clear_clipboard\(\):.*?play_sound\("Basso"\)', clear_cb, content, flags=re.DOTALL)

# 6. on_click Mouse triggers
on_click = """def on_click(x, y, button, pressed):
    if not pressed:
        return
    if button == mouse.Button.right:
        print(f"[Debug] Right-Click at: ({x}, {y}) | Zone: {TRIGGER_MARGIN}px | Provider: {PROVIDERS[current_provider_idx]['name']}")
        
        # Bottom-Left: Essay
        if x <= TRIGGER_MARGIN and y >= SCREEN_HEIGHT - TRIGGER_MARGIN:
            threading.Thread(target=handle_essay).start()
            
        # Bottom-Right: Clear Clipboard
        elif x >= SCREEN_WIDTH - TRIGGER_MARGIN and y >= SCREEN_HEIGHT - TRIGGER_MARGIN:
            clear_clipboard()"""
content = re.sub(r'def on_click\(x, y, button, pressed\):.*?clear_clipboard\(\)', on_click, content, flags=re.DOTALL)

# 7. on_press Keyboard triggers
on_press_append = """                        elif char == 'p':
                            threading.Thread(target=toggle_ghost_typing).start(); current_keys.discard(key)
                        elif char == 'b':
                            threading.Thread(target=handle_bug_report).start(); current_keys.discard(key)
                        elif char == 'e':
                            threading.Thread(target=toggle_explanation_typing).start(); current_keys.discard(key)
                        elif char == 'o':
                            switch_provider();  current_keys.discard(key)
                        elif char == 'l' or char == 'L':
                            toggle_input_mode();  current_keys.discard(key)
                        elif char == 'c':
                            threading.Thread(target=handle_coding).start(); current_keys.discard(key)
                        elif char == 'm':
                            threading.Thread(target=handle_mcq).start(); current_keys.discard(key)"""
content = re.sub(r'                        elif char == \'p\':.*?toggle_input_mode\(\);\s*current_keys\.discard\(key\)', on_press_append, content, flags=re.DOTALL)

# 8. Help Menu
help_menu = """[MOUSE TRIGGERS — Right-Click]
  Bottom-Left  : 1x = Essay solution (saved to code.txt)
  Bottom-Right : 1x = Clear Clipboard & text files

[KEYBOARD]
  Right Shift + C       : Get Coding Solution & Explanation
  Right Shift + M       : Get MCQ Answer
  Right Shift + S/D     : Start / End session
  Right Shift + B       : Bug Report / Fix test cases
  Right Shift + P       : Toggle Ghost Typing (Code)
  Right Shift + E       : Toggle Ghost Typing (Explanation)
  Right Shift + O       : Cycle to next provider
  Right Shift + L       : Toggle OCR / Screenshot mode"""
content = re.sub(r'\[MOUSE TRIGGERS — Right-Click\].*?Toggle OCR / Screenshot mode', help_menu, content, flags=re.DOTALL)

with open("assistant.py", "w", encoding="utf-8") as f:
    f.write(content)
