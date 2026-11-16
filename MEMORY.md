# BlackyAgent — Project Memory

## 1. Project Overview
BlackyAgent is an autonomous, Siri-like personal desktop AI assistant for macOS and mobile with unconstrained local execution capabilities. It integrates voice interaction (Option-key walkie-talkie), screen awareness, local terminal/code runner, filesystem operations, macOS GUI automation, WhatsApp Desktop native automation, and mobile remote control.

## 2. Tech Stack
- **Language**: Python >= 3.10 (tested on Python 3.12 on macOS)
- **AI / LLM**: Local Ollama only (`ollama` Python client >= 0.4, server `http://localhost:11434`). Default model `qwen3.5:4b` (text + native tool calling). Optional separate vision model via `OLLAMA_VISION_MODEL` (e.g. `llava:7b`); no cloud provider and no auto-download.
- **Speech**:
  - STT: Option-key push-to-talk via macOS `CoreGraphics`/`Carbon` C bindings + `SpeechRecognition` + `ffmpeg`
  - TTS: Native macOS `say` synthesis (`Samantha` voice at 195 wpm) with operational text filtering
- **Web & Scraper**: DuckDuckGo search (`duckduckgo-search`), BeautifulSoup4, Requests
- **Mobile Remote**: FastAPI, Uvicorn, Pydantic, TryCloudflare (Cloudflared tunnel), QR code generation
- **CLI & UI**: Rich console, custom multi-terminal IDE detection launcher (`blacky.sh`)

## 3. Architecture & Key Patterns
- **Manual Function Calling**: The agent runs its own tool loop against Ollama (no blind automatic execution), enforcing safety gates, screen verification, duplicate-call detection, a hop limit and user confirmations. Tool JSON schemas are generated from Python signatures in `blacky/tools/base.py`.
- **Continuous Screen Awareness**: Observes frontmost apps, browser URLs, takes `/tmp/blacky_live_screen.jpg` snapshots, and injects active screen state into reasoning.
- **Strict User-Intent Boundary**: Strict separation between Search, Add-to-Cart, Media Play, and Checkout.
- **Disambiguation & Never-AutoSelect**: Never guesses when multiple contacts/products match; halts for user clarification.
- **Idempotent Fullscreen Mode**: Standardizes application windows using native macOS Full Screen before UI automation.
- **Safety Confirmation Gates**: Gated tools (`delete_item`, `blinkit_checkout_flow`, `amazon_checkout_flow`, unprompted messaging) require explicit confirmation.

## 4. Completed Features
- Universal CLI commands (`blacky`, `blaky`) and bash launcher with IDE tab spawning (`blacky.sh`).
- Automatic Ollama startup & auto-revival: `./blacky.sh`, `blacky` CLI, and `OllamaProvider.chat()` automatically check and revive Ollama in the background if it is not running.
- Direct Intent Fast-Path: High-frequency deterministic OS actions (`open whatsapp`, `open chrome`, `open spotify`, etc.) and WhatsApp operations (`open whatsapp and search for You and send a hello message`, `send hello to X on whatsapp`, `text X on whatsapp Y`, etc.) execute instantly (0.1s) without waiting for 30s+ local LLM token reasoning on Apple Silicon M2.
- 6 complete tool suites: Filesystem, Terminal, Web & Browser, macOS System Control, WhatsApp Desktop, Mobile Control.
- Global Option & Fn key push-to-talk voice mode (both [Fn] Globe 🌐 and [Option] ⌥ keys work simultaneously) with phonetic speech normalization for Indian English / accents.
- Always New Tab & Full Screen: Every task or URL opened in the browser always creates a brand new tab (never reusing or hijacking existing tabs) and always expands to Entire Screen (Full Screen) mode on macOS.
- Local LLM Direct Execution: Optimized `_system_prompt()` and Ollama options (`num_predict: 2048`, temperature floor 0.5) to prevent runaway thinking loops and ensure immediate native tool invocation.
- Mobile Remote web controller with Siri glassmorphic UI and public 5G Cloudflare tunnel.
- Full unit test suite (100 passing unit tests in `tests/`, Ollama fully mocked).
- Comprehensive A-to-Z handoff specification document `intro.txt` created for AI agent knowledge transfer.

## 5. Known Bugs & Solutions
- **Incomplete Task Flag on App Launch ("open whatsapp")**:
  - *Cause*: `_classify_stage()` unconditionally mapped any string containing `"whatsapp"` to `"messaging"`, and `_send_was_requested()` treated `"whatsapp"` as a message-send verb. For commands like `open whatsapp`, `_verify_task_completion()` appended a false "Nothing has been sent yet" prompt and set `phase="awaiting_clarification"`.
  - *Solution*: `_classify_stage()` now checks whether the command is an open/launch action without send verbs, and `_send_was_requested()` requires explicit send verbs (`send`, `text`, `message`, `msg`, etc.).
  - *State Reset*: Agent task state now resets completely (`phase="completed"`, clear `instruction`, `stage="other"`, etc.) upon completion, returning the CLI REPL cleanly to the ready prompt `Blacky 🐾 > `.
  - *Clarification Bailout*: Users can say `cancel`, `stop`, or `never mind` to immediately exit an `awaiting_clarification` state.
  - *UI Animation*: Keeps the progress spinner active during post-tool response synthesis (`Synthesizing response...`) instead of leaving an empty terminal line.

- **Unresponsive / Frozen on "open whatsapp and search for You and send a hello message"**:
  - *Cause*:
    1. `_check_fast_path` excluded any prompt with words like `" and "`, `" text "`, `" message "`, throwing multi-part deterministic WhatsApp commands to the local LLM.
    2. `qwen3:4b` has thinking hardcoded into its Modelfile template; with 40 tool schemas + 25KB system prompt + `temperature=0.2`, the 4B model entered an endless circular chain-of-thought loop generating 2,500+ tokens for over 2 minutes.
    3. The reasoning turn blocked synchronously without elapsed-time feedback, making the terminal appear completely frozen at `Analyzing with local AI (qwen3:4b)...`.
    4. `"You"` was not in `_SELF_CHAT_ALIASES` in `blacky/tools/whatsapp.py`, so the self-chat `(You)` / "Message yourself" was not recognized as a self-target.
  - *Solution*:
    1. Extended `_check_fast_path` with `_parse_whatsapp_fast_path` to extract and execute deterministic WhatsApp message sending and chat opening in <1s.
    2. Added `"you"` to `_SELF_CHAT_ALIASES`, broadened `_SELF_ROW_RE` to match timestamps, and added a keyboard Return fallback in `_open_self_chat`.
    3. Added `num_predict: 2048` and temperature floor (0.5) for thinking models in `OllamaProvider._options()` to prevent circular token degeneration.
    4. Added a live elapsed-second ticker in the screen-analysis spinner so the user sees live progress during any model turn.
    5. Added auto-revival of the Ollama server in `OllamaProvider.chat()`.

- **Fn and Option Dual Voice Triggers & Browser New Tab Mode**:
  - *Fn + Option Push-to-Talk*: `_is_fn_pressed()` and `_is_option_pressed()` in `blacky/voice/stt.py` detect both the physical Fn (Globe 🌐, keycode 63, flag `0x00800000`) and Option (⌥, keycodes 58/61, flag `0x00080000`) keys. `BLACKY_VOICE_TRIGGER=both` is enabled by default.
  - *Always New Tab & Entire Screen*: `_open_url_in_browser_app()` in `blacky/tools/web.py` was updated to discard tab reuse loops and explicitly execute AppleScript to `make new tab with properties {URL: url}`, followed by `make_window_fullscreen(target_app)`. Every URL or browser action now opens in a new tab and enters macOS Entire Screen mode.

- **Reasoning Monologue Leakage & WhatsApp Phrasing Fast-Path Bypass**:
  - *Cause*:
    1. Fast-path regexes in `_parse_whatsapp_fast_path` did not accommodate natural phrasing such as `"open the whatsapp text <contact> to <msg> and send him"` (required `"and"`, forbade `"the"`, lacked `"to"` as a message connector, and did not strip trailing execution directives like `"and send him"`).
    2. When falling back to Ollama `qwen3:4b`, passing `think=False` with tools caused Ollama to suppress `<think>` tags and dump raw chain-of-thought monologue directly into `message.content`, while failing or delaying native tool call emission.
    3. If the model wrote Python function call syntax in text (e.g. `whatsapp_send_message(contact="...", message="...")`), `_extract_json_tool_call` only accepted JSON `{...}` and ignored function syntax.
    4. `_verify_task_completion` prepended the 2000-token internal reasoning monologue to the "Nothing has been sent yet" note, dumping the entire chain of thought to the terminal.
  - *Solution*:
    1. Expanded `_parse_whatsapp_fast_path` with natural patterns covering `(?:the\s+)?whatsapp`, optional `and`, `(?:to|saying|that|with|:)` connectors, and stripped trailing `and send (him|it|her|them|this)` directives so queries like `"open the whatsapp text yash baniya to aaj game 9:30 bajje khelenege and send him"` execute instantly in 0.1s.
    2. Updated `_build_kwargs` in `OllamaProvider` so `think=False` is never passed to thinking-capable models when tools are present, keeping reasoning cleanly isolated inside `message.thinking`.
    3. Enhanced `_strip_inline_reasoning` and `_verify_task_completion` to detect and strip internal monologue prefixes (`Okay, let's see...`, `Okay, let's break down...`) from user-facing output.
    4. Upgraded `_extract_json_tool_call` with an AST-based Python function parser to automatically recover and execute tool calls even if a model prints them as `tool_name(arg="val")` in text.

- **WhatsApp Contact Matching: Y-Coordinate Retina Clipping & Character-by-Character Fuzzy Matching**:
  - *Cause*:
    1. In `_find_whatsapp_contacts()`, the sidebar Y filter checked `int(280 * scale) < py`. On Retina 2x displays (`scale = 2.0`), `280 * 2.0 = 560`. The top contact search results in WhatsApp appear at `py ≈ 428` pixels (below the search box at `py ≈ 200`), so `428 < 560` completely excluded the first contact from the OCR candidate list.
    2. Contact matching required full-word or exact equality; when progressive backoff typed `yash baniy` or the contact name differed in casing/character suffixes (`Yash Baniya`), it was not matched or clicked.
    3. The bottom boundary only checked for `Messages`, allowing rows under `Groups in common` to leak in as ambiguous candidates.
  - *Solution*:
    1. Adjusted `min_y` to `int(120 * scale)` (240 pixels in Retina), capturing all contact rows directly beneath the search bar.
    2. Added `cutoff_y` bounded by both `Groups in common` and `Messages` to restrict candidate detection strictly to the direct 1-on-1 `Chats` section.
    3. Implemented `_contact_match_score()` providing case-insensitive character-by-character prefix, substring, token subset, and SequenceMatcher fuzzy similarity scoring (0.0 to 1.0).
    4. Implemented `_resolve_whatsapp_candidates()` to automatically classify single matches or clear top-score winners (score >= 0.8 with >= 0.15 margin) as `EXACT` and click them directly via `mouse_click(lx, ly)`.

- **WhatsApp App Launch Check False Negative, Voice Search Fast-Path Bypass & Daemon Ticker Shutdown Crash**:
  - *Cause*:
    1. `_ensure_whatsapp_running()` in `blacky/tools/whatsapp.py` did not check the filesystem for `/Applications/WhatsApp.app` first; it relied purely on a 5-second `osascript` invocation and `make_window_fullscreen()`. If AppleScript encountered a temporary timeout or window resize permission delay, it threw an exception and returned `False`, causing `whatsapp_open_chat` to falsely report `"Could not open WhatsApp. Please ensure WhatsApp is installed in /Applications/WhatsApp.app."` even when WhatsApp was already installed and running.
    2. When the user followed up with a voice command like `now search for the blue` (voice transcription of `now search for Billu`), the command lacked the keyword `"whatsapp"`. Because `_parse_whatsapp_fast_path` previously required `"whatsapp"` in the prompt, the query bypassed fast-path and fell back to local LLM reasoning (`qwen3:4b`), blocking the REPL for 20-30s.
    3. When the user pressed `Ctrl+C` (`SIGINT`) to abort the long LLM reasoning turn, Python crashed with `Fatal Python error: _enter_buffered_busy: could not acquire lock for <_io.BufferedWriter name='<stdout>'> at interpreter shutdown` due to the background `_ticker` daemon thread attempting to print to stdout via Rich console during interpreter teardown.
  - *Solution*:
    1. In `blacky/tools/whatsapp.py`, updated `_ensure_whatsapp_running()` to verify app bundle presence directly at `/Applications/WhatsApp.app` or `~/Applications/WhatsApp.app`, increased AppleScript timeouts to 8.0s, and made `make_window_fullscreen` best-effort within try/except so window management hiccups never fail WhatsApp initialization.
    2. In `blacky/core/agent.py`, enhanced `_parse_whatsapp_fast_path` to strip conversational prefixes like `now`, `then`, `also`, and added contextual detection (checking if `stage == "messaging"`, previous tool call was `whatsapp_*`, or foreground app is WhatsApp). Added Pattern 12 to resolve contextual contact searches (`now search for <contact>`, `search for <contact>`, `find <contact>`, `open chat with <contact>`) instantly in 0.1s.
    3. In `blacky/core/agent.py`, wrapped `_ticker` thread loop and `update_screen_analysis` in exception handlers catching `(KeyboardInterrupt, SystemExit, Exception)` to cleanly exit and prevent stdout lock contention during interpreter shutdown.

- **Hinglish/Spoken WhatsApp Phrasing Fast-Path Bypass & Ollama Token Optimization on M2 8GB RAM**:
  - *Cause*:
    1. Spoken Hinglish commands like `"open whatsapp search avnish kal aaega cllg text huim and send"` bypassed fast-path because:
       a) `and` between `whatsapp` and `search` was mandatory in fast-path regexes (`open whatsapp search avnish` lacked `and`).
       b) The message body (`kal aaega cllg`) was spoken *before* the trailing send directive (`text huim and send`, with phonetic voice typo `huim` for `him`).
    2. When falling back to Ollama `qwen3:4b`, `OLLAMA_NUM_CTX` defaulted to 8192 (allocating 1.3GB KV cache in unified RAM) and `OLLAMA_NUM_PREDICT` was uncapped at 2048 tokens, causing Qwen3's thinking loop to generate hundreds of chain-of-thought tokens for 57+ seconds on Apple Silicon M2.
    3. User inquired about upgrading to a higher Ollama model (e.g. 7B/8B/14B) on an M2 Mac with 8GB RAM & 256GB SSD.
  - *Solution*:
    1. Added `_WA_MSG_START_WORDS` (covering Hindi/Hinglish message starters like `kal`, `aaj`, `kaha`, `bhai`, `sun`, `cllg`, etc. and English words) and `_split_whatsapp_target_and_message()` in `blacky/core/agent.py` to seamlessly parse target contact names and message bodies even when the message appears before trailing verbs.
    2. Made `and` optional `(?:and\s+)?` across all WhatsApp search & open regexes, and added support for trailing execution directives like `(?:and\s+)?text\s+(?:him|her|them|huim|it)?\s+and\s+send`.
    3. In `blacky/config.py` and `blacky/core/ollama_client.py`, optimized default context window `OLLAMA_NUM_CTX` from 8192 to 4096 (saving ~600MB RAM) and capped `OLLAMA_NUM_PREDICT` at 512 tokens for tool calling.
    4. Hardware confirmation: On an 8GB unified memory Mac M2, 4B (`qwen3:4b` at 2.5GB) is the optimal model size; 7B/8B models require 6-7GB in RAM which causes severe SSD disk swapping and token generation throttling.

- **Search Bar Voice Phrasings ("how/now in the search bar...") & False "Task step completed." on Empty Model Turns**:
  - *Cause*:
    1. Spoken voice commands like `"how in the search bar search for the Yash baniya"` (where STT heard "how" instead of "now", plus "in the search bar" location prefix) bypassed fast-path because `how` and `in the search bar` were not stripped from preambles, and the leading article `the` in `the Yash baniya` was not sanitized.
    2. When falling back to the local model turn, if the model generated no tool calls and produced only internal thinking (which was stripped), `response.text` was empty. Line 1184 previously did `final_text = response.text or "Task step completed."`, falsely declaring "Task step completed." without actually executing any action.
    3. `_extract_json_tool_call` only checked already-stripped text, missing tool calls written inside raw text or `<think>` tags.
  - *Solution*:
    1. In `blacky/core/agent.py`, added preamble stripping for `how`, `now`, `goto`, and search-bar prefixes (`in/on/into/through/using the search bar`).
    2. Added `_clean_contact()` to strip leading articles (`the`, `a`) and trailing location mentions (`on whatsapp`, `in search bar`) so `the Yash baniya` correctly resolves to `Yash baniya`.
    3. In `blacky/core/ollama_client.py`, enhanced tool call recovery in `_normalize_reply` to inspect raw message content and thinking tags before fallback.
    4. In `blacky/core/agent.py`, prevented false "Task step completed." claims by checking `self._turn_tool_calls`: if no tool ran and no text was produced, Blacky reports honestly that no action was executed and asks for clarification.

## 6. Known Quirks / Heuristics
- WhatsApp automation must always run in full screen mode and use `whatsapp_*` tools exclusively (never Apple Messages).
- TTS output is strictly operational (<160 chars); never reads back long message bodies or generated code.
- Screen capture files are kept in `/tmp/` to avoid polluting the workspace.

## 7. Pending Tasks & Next Steps
- Maintain tool compatibility across new macOS updates and third-party web interface changes.
- Local STT is optional: install `faster-whisper` and it is used automatically; otherwise the existing SpeechRecognition engine is used.
