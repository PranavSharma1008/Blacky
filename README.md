# BlackyAgent 🐾

> **An Autonomous, Siri-like Personal AI Assistant for macOS & Mobile with Full Execution Power.**

BlackyAgent combines the conversational elegance and voice interaction of Siri with unconstrained local capabilities: autonomous file management, code generation & execution, live web search, macOS automation, and mobile remote control.

---

## 🌟 Key Features

- **🎙️ Siri-Style Walkie-Talkie Voice (Push-to-Talk)**:
  - **Mac Fn (Globe 🌐) Key**: Hold the `[Fn]` key while speaking; release it when done. Blacky immediately transcribes and executes your command!
  - **Manual Fallback**: Press `Enter` to record audio via microphone, or type your command directly.
  - Speaks operational responses back using macOS's built-in natural voice engine (`say`).
- **💬 WhatsApp Desktop Automation (macOS Native)**:
  - `whatsapp_send_message`: Send messages to contacts or phone numbers on WhatsApp Desktop with zero typing required.
  - `whatsapp_open_chat`: Open any contact's WhatsApp chat instantly.
  - `whatsapp_start_video_call`: Initiate direct 1-on-1 WhatsApp video calls.
  - `whatsapp_start_voice_call`: Initiate direct WhatsApp voice calls.
  - Intelligent contact disambiguation if multiple contacts share a name.
- **📱 Mobile Remote Mode (`blacky -m` / `blacky.sh -m`)**:
  - Launch a lightweight, Siri-inspired glassmorphic mobile web app.
  - **🌐 Public 5G Tunnel**: Automated Cloudflare tunnel enables secure access from anywhere across the globe on mobile cellular data.
  - **🏠 Local Wi-Fi**: Fast direct access with terminal ASCII QR code scanner.
  - Built-in mobile microphone (Web Speech API) & mobile voice feedback (Web Audio Speech Synthesis).
  - Quick action chips and live tool execution monitor.
- **📁 Full File System Operations**:
  - `create_folder`: Recursively create directories.
  - `write_file`: Generate complete, clean code with test cases, documentation, and configuration files.
  - `read_file` & `edit_file`: Read and modify existing files.
  - `list_directory`: Explore project structures.
- **⚡ Code Runner & Terminal Execution**:
  - `run_terminal_command`: Execute shell commands, install pip packages, run tests.
  - `run_python_code`: Execute Python snippets on the fly with timeout protection.
- **🌐 Live Web Search & Scraping**:
  - `search_web`: Real-time web search powered by DuckDuckGo (free, zero API key required).
  - `fetch_webpage`: Parse and summarize articles, documentation, and web pages.
  - `open_in_browser`: Open URLs directly in Safari/Chrome.
- **🍎 macOS Automation**:
  - `open_application`: Launch apps like WhatsApp, Spotify, Chrome, Terminal, Calculator, Notes, etc.
  - `set_system_volume`: Adjust volume from 0 to 100%.
  - `get_system_info`: Inspect battery percentage, CPU load, and RAM usage.
  - `send_notification`: Deliver macOS system notifications.
  - `run_applescript`: Custom deep AppleScript automation.
- **📱 Mobile Device Control**:
  - `mobile_get_connected_devices`: Detect connected iOS devices (via `pymobiledevice3`) and Android devices (via ADB).
  - `mobile_android_command`: Send ADB commands to connected Android phones.
  - `mobile_run_shortcut`: Trigger Apple Shortcuts that sync to iPhone/iPad.
  - `mobile_send_imessage`: Send SMS/iMessages to contacts via Apple Messages.
- **🧠 Intelligent Gemini Engine with Automatic Fallback**:
  - Uses Google Gemini (Gemini 3.5 Flash, 3.8 Flash, Flash-Latest, 2.5 Pro) with native Automatic Function Calling (AFC).
  - Multi-tier model fallback automatically handles 503 load spikes and 429 rate limits seamlessly.

---

## 🚀 Quickstart

### 1. Installation
Clone or navigate to the repository directory:
```bash
cd "BlackyAgent"

# Install all dependencies and register CLI entrypoints (blacky / blaky)
pip3 install -e .
```

### 2. Configure API Key
Create or verify your `.env` file (a configured key is already included):
```env
# Google Gemini API Key (Get free at https://aistudio.google.com/apikey)
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash
GEMINI_FALLBACK_MODELS=gemini-flash-latest,gemini-3.1-flash-lite,gemini-2.5-pro,gemini-3.8-flash

# Voice Settings
BLACKY_VOICE=Samantha
BLACKY_SPEECH_RATE=195
BLACKY_VOICE_ENABLED=true
```

---

## 💻 Usage Modes

### 1. Interactive Terminal REPL (Default)
Start a conversational session in your terminal with rich syntax highlighting and tool execution feedback:
```bash
blacky
# or
blaky
```

### 2. Push-to-Talk Siri Voice Mode
Speak directly to Blacky. Press `[Enter]`, speak your request, and Blacky will execute it and speak back to you:
```bash
blacky --voice
# or
blacky -v
```

### 3. Mobile Remote Mode (Phone Controller)
Control Blacky from your iPhone, iPad, or Android phone:
```bash
blacky --mobile
# or
blacky -m
```
- Displays an ASCII QR code in your terminal.
- Point your phone camera at the terminal screen to open the Siri-style mobile web interface.
- Tap the microphone button on your phone to talk to Blacky!

### 4. Direct One-Shot Execution
Pass your instruction directly as a single command:
```bash
# Example 1: Create a folder and write code
blacky "create a folder named algorithms and write a Python file for binary search with test cases"

# Example 2: Live web research
blacky "search the web for the latest Python release and summarize what's new"

# Example 3: macOS automation
blacky "open Spotify and tell me my Mac battery status"
```

---

## 🧪 Running Tests

Run the comprehensive unit test suite:
```bash
python3 -m unittest discover tests
```

---

## 📂 Project Architecture

```
BlackyAgent/
├── .env.example               # Configuration template
├── .gitignore                 # Safe repository exclusions (.env, caches, etc.)
├── pyproject.toml             # Package configuration & CLI scripts (`blacky`, `blaky`)
├── requirements.txt           # Python dependencies
├── README.md                  # Documentation
├── blacky.sh                  # Multi-tab terminal launcher & controller
├── run.sh                     # Quick execution wrapper
├── algorithms/                # Algorithmic code examples
│   └── binary_search.py       # Full binary search implementation
├── utils/                     # Utility modules
│   └── string_helpers.py      # String operations, casing, & palindromes
├── blacky/
│   ├── __init__.py            # Package root
│   ├── main.py                # CLI argument parser and mode runners
│   ├── config.py              # Centralized environment configuration
│   ├── core/
│   │   ├── agent.py           # ReAct autonomous orchestrator & model fallback
│   │   └── prompts.py         # System prompt & tool guidance
│   ├── tools/
│   │   ├── base.py            # ToolRegistry and execution logging
│   │   ├── filesystem.py      # Folder creation, file writing/reading/editing
│   │   ├── terminal.py        # Terminal shell & python execution
│   │   ├── web.py             # DuckDuckGo search & webpage scraper
│   │   ├── macos.py           # Apps, volume, battery, notifications
│   │   ├── whatsapp.py        # Native WhatsApp desktop messaging & calls
│   │   └── mobile.py          # iOS, Android ADB, Apple Shortcuts, iMessage
│   ├── voice/
│   │   ├── tts.py             # Zero-latency macOS `say` voice synthesis
│   │   └── stt.py             # Fn push-to-talk microphone audio transcription
│   ├── ui/
│   │   └── console.py         # Rich terminal output, banners, QR codes
│   └── web/
│       ├── server.py          # FastAPI server with Cloudflare 5G tunnel
│       └── static/index.html  # Glassmorphic Siri mobile web client
└── tests/
    ├── test_filesystem.py     # Filesystem unit tests
    ├── test_tools.py          # Tool registry and execution tests
    ├── test_whatsapp.py       # WhatsApp tool validation tests
    ├── test_utils.py          # String helper unit tests
    └── test_agent.py          # Agent initialization and inference tests
```

---

## 🛡️ License
MIT License. Built for full local automation on macOS.
