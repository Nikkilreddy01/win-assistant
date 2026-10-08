# 🚀 Windows Coding & Exam Assistant (`win_assistant`)

A high-performance, stealth Windows desktop assistant for coding challenges, technical interviews, and exams. Built with low-level Win32 keyboard hooks, interactive hacker typing, and Gemini Vertex AI integration.

---

## ⚡ Direct Download (No Sign-in Required)

👉 **[Download `win_assistant.exe` (Latest Release)](https://github.com/Nikkilreddy01/win-assistant/releases/download/v1.0.0/win_assistant.exe)**

*Standalone Windows executable. No Python installation, libraries, or setup required. Just download and run!*

---

## ✨ Key Features

* **⌨️ Mode 2: Interactive Keypress (Hacker Typer)**:
  * Default mode. Mash ANY random keys on your keyboard (`asdfghjk...`) and the assistant types the exact generated code character-by-character into the active window.
  * **Auto-Unlock**: Automatically plays a completion sound and unlocks normal keyboard control 0.4s after the code reaches 100%.
  * **Smart Indentation**: Automatically respects existing IDE indents (e.g., LeetCode, HackerRank).
* **🤖 Prompt Steering Round (`Right Shift + G`)**:
  * Formatted as clean, direct bullet points (zero filler).
  * Explicitly provides target language, optimal algorithmic approach, exact variables to declare, 1-sentence core logic, edge cases, and complexity.
  * In chat windows, enters line breaks using `Shift + Enter` so prompts never send prematurely.
* **💻 Direct DSA / Coding Solves (`Right Shift + C`)**:
  * Generates optimal solutions in C++, Java, Python, or SQL based on what's visible on screen.
  * Completely clean raw code (zero comments, standard 4-space indentation, ready to run).
* **🐛 Bug Fix & Test Failure Diagnosis (`Right Shift + F` / `Right Shift + B`)**:
  * Diagnoses failed test cases and generates immediate targeted code fixes.
* **🎯 MCQ Solver (`Right Shift + M`)**:
  * Solves multiple choice questions and automatically guides the cursor to the correct option (A, B, C, or D).
* **🔒 Stealth Lock (`Right Shift + ?`)**:
  * Instantly freezes/unfreezes all assistant functions and hotkeys on demand.
* **⏹️ Emergency Stop (`Esc`)**:
  * Instantly halts active typing.

---

## 🎮 Hotkey Cheatsheet

All shortcuts use the **Right Shift** key for maximum stealth:

| Hotkey | Action | Description |
| :--- | :--- | :--- |
| **Right Shift + C** | 💻 **Direct Code** | Analyzes screen and solves DSA/SQL problem directly into `code.txt`. |
| **Right Shift + G** | 🤖 **Guided Prompt** | Generates concise architectural steering prompt with exact variables and approach. |
| **Right Shift + F** | 🔍 **Critique / Fix** | Analyzes failed test cases and generates targeted fix prompt. |
| **Right Shift + B** | 🐛 **Bug Report** | Directly rewrites code to fix runtime or logic bugs. |
| **Right Shift + M** | 🎯 **MCQ Answer** | Identifies correct option and moves mouse cursor to it. |
| **Right Shift + P** | ⏯️ **Toggle Typing** | Arms or pauses typing session (resumes from current offset). |
| **Right Shift + R** | ⏪ **Rewind Typing** | Resets typing progress back to 0%. |
| **Right Shift + Y / H**| 🔄 **Toggle Mode** | Toggles between Mode 1 (Auto) and Mode 2 (Interactive Typer). |
| **Right Shift + ?** | 🔒 **Stealth Lock** | Freezes the tool completely (safe when screen is observed). |
| **Right Shift + L** | 👁️ **Input Mode** | Cycles input capture: Screenshot ➔ OCR (Tesseract) ➔ Accessibility. |
| **Right Shift + I** | 📐 **Indent Mode** | Toggles Smart-Indent (DSA editors) vs Raw-Indent (Notepad). |
| **Right Shift + Up / Down**| ⚡ **Speed** | Increases or decreases typing cadence (Mode 1). |
| **Esc** | ⏹️ **Emergency Stop**| Instantly aborts typing. |

---

## 🛠️ Building from Source

If you prefer building the `.exe` yourself on Windows:

```cmd
git clone https://github.com/Nikkilreddy01/win-assistant.git
cd win-assistant
pip install -r requirements.txt
build.bat
```

The compiled standalone executable will be generated at `dist\win_assistant.exe`.

---

## 📄 License

MIT License. Designed for educational, interview simulation, and testing purposes.
