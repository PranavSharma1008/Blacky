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
- Screen Analyzing Mode & Automated MCQ Paper Solver: Native macOS Menu Bar status bar item (`sparkles.tv` SF Symbol / `🐾`) + compact movable floating chatbot companion window (`390x600` WKWebView / Chrome `--app` fallback at `http://127.0.0.1:8010/screen`). Replaces the old giant 1200x820 desktop window. Floats over any application (`NSFloatingWindowLevel`), can be dragged anywhere, hides into the Menu Bar on close, toggles via Menu Bar click, and temporarily conceals itself for 40ms during display captures to prevent window occlusion and recursive screenshots. Solves MCQs step-by-step with live SSE streaming cards, answers custom screen/code analysis commands, and includes running app detection. Supported via CLI (`blacky --screen`), launcher menu (`./blacky.sh [7]`), and instant fast-path (`activate screen analyzing mode`).
- Automatic Ollama startup & auto-revival: `./blacky.sh`, `blacky` CLI, and `OllamaProvider.chat()` automatically check and revive Ollama in the background if it is not running.
- Direct Intent Fast-Path: High-frequency deterministic OS actions (`open whatsapp`, `open chrome`, `open spotify`, etc.) and WhatsApp operations (`open whatsapp and search for You and send a hello message`, `send hello to X on whatsapp`, `text X on whatsapp Y`, etc.) execute instantly (0.1s) without waiting for 30s+ local LLM token reasoning on Apple Silicon M2.
- 6 complete tool suites: Filesystem, Terminal, Web & Browser, macOS System Control, WhatsApp Desktop, Mobile Control.
- Global Option & Fn key push-to-talk voice mode (both [Fn] Globe 🌐 and [Option] ⌥ keys work simultaneously) with phonetic speech normalization for Indian English / accents.
- Smart Tab Reuse & Full Screen: If a requested site or web app (e.g. Blinkit, YouTube, GitHub, portfolio) is already open in an existing tab, Blacky brings that tab and window to front in Entire Screen mode without creating duplicate tabs. A brand new tab is ONLY opened if the user explicitly specifies 'in a new tab' / 'new tab', or if the site is not currently open.
- Local LLM Direct Execution: Optimized `_system_prompt()` and Ollama options (`num_predict: 2048`, temperature floor 0.5) to prevent runaway thinking loops and ensure immediate native tool invocation.
- Mobile Remote web controller with Siri glassmorphic UI and public 5G Cloudflare tunnel.
- Command Simplifier & Natural Language Intent Distiller: Preprocesses verbose, rambling, multi-clause, repetitive voice-dictated prompts across all domains (YouTube, Web Search, WhatsApp, LeetCode, Filesystem) into direct canonical instructions (e.g. `play bulleya song on youtube in Brave Browser`). Displays `🎯 Simplified Intent:` to the user and triggers instant Fast-Path execution (<0.2s) without LLM delay.
- Media & Search Fast-Path with Browser Routing: Dedicated deterministic fast-path (`_parse_media_fast_path`) supporting song/query extraction, Hindi play suffixes (`chalao`, `bajao`, `sunao`), search engines (`youtube`, `google`, `duckduckgo`), explicit browser targeting (`in Brave Browser`, `in Google Chrome`), and app launch precedence (`_KNOWN_APPS`).
- Full unit test suite (141 passing unit tests in `tests/`, Ollama fully mocked).
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

- **Slang / Conversational Preambles ("ya i need...") Bypassing Fast-Path & 11s+ Local Model Delay**:
  - *Cause*:
    1. User inputs starting with conversational prefixes or slang (e.g. `ya i need open the whatsapp and text to yash that "..." and send him`, `yeah i need to...`, `can you open chrome`) bypassed the instant deterministic Fast-Path because `ya`, `yeah`, `yes`, `yup`, `i need (to)`, `i want (to)`, `i have to`, `can/could/will/would you` were not in the preamble stripping regex.
    2. Missing leading preposition handler in `_clean_contact`: phrases like `text to yash` retained `to` in the target contact name (`to yash`).
    3. When fast-path missed, the request fell back to the local LLM (`qwen3.5:4b`) via Ollama. Small local models running on unified RAM (Apple Silicon M2) must ingest all ~40 tool schemas + system prompt, and generate chain-of-thought thinking tokens before outputting tool calls, taking 10-20+ seconds for a single turn.
  - *Solution*:
    1. Expanded preamble normalization regex across WhatsApp and App Open fast-paths in `blacky/core/agent.py` to strip all conversational fillers (`ya`, `yeah`, `yes`, `yup`, `i need (to)`, `i want (to)`, `have to`, `can/could/will/would you`, `hey/ok/okay blacky`, `kindly`, etc.).
    2. Updated `_clean_contact()` to strip leading prepositions (`to`) and normalized curly/smart quotes in `_clean_msg()`.
    3. Enhanced Pattern 4 and added Pattern 4b in `_parse_whatsapp_fast_path` to handle direct quotes (`text yash "..."`), connectors (`that`, `to`, `saying`), and message-first Hinglish splits without requiring explicit search verbs.
    4. Direct commands like `"ya i need open the whatsapp and text to yash that \"...\" and send him"` now execute immediately via Fast-Path in <0.2s without waiting for the local LLM.

- **Smart Tab Reuse vs. Explicit New Tab & MallocStackLogging Terminal Warning**:
  - *Cause*:
    1. Previous policy unconditionally created a brand new tab for every URL or web app opened (`open blinkit`, `open github`, `open portfolio`), cluttering the browser with duplicate tabs when the site was already open.
    2. Missing support for user's explicit directive 'open in a new tab'.
    3. macOS dynamic linker output `Python(...) MallocStackLogging: can't turn off malloc stack logging because it was not enabled.` when Python and child processes executed `osascript`.
  - *Solution*:
    1. Updated `_open_url_in_browser_app()`, `open_in_browser()`, and `open_application()` to check `_bring_site_to_front()` first when `new_tab=False`. If already open in any window/tab, brings that tab to the front in Entire Screen mode.
    2. Added `new_tab` detection across fast-paths and tool callers so queries specifying 'in a new tab' / 'new tab' create a brand new tab.
    3. Cleared `MallocStackLogging` and `MallocStackLoggingNoCompact` environment variables in `blacky/main.py` and `blacky/tools/macos.py`, eliminating the stderr warning.
    4. Reinforced doubt and clarification rule in `blacky/core/prompts.py`: when instructions are clear, execute directly; when in doubt or when options are ambiguous, ask first before acting.

- **Filesystem & Mac Tasks Freeze (143s), Context Truncation & MallocStackLogging Output**:
  - *Cause*:
    1. Huge Prompt Overload: `SYSTEM_INSTRUCTION` (6,606 tokens) + 40 tool schemas (4,511 tokens) totaled 11,118 tokens! In `config.py`, `OLLAMA_NUM_CTX = 4096`. Sending 11,118 tokens into 4,096 context truncated 60% of instructions and tools, caused severe KV cache thrashing and 130s+ prefill lockup on Apple Silicon unified RAM, and caused `qwen3.5:4b` to return empty tool calls `[]` and empty text.
    2. Thinking Parameter Suppression: `_build_kwargs()` in `blacky/core/ollama_client.py` suppressed `think=False` when tools were present (`if tools and think is False: pass`), forcing Ollama to use `thinking: true` default, generating hundreds of useless chain-of-thought tokens.
    3. Path Resolution: `_resolve_path` in `blacky/tools/filesystem.py` resolved relative paths strictly against `config.BASE_DIR` instead of user special folders (`~/Desktop`, `~/Downloads`, `~/Documents`).
    4. MallocStackLogging: Calling `os.environ.pop("MallocStackLogging", None)` inside Python triggered libc's dynamic linker warning `can't turn off malloc stack logging because it was not enabled`.
  - *Solution*:
    1. Dynamic Tool Routing: Implemented `_filter_tools_for_request()` in `blacky/core/agent.py` to route tools by domain (filesystem, terminal, web, whatsapp, macos, mobile), reducing active tool schemas from 40 down to ~8-12 tools (<800 tokens).
    2. Compact Local System Instruction: Added `LOCAL_SYSTEM_INSTRUCTION` (~300 tokens) in `blacky/core/prompts.py`, dropping total turn input from 11,118 tokens to ~1,100 tokens (fits easily within 4096 context, 10x faster prefill in 1-2s).
    3. Direct Tool Invocation: Removed thinking suppression in `_build_kwargs()`, allowing `think=False` to be sent to Ollama so `qwen3.5:4b` immediately generates native tool calls in ~15-18s instead of 140s+.
    4. Special Directory Resolution: Updated `_resolve_path()` in `blacky/tools/filesystem.py` to intelligently map `desktop/...`, `downloads/...`, and `documents/...` to user home directories (`~/Desktop`, `~/Downloads`, `~/Documents`).
    5. Filesystem & Algorithm Fast-Path: Added `_parse_filesystem_fast_path()` in `blacky/core/agent.py` with standard algorithm templates (Binary Search, Bubble Sort, Linear Search, Hello World in Java, Python, C++, JS) and folder/file creators that execute in <0.05s.
    6. Malloc Warnings Silenced: Added `unset MallocStackLogging MallocStackLoggingNoCompact` to `blacky.sh` before Python starts, and removed `os.environ.pop()` from `blacky/main.py`.

- **Filesystem Phrasing Miss (48s), Redundant Second LLM Turn & False "Nothing has been sent yet" Messaging Prompt**:
  - *Cause*:
    1. Fast-Path Regex Rigidness: When the user commanded `in desktop make me a text file name b.txt inside that binary search code in java language`, `_parse_filesystem_fast_path` missed because:
       a) Regex only matched `make a file` (failed on `make me a text file`).
       b) Only matched `inside this` or `with` (failed on `inside that`).
    2. Redundant Second LLM Call: Falling back to local `qwen3.5:4b` on Apple Silicon M2 Air, the model generated 1,402 bytes of Java code in tool arguments (~25s). After `write_file` executed, `_run_agent_turn` called `_send_model_turn()` a second time with all tools and conversation history just to synthesize an explanation, adding another 20s (totaling 48s).
    3. False Messaging Stage Bug: In `_classify_stage()`, matching `"text "` inside `"text file"` erroneously classified the task as `"messaging"`. Consequently, `_send_was_requested()` treated it as an unfulfilled message request and `_verify_task_completion()` falsely appended: *"Nothing has been sent yet — I stopped before messaging anyone. Tell me the contact name..."* and entered `awaiting_clarification`.
  - *Solution*:
    1. Natural Filesystem Fast-Path: Overhauled `_parse_filesystem_fast_path` regex to flexibly handle `make [me] [a] [new] [text/code/java/python] file [name/named/called] <fn>`, flexible connectors (`inside that/this/it`, `with`, `containing`, `having`, `and put/write`), and empty files. Execution dropped from 48s to 0.02s (<50ms).
    2. Additional Algorithm Templates: Added Quick Sort, Fibonacci, and Factorial in Java & Python to `_ALGORITHM_TEMPLATES` and `_detect_algorithm_template`.
    3. Stage Classification & Send Sanitization: Updated `_classify_stage()` and `_send_was_requested()` to classify file operations as `file_task` and sanitize phrases like `text file` or `text document`, preventing false messaging triggers.
    4. Domain Keyword Pruning: Refined `_DOMAIN_KEYWORDS` to prevent `text file` from loading WhatsApp tools.
    5. Direct Completion for Deterministic Action Tools: Added `_DIRECT_COMPLETION_TOOLS` (`write_file`, `create_folder`, `edit_file`, `delete_item`, `make_window_fullscreen`, etc.) to directly report success without burning a redundant 20s second LLM turn, cutting fallback LLM response time in half.

- **Segmentation Fault (SIGSEGV) in mouse_click & LeetCode Problem Search, Solve & Submit Automation**:
  - *Cause*:
    1. 64-bit Pointer Truncation Crash: In `blacky/tools/macos.py`, `mouse_click(x=-1, y=-1)` invoked `cg.CGEventCreate(None)` without declaring `cg.CGEventCreate.restype = ctypes.c_void_p`. On 64-bit ARM64 macOS, ctypes defaulted to 32-bit `c_int`, truncating the 64-bit pointer address (e.g. `0x60000155d3c0` -> `0x0155d3c0`). Passing this invalid pointer into `cg.CGEventGetLocation(ev)` triggered an unmapped memory read in `SLEventGetLocation`, causing an instant segmentation fault (`EXC_BAD_ACCESS: SIGSEGV: 11`).
    2. LeetCode Landing Page Deadlock: When commanded `open leetcode and search for two sum ques and solve it and submit it`, Blacky navigated only to the marketing landing page `https://leetcode.com`. The local LLM attempted `screen_click_text('Search')` which failed because no search button was visible on the unauthenticated marketing page, and then called vision/mouse tools that crashed.
  - *Solution*:
    1. ctypes 64-bit Pointer Safety: Explicitly declared `cg.CGEventCreate.restype = ctypes.c_void_p`, `cg.CGEventCreate.argtypes = [ctypes.c_void_p]`, added null checks, and properly released event objects using `cf.CFRelease()`.
    2. LeetCode Direct Automation Tool: Implemented `leetcode_problem()` in `blacky/tools/web.py` with automatic problem slug extraction (e.g. `two sum ques` -> `https://leetcode.com/problems/two-sum/`), built-in optimal solution database, desktop file saving (`~/Desktop/two_sum_leetcode_solution.txt`), macOS clipboard injection (`pbcopy`), and automated editor pasting and LeetCode submission (`Cmd+'`).
    3. LeetCode Direct Fast-Path: Added Pattern 5 in `blacky/core/agent.py` to recognize LeetCode problem search, solve, and submit commands, executing the full workflow end-to-end in <0.5s.
    4. Mapped LeetCode across `_WEB_APP_URLS` and `browser_search`.

- **Screen Analyzing Mode & MCQ Paper Solver Automation**:
  - *Context & Request*: User required a dedicated screen analyzing mode where a new terminal-style app window opens (`--app` chromeless window) to work through MCQ papers (solve one MCQ, click Next, then solve the next, repeating throughout the paper) and handle screen instructions (`analyze my screen and based on my code do the task`).
  - *Identified Issues*:
    1. Vision Model Status False-Negative: Even though Ollama's local `qwen3.5:4b` reports `capabilities: ['completion', 'vision', 'thinking', 'tools']`, `vision_status()` returned `False` whenever `OLLAMA_VISION_MODEL` was empty in `.env`, falsely blocking screen mode.
    2. Activation Phrase Miss: Natural commands like `activate screen analyzing mode`, `screen mode`, `open screen mode` in REPL/Voice were not intercepted in fast-path; they either bypassed to LLM or attempted static synchronous terminal OCR without launching the dedicated window.
    3. UI Static Wait: In `screen.html`, solving MCQs blocked until all questions finished, with no live streaming of question cards or clicking progress.
    4. Target App Context: Capturing the screen while the chat window was in front risked occluding the sample paper when `target_app` was unset.
  - *Solution*:
    1. Automatic Vision Capability Inheritance: In `blacky/core/ollama_client.py`, added auto-detection of `vision` capability on the active primary model (`self.model`) if `OLLAMA_VISION_MODEL` is empty, ensuring vision readiness out of the box.
    2. Instant Activation Fast-Path: In `blacky/core/agent.py`, added regex fast-path for `activate screen analyzing mode`, `screen mode`, `open screen mode`, etc. Calling `ensure_screen_mode_active()` spawns the local server on port 8010 in a background daemon thread and opens the standalone Chrome/Brave app window.
    3. Real-Time SSE Streaming: Added `/api/screen/mcq/stream` in `blacky/web/server.py` and `on_question_solved` callback in `ScreenSession.solve_mcqs()`. Solved questions stream live to `screen.html`, rendering custom MCQ cards with highlighted correct choices, reasons, and next-click confirmations in real time.
    4. Extended Next Labels & Robust Option Matching: Added `Submit & Next`, `Save & Next Question`, `Next >`, `Proceed` to `NEXT_LABELS`, and candidate option matching with letter prefixes (`B. Paris`, `B) Paris`, `(B) Paris`, `B`) in `_click_option()`.
    5. Dynamic Target App Selection: Implemented `/api/screen/apps` to list visible macOS running applications (`Google Chrome`, `Brave Browser`, `Safari`, `Preview`, etc.) in a dropdown, and auto-activation in `activate_app()` when set to `Auto`.
    6. Sub-Second Vision Turns: Set `think=False` on `_ask_vision()` calls, reducing MCQ evaluation turns from 30s+ down to ~1-2s.

- **Screen Analyzing Mode Overhaul: Native Menu Bar Status Item & Floating Movable Companion Chatbot (Replaces Giant 1200x820 Window)**:
  - *Cause*:
    1. The old Screen Analyzing mode launched a giant 1200x820 desktop window that occupied 85-90% of the display and obstructed whatever IDE, browser, or exam the user had open.
    2. Because the window was huge, screen captures took pictures of the Blacky window itself in an infinite hall-of-mirrors recursion loop.
    3. The UI had a giant split pane (left preview taking up half the screen) and lacked Menu Bar integration (no status bar icon like Comet/Ollama in the macOS menu bar).
    4. Unhandled server exceptions during screen analysis returned raw HTTP 500 errors to the UI.
  - *Solution*:
    1. Implemented native macOS Menu Bar Companion in `blacky/web/companion.py` using Cocoa `AppKit.NSStatusBar` with SF Symbol `sparkles.tv` (or `🐾`). Left-clicking toggles the floating chatbot window; right-clicking provides contextual actions ("Toggle Chatbot", "Analyze Screen", "Solve MCQs", "Target App", "Quit").
    2. Built a compact floating companion window (`NSWindow` + `WKWebView` at `390x600`) with `NSFloatingWindowLevel` (floats on top of all apps) and `setMovableByWindowBackground_(True)` (draggable from anywhere on its background/header).
    3. Completely redesigned `blacky/web/static/screen.html`: removed the giant split pane and left preview; replaced with a modern glassmorphic chat stream, quick action pills (`👁️ Analyze Screen`, `🎯 Solve MCQs`, `💻 Explain Code`), target app selector, streaming MCQ cards with green highlight and explanations, and drag handle.
    4. Implemented `companion_capture_guard()` in `blacky/core/screen_mode.py` to momentarily hide the companion window (40ms) during `screencapture`, ensuring 100% clean display capture of underlying apps without occlusion or self-recursion.
    5. Added try/except error boundaries in `blacky/web/server.py` to eliminate HTTP 500 crashes and added dynamic vision status refresh in `ScreenSession.status()`.

- **Hinglish Understanding ("whatsapp kkhol yash baniya ko message kr...") & Pending Task Continuation on Disambiguation**:
  - *Cause*:
    1. Fast-Path Missing Hindi/Hinglish Grammar & Words: Commands like `ok whatsapp kkhol yash baniya ko message kr kosish krung aaj aa paya toh game kyuki nalr ha` bypassed fast-path because `kkhol` / `khol` / `kholo` (open), `ko` (to), `message kr` / `bhej` (send), and Hinglish words like `kosish` / `osish` (try), `krung` (will do), `nalr` (idle/free) were not recognized.
    2. Model Vocabulary Gap on Fallback: When falling back to `qwen3.5:4b`, the English-biased 4B model misinterpreted `kkhol` as a contact name and executed `whatsapp_open_chat(contact='kkhol')` and `whatsapp_send_message(contact='kkhol', ...)` which failed.
    3. Premature Target Splitting: In `open whatsapp text yash baniya osish krung...`, `tokens[1]` was `baniya` and `tokens[2]` was `osish` (neither in the old start word list). The parser defaulted to `tokens[0]` as contact (`yash`), pushing `baniya` into the message and triggering an ambiguous match (`Yashika G2` vs `Yash Baniya`).
    4. Pending Action & Disambiguation State Erasure: When `AMBIGUOUS_CONTACTS` occurred, `_handle_ambiguous_result` and `_run_agent_turn` wiped `self.task_state["pending_action"] = None` and `self.task_state["pending_candidates"] = []`. When the user answered `yash baniya`, Blacky sent a vague prompt to `qwen3.5:4b` (`User answered: "yash baniya". Finish original task now.`), which hung for 39s on M2 unified RAM and failed to send the pending message.
  - *Solution*:
    1. Expanded `_WA_MSG_START_WORDS` with comprehensive Hinglish vocabulary (`koshish`, `kosish`, `osish`, `krung`, `krunga`, `karunga`, `paya`, `paunga`, `nalr`, `nalle`, `bhaiya`, `yaar`, `bunk`, `lecture`, `khelenge`, `game`, `bol`, `bata`, `bhej`) and common English verbs/pronouns.
    2. Overhauled `_split_whatsapp_target_and_message`: supports `<contact> ko message/bhej <msg>`, explicit connectors (`to`, `saying`, `that`, `ki`, `ke`), and scans tokens for the first message start word up to index 4, resolving 2-to-3 word Indian names (`yash baniya`) cleanly.
    3. Enhanced `_parse_whatsapp_fast_path` with Hindi/Hinglish patterns H1-H4 (`whatsapp (kkhol|khol) <contact> ko (message|msg|text|send|bhej) (kr|kar|de|do) <msg>`, `whatsapp pe <contact> ko message kar <msg>`, `yash baniya ko whatsapp pe bhej <msg>`).
    4. Supported Hindi app opening (`chrome kholo`, `spotify chalao`, `khol chrome`).
    5. Preserved Pending Context: Updated `_handle_ambiguous_result` to store `self.task_state["pending_action"]` and populate `self.task_state["pending_candidates"]` with candidate names and OCR coordinates. Prevented turn cleanup from wiping `pending_action` while in `awaiting_clarification`.
    6. Instant Disambiguation Execution & Multi-Op Chaining: In `_handle_clarification_answer`, resolved candidate answers (`yash baniya`, `second one`, `2`) immediately execute the pending action directly (`whatsapp_send_message` with the saved message) in <0.2s without waiting 39s for the LLM. If the user also specified a subsequent action (e.g. `yash baniya and open chrome`), Blacky completes the pending message first and then executes the next operation.
    7. Updated `LOCAL_SYSTEM_INSTRUCTION` in `blacky/core/prompts.py` with Section 6 teaching `qwen3.5:4b` Hinglish grammar and never confusing Hindi verbs (`kkhol`, `bhej`, `kr`) with contact names.

- **WhatsApp Hindi/Hinglish Phrasing ("kkhol", "ko message kr"), Ambiguity Disambiguation Fast-Path & OllamaProvider think Parameter Bug**:
  - *Cause*:
    1. `TypeError: OllamaProvider.chat() got an unexpected keyword argument 'think'`: In `blacky/core/screen_mode.py`, `_ask_vision()` passed `think=False` to `self.provider.chat()`, but `OllamaProvider.chat()` and `stream_chat()` did not accept `think` in their keyword signatures, raising an uncaught `TypeError`.
    2. Hindi/Hinglish verb parsing (`kkhol`): In `ok whatsapp kkhol yash baniya ko message kr kosish krung...`, `Pattern 9` in `_parse_whatsapp_fast_path` (`r"^whatsapp\s+(?:to\s+)?(.+?)\s*[:\s]\s*(.+)$"`) matched the space after `kkhol`, falsely capturing `kkhol` (Hindi "open") as the recipient contact name instead of the action verb.
    3. Multi-word contact truncation & message splitting: In `_split_whatsapp_target_and_message`, words like `osish` (typo for `kosish`), `krung`, `toh`, `nalr` were missing from `_WA_MSG_START_WORDS`. The fallback logic greedily assumed contact names are only 1 word, splitting `yash baniya ...` into contact `yash` and message `baniya osish...`, which caused WhatsApp to report `AMBIGUOUS_CONTACTS` (`Yashika G2`, `Yash Baniya`).
    4. Disambiguation state loss & wrong message sent: In `_handle_ambiguous_result`, `pending_candidates` was set to `[]` and `pending_action` was wiped out. When the user clarified with `yash baniya`, `_resolve_pending_answer` could not match candidates, so it dumped a generic prompt into a 98-second local LLM turn (`qwen3.5:4b`) without the original message text, causing the model to hallucinate and send `message='Thanks!'` to Yash Baniya.
  - *Solution*:
    1. Added `think: bool | None = None` to `OllamaProvider.chat()`, `stream_chat()`, and `_build_kwargs()` in `blacky/core/ollama_client.py` and updated test doubles.
    2. Overhauled `_split_whatsapp_target_and_message` and added rich Hindi/Hinglish vocabulary to `_WA_MSG_START_WORDS` (`koshish`, `kosish`, `osish`, `krung`, `krunga`, `karunga`, `arha`, `toh`, `kyuki`, `nalr`, etc.). For multi-token sentences (>= 4 words), contact names now preserve Indian two-word formats (`Yash Baniya`).
    3. Added dedicated Hindi fast-path patterns in `_parse_whatsapp_fast_path` covering `(?:open|khol|kkhol|kholo)? whatsapp (pe)? <contact> ko (message|msg|text|bhej|bol) (kr|kar|karo)? <msg>` and chat openers (`<contact> ki chat khol`).
    4. Refactored Pattern 9 in `_parse_whatsapp_fast_path` to require a colon, connector, or quotes instead of matching on any bare whitespace.
    5. Preserved `pending_action` (`tool`, `args`) and parsed candidate names (`['Yashika G2', 'Yash Baniya']`) inside `_handle_ambiguous_result`.
    6. Updated `_handle_clarification_answer`: when the user clarifies the ambiguous contact (e.g. `yash baniya`), Blacky instantly updates the contact and executes the pending send or open tool directly via fast-path without invoking the local LLM or hallucinating.

- **LeetCode Phrasing Miss ("4. Median of Two Sorted Arrays solve this on leetocde in java"), Typo Support & Missing Java Solutions**:
  - *Cause*:
    1. Rigid Regex Ordering & Missing Typos: In `blacky/core/agent.py`, the LeetCode regex strictly required the command to begin with `open leetcode ...` or `search for ...`. Commands specifying the problem first (e.g. `4. Median of Two Sorted Arrays solve this on leetocde and submit in java language`) missed the regex completely. Furthermore, typos like `leetocde`, `leetcdoe`, `leatcode`, question numbering prefixes (`4. `, `Q. 1`, `#4`), and language specifications (`in java language`) were not supported.
    2. Missing Tool Schema in Domain Router: `_TOOL_DOMAINS["web"]` and `_CORE_TOOLS` omitted `leetcode_problem`. When the fast-path missed and fell back to `qwen3.5:4b`, the model was not provided `leetcode_problem` schema and entered a 58+ second circular reasoning freeze.
    3. Missing Problem 4 Solution & Slug Numbering: `_LEETCODE_SOLUTIONS` lacked the optimal solution for `median-of-two-sorted-arrays` in Java, Python, and C++, and `leetcode_problem` slug generator did not strip leading numbering prefixes (`4.`), causing it to generate invalid slugs like `4-median-of-two-sorted-arrays`.
  - *Solution*:
    1. Implemented dedicated `_parse_leetcode_fast_path` in `blacky/core/agent.py` supporting problem-first syntax, numbering stripping (`4.`, `Q. 1`, `#4`), LeetCode typos (`leetocde`, `leetcdoe`, `leatcode`, `letcode`, `leetcde`), and language detection (`java`, `python`, `cpp`, `javascript`).
    2. Added `leetcode_problem` to `_TOOL_DOMAINS["web"]`, `_CORE_TOOLS`, `_DIRECT_COMPLETION_TOOLS`, and `_DOMAIN_KEYWORDS["web"]`.
    3. Added optimal binary-search $O(\log(\min(m, n)))$ solutions for `median-of-two-sorted-arrays` across Java, Python, and C++, as well as Java solutions for `3sum`, `valid-parentheses`, and `reverse-linked-list` in `_LEETCODE_SOLUTIONS`.
    4. Updated `leetcode_problem` in `blacky/tools/web.py` to strip question numbering from slugs and respect the explicitly requested `language` parameter.

- **Voice Dictation Ramblings & Rigid Media Regex Bypassing Fast-Path (18s+ Model Hang)**:
  - *Cause*:
    1. When spoken input contained multi-step explanations and repetitive conversational clauses (e.g. `"I have a task that you have to open the brave and search for the YouTube and inside the YouTube you have to search for the bulleya song and I have to that you have to play it song and play that song bulleya"`), the command failed the rigid single-step fast-path checks and fell back to the local LLM (`qwen3.5:4b`), causing an 18s+ freeze.
    2. In `agent.py`, the old regex `m_play = re.match(r"^(?:please\s+)?play\s+(.+?)(?:\s+on\s+youtube)?$", clean_lower)` failed to strip trailing browser directives (`in brave browser`), capturing the entire phrase into `query` and failing to pass `browser=browser` to `youtube_play`.
    3. In `web.py`, `_resolve_browser_app` unconditionally returned `get_default_browser()`, ignoring user-specified browsers.
    4. In `_parse_media_fast_path`, Hindi play verb `<query> chalao` clashed with app launch `<app> chalao` (e.g. `spotify chalao`).
  - *Solution*:
    1. Implemented `CommandSimplifier` in `blacky/core/simplifier.py` to distill rambling multi-clause instructions across media play, web search, WhatsApp, LeetCode, and conversational preambles.
    2. Integrated `CommandSimplifier` at the start of `agent.run()`, printing `🎯 Simplified Intent:` to the UI.
    3. Implemented `_parse_media_fast_path` in `blacky/core/agent.py` to parse query, target browser, and site cleanly for YouTube play and search queries, while checking `known_apps` to prevent collision with app launches (`spotify chalao`).
    4. Updated `_resolve_browser_app` in `blacky/tools/web.py` to honor explicitly requested browsers (`Brave Browser`, `Google Chrome`, `Safari`, etc.).
    5. Added 11 unit tests in `tests/test_simplifier.py`, bringing total test suite to 131 passing tests.

- **WhatsApp Infinite Disambiguation Loop ("Satyam" vs "Satyam Brother"), Chained Command Fast-Path Bypass & Pattern 11 Regex**:
  - *Cause*:
    1. In `_contact_match_score()` in `blacky/tools/whatsapp.py`, `"Satyam Brother"` scored ~0.939 against query `"Satyam"`. In `_resolve_whatsapp_candidates()`, top candidate `"Satyam"` scored 1.0, but the score margin `1.0 - 0.939 = 0.061 < 0.15` triggered `AMBIGUOUS_CONTACTS`. When the user confirmed with `"Satyam"` or `"text to Satyam"`, the search re-evaluated against the exact same candidates with margin `< 0.15`, entering an infinite clarification loop.
    2. In `_handle_clarification_answer()` in `blacky/core/agent.py`, `self.task_state["phase"] = "executing"` was set prior to executing a chained command (e.g. `yash baniya and open chrome`). When `self.run(next_instruction)` was invoked, `continuing_task` evaluated to `True`, which bypassed `_check_fast_path(next_instruction)` and dropped into a raw model turn.
    3. In `_parse_whatsapp_fast_path`, Pattern 11 (`r"^(?:open\s+)?{_WA}\s+search\s+..."`) lacked `(?:and\s+)?` between `{_WA}` and `search`. Queries like `"open whatsapp and search for Satyam"` failed Pattern 11 and fell through to Pattern 13, misinterpreting `"and search for Satyam"` as the contact name.
  - *Solution*:
    1. In `blacky/tools/whatsapp.py`, updated `_resolve_whatsapp_candidates()` with explicit exact-match evaluation (`is_exact(cand)`) before fuzzy margin scoring. If exactly one candidate matches the full query name and no peer variant exists (multi-word extensions like `Satyam Brother` are not peer variants of single-word `Satyam`), it returns `("EXACT", [exact_cand])` immediately. Conversely, if a peer candidate has identical word count with character transposition/typos (`Satyam` vs `Satyma`) or multiple exact duplicates exist, it returns `AMBIGUOUS` and asks the user.
    2. In `blacky/core/agent.py`, added `self._reset_task_state()` prior to calling `self.run(next_instruction)` in `_handle_clarification_answer()`, allowing chained commands (e.g. `yash baniya and open chrome`) to execute cleanly via fast-path.
    3. In `blacky/core/agent.py`, added optional `(?:and\s+)?` to Pattern 11 regex in `_parse_whatsapp_fast_path`.
    4. In `_resolve_pending_answer()`, added verb/preposition stripping (`text`, `send`, `to`, `with`, `for`, `bhai`, `ko`) and trailing markers (`ko`, `pe`, `bhej`, `kar`), prioritizing exact string matches before substring matches and resolving ordinals (`first`, `second`, `2nd one`).
    5. Clean Test Double Separation: Made `FakeProvider` inherit from `OllamaProvider` in `tests/test_agent.py` and restored `if not isinstance(self.provider, OllamaProvider): return None` in `_check_fast_path()`. This isolates `ScriptedProvider` in `test_ollama.py` to test the LLM tool loop, confirmation gates, and error handlers without fast-path hijacking, while allowing fast-paths to run across all other test suites and production.

- **Floating Companion Window Pure Chat Redesign & Unconstrained Full Autonomous Execution**:
  - *Context & Request*: User requested removing all extra UI elements from the Blacky Companion window (MCQ pills, question quantity selectors, Auto-Next, and app selectors) to make it a pure, distraction-free floating chat companion ("only a chat message only") that automatically does all work without artificial limits ("there is no limit of doing the work i need it can do automatically all work").
  - *Identified Issues*:
    1. UI Clutter: `screen.html` contained redundant exam-solver controls (`.quick-bar` with Analyze Screen, Solve MCQs, Explain Code; `#mcqPanel` with Qty: 10, Auto-Next, Run Solver; and `#targetApp` dropdown) taking up screen space and distracting from general desktop automation.
    2. Companion Keyword Hijacking Trap: In `blacky/web/server.py` (`/api/screen/chat`), a 15-word `screen_keywords` filter (`find`, `code`, `tell`, `what`, `see`, `read`, `look`, `error`, etc.) hijacked every normal English command into a static screenshot analysis (`_screen_session().analyze()`), preventing `BlackyAgent.run()` from executing actual tools.
    3. Premature Focus Stealing: `activate_app(req.target_app)` at the start of `/api/screen/chat` forcibly activated browsers even when commands targeted WhatsApp, desktop apps, or system tasks.
    4. Execution Hop Limit: `BLACKY_MAX_TOOL_HOPS` defaulted to 8, which could limit multi-step automated workflows.
    5. Typo Vulnerability: Commands with voice typos like `serch` (e.g. `open whatsapp and serch velocity and send him thanks message`) bypassed fast-paths.
  - *Solution*:
    1. Pure Chat Floating UI: Overhauled `blacky/web/static/screen.html` into a minimalist glassmorphic floating chat companion. Removed the quick-bar, MCQ settings panel, and app dropdown. Streamlined the draggable header to brand dot, `BLACKY`, active model badge (`qwen3.5:4b`), clear chat button `🗑`, and close button `✕`. Dedicated 100% of the body to chat messages with markdown, tool execution tags, status indicator, and prompt input.
    2. Removed Keyword Trap in `/api/screen/chat`: Only explicit visual inspection commands (`analyze screen`, `what is on my screen`) trigger `_screen_session().analyze()`; all general commands execute directly through `get_screen_agent().run(prompt)` and return executed tool logs.
    3. Conditional App Activation: `activate_app()` only executes when explicitly running visual screen analysis or MCQ evaluation.
    4. Expanded Hop Limit: Increased `BLACKY_MAX_TOOL_HOPS` from 8 to 30 in `blacky/config.py`.
    5. Typo Normalization: Expanded `CommandSimplifier.simplify()` and `_parse_whatsapp_fast_path` to handle `serch`, `srch`, `whatapp`, `messege`, `youtub`, `chrom`, ensuring commands like `open whatsapp and serch velocity and send him thanks message` execute immediately in <0.2s.
    6. Updated `blacky/web/companion.py` window title to "Blacky Companion". Full test suite (141 tests) passing.

## 6. Known Quirks / Heuristics
- WhatsApp automation must always run in full screen mode and use `whatsapp_*` tools exclusively (never Apple Messages).
- TTS output is strictly operational (<160 chars); never reads back long message bodies or generated code.
- Screen capture files are kept in `/tmp/` to avoid polluting the workspace.

## 7. Pending Tasks & Next Steps
- Maintain tool compatibility across new macOS updates and third-party web interface changes.
- Local STT is optional: install `faster-whisper` and it is used automatically; otherwise the existing SpeechRecognition engine is used.
