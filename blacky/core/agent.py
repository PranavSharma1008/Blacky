"""
Agent core orchestrator for BlackyAgent.
Talks to a locally running Ollama model with manual tool dispatch, continuous
screen awareness, intelligent ambiguity handling, confirmation gating and
task-state management.

Ollama is the only LLM provider: there is no cloud fallback anywhere in this
module.
"""

import base64
import json
import re
from typing import Any

from blacky.config import config
from blacky.core.ollama_client import (
    ModelReply,
    OllamaError,
    OllamaModelMissingError,
    OllamaProvider,
    OllamaUnavailableError,
    ToolCall,
)
from blacky.core.prompts import SYSTEM_INSTRUCTION
from blacky.tools import registry
from blacky.voice import voice_engine
from blacky.ui.console import (
    print_agent_response,
    print_warning,
    print_error,
    start_screen_analysis,
    update_screen_analysis,
    stop_screen_analysis,
)


# Tools that must NEVER be executed without explicit user confirmation.
_CONFIRMATION_REQUIRED_TOOLS = {
    "delete_item",
    "blinkit_checkout_flow",
    "amazon_checkout_flow",
}

# Tools that send user-facing messages (WhatsApp / SMS / iMessage / email).
_SEND_TOOL_NAMES = {
    "whatsapp_send_message",
    "mobile_send_imessage",
}

_TASK_PHASES = ("idle", "executing", "awaiting_clarification", "completed")

_ANSWER_ORDINALS = {
    "first": 1, "1st": 1, "1": 1, "one": 1, "first one": 1,
    "second": 2, "2nd": 2, "2": 2, "two": 2, "second one": 2,
    "third": 3, "3rd": 3, "3": 3, "three": 3,
    "fourth": 4, "4th": 4, "4": 4, "four": 4,
    "fifth": 5, "5th": 5, "5": 5, "five": 5,
    "1st one": 1, "2nd one": 2, "3rd one": 3, "4th one": 4, "5th one": 5,
}

_AFFIRMATIVE_ANSWERS = {
    "yes", "yeah", "yep", "yup", "ok", "okay", "sure", "yeah sure", "correct",
    "right", "exactly", "do it", "yes please", "go ahead", "approve", "approved",
    "confirmed", "absolutely", "yess", "yeah yeah",
}

_NEGATIVE_ANSWERS = {
    "no", "nope", "nah", "not now", "no thanks", "skip", "later", "cancel",
    "stop", "negative", "do not", "dont", "dont", "never mind", "forget it",
}


_NEW_INSTRUCTION_HINTS = (
    "remove", "delete", "open", "close", "launch", "add", "buy", "purchase",
    "order", "checkout", "send", "message", "text", "compose", "email", "chat",
    "call", "play", "watch", "listen", "create", "write", "file", "folder",
    "code", "search", "find", "browse", "google", "cart", "clear", "empty",
)

# Common words that indicate the start of a message body in Hinglish / English
_WA_MSG_START_WORDS = {
    "kal", "aaj", "parso", "ab", "abhi", "kaha", "kahan", "kya", "kyu", "kyun", "kaise", "kab",
    "bhai", "bro", "sun", "suno", "dekh", "dekho", "bhej", "bhejo", "aana", "aao", "aaega", "ayega",
    "chal", "chalo", "khel", "khelte", "khelenge", "mil", "milte", "baat", "phone", "call", "class",
    "cllg", "college", "ghar", "office", "urgent", "important", "the", "a", "an", "hello", "hi", "hey",
    "are", "is", "can", "could", "will", "would", "where", "what", "why", "when", "how", "please", "pls",
    "come", "let", "lets", "see", "meet", "tell", "give", "take", "i", "we", "you", "dont", "not", "thanks",
    "thank", "ok", "okay", "good", "bad", "yes", "no", "sorry", "ha", "haa", "nahi", "nhi", "mat",
}


def _split_whatsapp_target_and_message(text: str) -> tuple[str, str]:
    """
    Split combined contact name and message text (e.g. 'avnish kal aaega cllg' -> ('avnish', 'kal aaega cllg')).
    """
    tokens = text.strip().split()
    if len(tokens) <= 1:
        return text.strip(), "hello"
    if tokens[1].lower() in _WA_MSG_START_WORDS:
        return tokens[0], " ".join(tokens[1:])
    if len(tokens) > 2 and tokens[2].lower() in _WA_MSG_START_WORDS:
        return " ".join(tokens[:2]), " ".join(tokens[2:])
    if len(tokens) > 3 and tokens[3].lower() in _WA_MSG_START_WORDS:
        return " ".join(tokens[:3]), " ".join(tokens[3:])
    return tokens[0], " ".join(tokens[1:])



class BlackyAgent:
    """Core autonomous AI agent orchestrator."""

    MAX_TOOL_HOPS = config.BLACKY_MAX_TOOL_HOPS

    def __init__(self, speak_replies: bool = False, provider: OllamaProvider | None = None):
        self.speak_replies = speak_replies
        self.provider = provider or OllamaProvider()
        # `client` kept for compatibility with callers that inspect the provider.
        self.client = self.provider
        self.active_model = self.provider.model
        # Conversation history sent to the local model (user/assistant/tool turns).
        self.messages: list[dict[str, Any]] = []
        self.vision_enabled = False
        self.vision_detail = ""
        self._last_model_error = ""
        self.task_state: dict[str, Any] = {
            "phase": "idle",
            "instruction": "",
            "stage": "other",
            "pending_question": "",
            "pending_candidates": [],
            "pending_action": None,
            "awaiting_confirmation": False,
            "selected": None,
            "answers": [],
        }
        # Names of tools actually executed during the current user turn.
        self._turn_tool_calls: list[str] = []
        # JSON-schema tool definitions exposed to the local model.
        self.tool_schemas: list[dict[str, Any]] = registry.get_tool_schemas()
        self._init_provider()

    # ------------------------------------------------------------------
    # Client / session setup
    # ------------------------------------------------------------------
    def _init_provider(self) -> None:
        """Verify the local Ollama server/model once and remember vision support."""
        ok, detail = self.provider.check_connection()
        if not ok:
            print_warning(detail)
        elif not self.provider.has_model(self.provider.model):
            print_warning(
                f"Model '{self.provider.model}' is not installed. Run: ollama pull {self.provider.model}"
            )

        try:
            self.vision_enabled, self.vision_detail = self.provider.vision_status()
        except OllamaError as exc:
            self.vision_enabled, self.vision_detail = False, str(exc)

    def reset_history(self) -> None:
        """Drop the local conversation history (new session)."""
        self.messages = []

    # ------------------------------------------------------------------
    # Task state helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _classify_stage(instruction: str) -> str:
        """Best-effort classification of the current task stage."""
        lower = (instruction or "").lower().strip()
        if any(k in lower for k in ("add to cart", "add ", "buy", "purchase", "order", "checkout")):
            return "add"
        # If the user only asks to open/launch/close/maximize an app, it is an app/system task, not messaging
        is_open_or_app_action = any(
            lower.startswith(prefix) for prefix in ("open ", "launch ", "start ", "show ", "switch to ", "close ", "quit ")
        )
        has_send_or_chat_intent = any(
            k in lower for k in ("send", "text ", "message", "msg", "compose", "chat with", "call", "tell ", "bhej", "bolo")
        )
        if any(k in lower for k in ("message", "text ", "sms", "email", "compose", "chat", "call", "video call", "voice call")):
            return "messaging"
        if "whatsapp" in lower:
            if is_open_or_app_action and not has_send_or_chat_intent:
                return "other"
            return "messaging"
        if any(k in lower for k in ("create", "write", "file", "folder", "code", "binary", "java", "script", "notebook")):
            return "file_task"
        if any(k in lower for k in ("search", "find", "look", "show me", "google", "browse", "which")):
            return "search"
        if any(k in lower for k in ("play", "watch", "listen", "video", "music", "song", "movie")):
            return "media"
        return "other"

    def _start_new_task(self, instruction: str) -> None:
        """Reset task context for a brand-new user instruction."""
        self.task_state["phase"] = "executing"
        self.task_state["instruction"] = instruction
        self.task_state["stage"] = self._classify_stage(instruction)
        self.task_state["pending_question"] = ""
        self.task_state["pending_candidates"] = []
        self.task_state["pending_action"] = None
        self.task_state["awaiting_confirmation"] = False
        self.task_state["selected"] = None
        self.task_state["answers"] = []

    def _handle_clarification_answer(self, answer: str) -> str:
        """
        Continue the current task after the user answered a pending question,
        or approved / declined a pending consequential action.
        """
        pending_action = self.task_state.get("pending_action")
        awaiting_confirmation = self.task_state.get("awaiting_confirmation")

        self.task_state["phase"] = "executing"
        self.task_state["answers"].append(answer.strip())

        clean_ans = answer.strip().lower()

        # Cancellation / bailout from clarification state
        if clean_ans in _NEGATIVE_ANSWERS and not awaiting_confirmation:
            self.task_state["phase"] = "completed"
            self.task_state["instruction"] = ""
            self.task_state["stage"] = "other"
            self.task_state["pending_question"] = ""
            self.task_state["pending_candidates"] = []
            self.task_state["pending_action"] = None
            self.task_state["awaiting_confirmation"] = False
            self.task_state["selected"] = None
            self.task_state["answers"] = []
            cancel_msg = "Task cancelled. Standing by for your next command."
            stop_screen_analysis("task_completed")
            self._finalize_response(cancel_msg)
            return cancel_msg

        if awaiting_confirmation and pending_action:
            tool_name = pending_action.get("tool", "")
            tool_args = pending_action.get("args") or {}
            approved = self._is_affirmative_answer(answer)
            self.task_state["awaiting_confirmation"] = False
            self.task_state["pending_action"] = None
            if approved:
                tool_result = self._execute_tool_call_by_name(tool_name, tool_args)
                stop_screen_analysis("verifying")
                return self._run_agent_turn(f"User approved the action. Please verify the result of: {tool_name}.")
            decline_text = (
                f"Understood — I will NOT perform '{tool_name}' without your explicit approval. "
                "No action was taken."
            )
            self.task_state["phase"] = "completed"
            self._finalize_response(decline_text)
            return decline_text

        resolved = self._resolve_pending_answer(answer)
        if resolved is None:
            # The user's answer did not map to a pending candidate/confirmation.
            # If it reads like a brand-new instruction (e.g. a correction such as
            # "remove that item so the cart will be empty"), handle it as a new
            # task instead of re-asking the same question.
            if self._looks_like_new_instruction(answer):
                self.task_state["phase"] = "executing"
                self.task_state["instruction"] = answer.strip()
                self.task_state["stage"] = self._classify_stage(answer.strip())
                self.task_state["pending_question"] = ""
                self.task_state["pending_candidates"] = []
                self.task_state["pending_action"] = None
                self.task_state["awaiting_confirmation"] = False
                self.task_state["selected"] = None
                self.task_state["answers"] = [answer.strip()]
                return self._run_agent_turn(answer.strip())

            # The pending question had no option list (e.g. "Which contact should I
            # message?"), so the answer is free-form info for the current task
            # (very often just a contact name). Continue the task with it instead
            # of re-asking the same question forever.
            if not (self.task_state.get("pending_candidates") or []):
                return self._run_agent_turn(
                    f'User answered the pending question: "{answer.strip()}". '
                    "Use this answer and finish the original task now."
                )

            # Could not map the answer -> keep waiting for a valid clarification answer.
            self.task_state["phase"] = "awaiting_clarification"
            question = self.task_state.get("pending_question") or "Sorry, I didn't understand. Could you please clarify?"
            self.task_state["pending_question"] = question
            stop_screen_analysis("waiting_for_user")
            self._announce(question)
            return question

        self.task_state["selected"] = resolved
        # Keep WhatsApp-level disambiguation context in sync for contact flows.
        try:
            from blacky.tools import whatsapp as whatsapp_module
            whatsapp_module._LAST_DISAMBIGUATION_CANDIDATES = self.task_state.get("pending_candidates") or []
        except Exception:
            pass
        follow_up = (
            f"User answered: \"{answer.strip()}\". "
            f"Selected option: {resolved}. Continue the task from this point."
        )
        return self._run_agent_turn(follow_up)

    # ------------------------------------------------------------------
    # Answer / candidate resolution
    # ------------------------------------------------------------------
    def _resolve_pending_answer(self, answer: str) -> Any | None:
        """Map a user's free-form answer to a pending candidate (if any)."""
        candidates = self.task_state.get("pending_candidates") or []
        if not candidates:
            return None
        clean = (answer or "").strip().strip("'\"").strip().lower()
        tokens = clean.split()
        # Strip leading filler/ordinal words like 'the', 'a', 'please', 'just'
        while tokens and tokens[0] in ("the", "a", "an", "please", "just", "ok", "okay", "now"):
            tokens.pop(0)
        key = " ".join(tokens)
        if key in _ANSWER_ORDINALS:
            idx = _ANSWER_ORDINALS[key] - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
        if clean.isdigit():
            idx = int(clean) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
        # Direct / partial name match against candidate labels
        lowered = clean
        for cand in candidates:
            name = str(cand.get("name") or cand.get("norm") or cand.get("label") or "")
            if not name:
                continue
            name_lower = name.lower()
            if lowered and (lowered in name_lower or name_lower in lowered):
                return cand
        # Word-level overlap match (e.g. "the one with 750ml" -> variant match)
        answer_words = {w for w in lowered.replace(",", " ").split() if len(w) > 1}
        if answer_words:
            for cand in candidates:
                name = str(cand.get("name") or cand.get("norm") or cand.get("label") or "").lower()
                cand_words = {w for w in name.replace(",", " ").split() if len(w) > 1}
                if answer_words.issubset(cand_words) or cand_words.issubset(answer_words):
                    return cand
        return None

    # ------------------------------------------------------------------
    # Confirmation helpers
    # ------------------------------------------------------------------
    def _is_affirmative_answer(self, answer: str) -> bool:
        clean = (answer or "").strip().strip("'\"").lower()
        clean = " ".join(clean.split())
        if clean in _AFFIRMATIVE_ANSWERS:
            return True
        if clean in _NEGATIVE_ANSWERS:
            return False
        # Numeric confirmations like "1", "2"
        if clean.isdigit():
            return True
        return False

    def _looks_like_new_instruction(self, text: str) -> bool:
        """Heuristic: does this input read like a NEW task/correction instruction
        rather than a selection/confirmation answer to a pending question?"""
        clean = " ".join((text or "").lower().split())
        if not clean:
            return False
        return any(h in clean for h in _NEW_INSTRUCTION_HINTS)

    def _requires_confirmation(self, tool_name: str, args: dict) -> bool:
        """Return True when the tool call needs explicit user approval."""
        if tool_name in _CONFIRMATION_REQUIRED_TOOLS:
            return True
        if tool_name in _SEND_TOOL_NAMES:
            # Only allow messaging tools when the task instruction explicitly
            # authorized sending a message (e.g. "open WhatsApp and message X hello").
            # Merely naming an app ('open WhatsApp') does NOT authorize sending;
            # an actual send verb must be present in the instruction.
            instruction = (self.task_state.get("instruction") or "").lower()
            authorized = any(
                k in instruction
                for k in ("send", "text", "message", "msg", "compose", "tell", "bhej", "bolo")
            )
            if not authorized:
                return True
        return False

    def _build_confirmation_question(self, tool_name: str, args: dict) -> str:
        if tool_name == "delete_item":
            path = args.get("path") or args.get("target_path") or "this item"
            return f"Should I delete '{path}'? Please confirm before I remove it."
        if tool_name in ("blinkit_checkout_flow", "amazon_checkout_flow"):
            return "Should I proceed to checkout / payment? Please confirm — I will stop before placing any final order."
        if tool_name in _SEND_TOOL_NAMES:
            return "This will send a message. Should I go ahead?"
        return "This action may have unintended consequences. Should I proceed?"

    # ------------------------------------------------------------------
    # Tool execution helpers
    # ------------------------------------------------------------------
    def _execute_tool_call_by_name(self, tool_name: str, args: dict) -> str:
        """Execute one validated tool call, logging the outcome."""
        fn = registry.get_tool(tool_name)
        if fn is None:
            return f"Error: Unknown tool '{tool_name}'."
        if not isinstance(args, dict):
            args = {}
        logs_before = registry.log_count()
        try:
            result = fn(**args)
        except TypeError as exc:
            result = f"Error: invalid arguments for {tool_name}: {exc}"
        except Exception as e:
            result = f"Error: {tool_name} execution failed: {e}"
        self._turn_tool_calls.append(tool_name)
        # Most tools log themselves; only add an entry when they did not.
        if registry.log_count() == logs_before:
            success = not str(result).lower().startswith("error")
            registry.log_call(tool_name, args, str(result), success=success)
        return result

    # ------------------------------------------------------------------
    # Completion verification
    # ------------------------------------------------------------------
    def _send_was_requested(self) -> bool:
        """True when the current instruction asks Blacky to send a message."""
        instruction = (self.task_state.get("instruction") or "").lower().strip()
        if self.task_state.get("stage") != "messaging":
            return False
        # Opening or launching WhatsApp without explicit send verbs does NOT request a send
        if any(instruction.startswith(prefix) for prefix in ("open ", "launch ", "start ", "show ", "switch ", "bring ")):
            if not any(k in instruction for k in ("send", "text", "message", "msg", "tell", "bhej", "bolo", "compose")):
                return False
        # Naming the app alone ("open whatsapp", "whatsapp") is NOT a request to send a message
        clean_words = [w for w in re.sub(r"[^a-z0-9\s]", " ", instruction).split() if w not in ("the", "a", "an", "app", "application")]
        if clean_words in (["whatsapp"], ["open", "whatsapp"], ["launch", "whatsapp"]):
            return False
        return any(
            verb in instruction
            for verb in ("send", "text", "message", "msg", "tell", "bhej", "bolo", "compose")
        )

    def _turn_sent_message(self) -> bool:
        return any(name in _SEND_TOOL_NAMES for name in self._turn_tool_calls)

    @staticmethod
    def _is_clarifying_question(text: str) -> bool:
        """True when Blacky ended the turn by asking the user for information."""
        clean = (text or "").strip()
        if "?" not in clean:
            return False
        tail = clean.rsplit("\n", 1)[-1].lower()
        # A closing courtesy question after a successful action is not a clarification.
        return not any(
            phrase in tail
            for phrase in ("successfully", "completed", "has been sent", "is done", "was added")
        )

    def _verify_task_completion(self, final_text: str) -> tuple[str, bool]:
        """
        Guard against false 'done' reports.
        If the user asked for a message to be sent and no send tool actually ran,
        return (text, True) so the task stays open instead of being closed.
        """
        if self.task_state.get("awaiting_confirmation"):
            return final_text, False
        if not self._send_was_requested() or self._turn_sent_message():
            return final_text, False

        clean = (final_text or "").strip()
        if self._is_clarifying_question(clean):
            # Blacky genuinely asked something -> just keep the task open.
            return final_text, True

        # Never leak raw internal chain-of-thought monologue to the user
        reasoning_prefixes = (
            "okay, let's see",
            "okay, let's break down",
            "let's think",
            "let me see",
            "first, i need to",
            "the user wants to",
            "looking at the tools",
            "wait, the user says",
            "so the user wants",
        )
        if any(clean.lower().startswith(prefix) for prefix in reasoning_prefixes):
            clean = ""

        note = (
            "Nothing has been sent yet — I stopped before messaging anyone. "
            "Tell me the contact name (or say 'me' to message your own chat) and I'll send it right away."
        )
        return (f"{clean}\n\n{note}" if clean else note), True

    @staticmethod
    def _call_signature(call: ToolCall) -> str:
        """Stable identity for a tool call, used to detect model loops."""
        try:
            args = json.dumps(call.arguments or {}, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            args = str(call.arguments)
        return f"{call.name}|{args}"

    def _execute_tool_call(self, call: ToolCall) -> str:
        return self._execute_tool_call_by_name(call.name, call.arguments or {})

    @staticmethod
    def _tool_message(name: str, result: str) -> dict[str, Any]:
        """Ollama tool-result message for one executed tool call."""
        return {"role": "tool", "tool_name": name, "content": result}

    @staticmethod
    def _assistant_message(reply: ModelReply) -> dict[str, Any]:
        """Convert a normalized reply back into an Ollama conversation message."""
        message: dict[str, Any] = {"role": "assistant", "content": reply.text or ""}
        if reply.tool_calls:
            message["tool_calls"] = [
                {"function": {"name": call.name, "arguments": call.arguments}}
                for call in reply.tool_calls
            ]
        return message

    @staticmethod
    def _get_function_calls(reply: ModelReply | None) -> list[ToolCall]:
        return list(reply.tool_calls) if reply else []

    # ------------------------------------------------------------------
    # Screen awareness helpers
    # ------------------------------------------------------------------
    def _capture_screen_context(self) -> dict[str, str]:
        from blacky.tools.macos import get_screen_context
        screen_ctx = get_screen_context() or {}
        return screen_ctx

    def _capture_screen_image(self, screen_ctx: dict[str, Any]) -> str | None:
        """Capture the screen as base64 JPEG for a vision-capable local model.

        Returns None when no vision model is configured/installed: the agent then
        runs text-only instead of pretending it can see the screen.
        """
        if not self.vision_enabled:
            return None
        try:
            from blacky.tools.macos import capture_display_screen

            front_app = screen_ctx.get("front_app", "")
            live_jpg_path = "/tmp/blacky_live_screen.jpg"
            terminal_apps = ("Terminal", "iTerm2", "Alacritty", "Code", "Cursor")
            target_app = front_app if front_app not in terminal_apps else ""
            target_site = ""
            lower_prompt = str(self.task_state.get("instruction") or "").lower()
            for site_kw in ("blinkit", "youtube", "amazon", "flipkart", "netflix", "spotify", "google", "github", "whatsapp"):
                if site_kw in lower_prompt:
                    target_site = site_kw
                    break
            if not target_site and screen_ctx.get("active_site"):
                target_site = screen_ctx.get("active_site")
            capture_display_screen(live_jpg_path, app_name=target_app, target_site=target_site)
            with open(live_jpg_path, "rb") as handle:
                return base64.b64encode(handle.read()).decode("ascii")
        except Exception as exc:  # screen capture is best-effort
            print_warning(f"Screen capture unavailable: {exc}")
            return None

    def _capture_screen_after_action(self) -> None:
        """Re-capture the screen after an important action to verify its effect."""
        if not self.vision_enabled:
            return
        try:
            from blacky.tools.macos import capture_display_screen
            capture_display_screen("/tmp/blacky_verify_screen.jpg")
        except Exception:
            pass

    def _build_user_prompt(self, user_text: str, screen_ctx: dict[str, Any]) -> str:
        context_items = []
        if screen_ctx.get("front_app") and screen_ctx.get("front_app") not in ("Terminal", "iTerm2", "Alacritty"):
            context_items.append(f"• Active Foreground App: {screen_ctx['front_app']}")
        if screen_ctx.get("active_site"):
            context_items.append(f"• Active Website/Service: {screen_ctx['active_site'].upper()}")
        if screen_ctx.get("browser_url"):
            context_items.append(f"• Open URL: {screen_ctx['browser_url']}")
        if screen_ctx.get("github_user"):
            context_items.append(f"• Active GitHub User/Owner: {screen_ctx['github_user']}")
        if screen_ctx.get("github_repo"):
            context_items.append(f"• Active GitHub Repository: {screen_ctx['github_repo']}")
        if screen_ctx.get("window_title"):
            context_items.append(f"• Window Title: {screen_ctx['window_title']}")
        if self.vision_enabled:
            context_items.append("• Screen Image: attached (a screenshot of the current display)")
        else:
            context_items.append("• Screen Image: unavailable (no local vision model) — rely on the app/window context above")

        intent_rule = (
            "(CRITICAL USER-INTENT BOUNDARY: Work ONLY up to the user's specific instruction. "
            "NEVER perform any operation on your own or extrapolate unrequested next steps. "
            "If the user said 'search', ONLY search and display results—NEVER click ADD, add to cart, play, or checkout. "
            "If the user said 'open', ONLY open. Stop immediately once the exact requested instruction is fulfilled.)"
        )
        if context_items:
            return (
                "[Active Screen State - User is currently viewing this application/page]:\n"
                + "\n".join(context_items)
                + f"\n\nUser Voice/Text Command: {user_text.strip()}\n"
                + intent_rule
            )
        return f"User Voice/Text Command: {user_text.strip()}\n{intent_rule}"

    # ------------------------------------------------------------------
    # Model interaction (local Ollama only)
    # ------------------------------------------------------------------
    def _system_prompt(self) -> str:
        """System prompt plus the live list of executable tools."""
        names = ", ".join(registry.tool_names())
        return (
            f"{SYSTEM_INSTRUCTION}\n\n"
            "10. TOOL INSTRUCTIONS (LOCAL MODEL)\n"
            "- CRITICAL DIRECT EXECUTION: Do NOT output lengthy thinking essays or inner monologue in <think> tags. When an action is requested, IMMEDIATELY call the appropriate tool.\n"
            "- NEW TAB & FULL SCREEN: All browser tasks and opened URLs must open in a NEW TAB and ALWAYS in Entire Screen (Full Screen) mode on macOS.\n"
            "- A live screenshot is attached ONLY when screen vision is available; otherwise use the app/window context.\n"
            "- Invoke tools through the tool/function channel — never paste JSON in your reply text.\n"
            "- Call ONE tool at a time, wait for its result, then decide the next step.\n"
            f"- The only callable tools are: {names}.\n"
            "- Understand English and Hinglish (e.g. 'WhatsApp par Palwan ka chat kholo', 'Downloads me file dhundo').\n"
            "- If a tool reports failure or ambiguity, say so honestly; never claim success you did not verify.\n"
            "- After a tool succeeds, answer the user — do NOT invent extra steps (extra notifications, "
            "extra lookups) that the user never asked for.\n"
            "- Keep the final answer to 2-3 short sentences; the user hears it spoken aloud."
        )

    def _trim_history(self) -> None:
        """Keep history bounded without orphaning tool results."""
        limit = max(4, config.OLLAMA_HISTORY_MESSAGES)
        while len(self.messages) > limit:
            self.messages.pop(0)
        # A conversation must not start with an orphaned tool result.
        while self.messages and self.messages[0].get("role") == "tool":
            self.messages.pop(0)

    def _send_model_turn(
        self, user_text: str | None = None, image_b64: str | None = None
    ) -> ModelReply | None:
        """
        Ask the local model for the next step.

        With `user_text`, that text is appended as the new user turn. Without it
        the existing conversation is reused, so tool results are read from the
        tool messages themselves (small models get confused by extra nudges).
        """
        if user_text is not None:
            message: dict[str, Any] = {"role": "user", "content": user_text}
            if image_b64:
                message["images"] = [image_b64]
            self.messages.append(message)
            self._trim_history()
        elif not self.messages:
            return None

        conversation = [
            {"role": "system", "content": self._system_prompt()},
            *self.messages,
        ]
        try:
            reply = self.provider.chat(
                conversation,
                tools=self.tool_schemas,
                model=self.active_model,
                allowed_tools=registry.tool_names(),
            )
        except OllamaModelMissingError as exc:
            self._last_model_error = str(exc)
            print_error(str(exc))
            self.messages.pop()  # do not keep a user turn the model never saw
            return None
        except OllamaUnavailableError as exc:
            self._last_model_error = str(exc)
            print_error(str(exc))
            self.messages.pop()
            return None
        except OllamaError as exc:
            self._last_model_error = str(exc)
            print_error(str(exc))
            self.messages.pop()
            return None

        self._last_model_error = ""
        self.messages.append(self._assistant_message(reply))
        self._trim_history()
        return reply

    # ------------------------------------------------------------------
    # Response finalization / voice
    # ------------------------------------------------------------------
    def _announce(self, text: str) -> None:
        print_agent_response(text)
        if self.speak_replies:
            voice_engine.speak(text, wait=False)

    def _finalize_response(self, response_text: str) -> str:
        print_agent_response(response_text)
        if self.speak_replies:
            voice_engine.speak(response_text, wait=False)
        return response_text

    def _reset_task_state(self) -> None:
        """Reset task state upon completion."""
        self.task_state["phase"] = "completed"
        self.task_state["instruction"] = ""
        self.task_state["stage"] = "other"
        self.task_state["pending_question"] = ""
        self.task_state["pending_candidates"] = []
        self.task_state["pending_action"] = None
        self.task_state["awaiting_confirmation"] = False
        self.task_state["selected"] = None
        self.task_state["answers"] = []

    def _parse_whatsapp_fast_path(self, prompt: str) -> tuple[str, str, str] | None:
        """
        Extract deterministic WhatsApp actions (send message or open chat)
        from natural language user queries without invoking the local LLM.
        Returns: ("send", contact, message) or ("open", contact, "") or None.
        """
        import re
        clean = (prompt or "").strip()
        if not clean:
            return None
        clean = " ".join(clean.split())
        lower = clean.lower()

        is_wa_context = False
        if "whatsapp" in lower or lower.startswith("whatsapp "):
            is_wa_context = True
        else:
            # Contextual: previous stage was messaging, previous turn ran whatsapp, or WhatsApp is frontmost
            if self.task_state.get("stage") == "messaging":
                is_wa_context = True
            elif self._turn_tool_calls and any("whatsapp" in t for t in self._turn_tool_calls):
                is_wa_context = True
            else:
                try:
                    from blacky.tools.macos import get_screen_context
                    ctx = get_screen_context()
                    if ctx and ctx.get("front_app", "").lower() == "whatsapp":
                        is_wa_context = True
                except Exception:
                    pass

        if not is_wa_context:
            return None

        # Clean conversational preambles and search bar phrasings
        p = re.sub(
            r"^(?:now\s+|how\s+|then\s+|also\s+|so\s+|just\s+|please\s+|can\s+you\s+|could\s+you\s+|i\s+want\s+to\s+|help\s+me\s+|go\s+to\s+|goto\s+)+",
            "",
            clean,
            flags=re.I,
        ).strip()
        p = re.sub(
            r"^(?:in|on|into|through|using)\s+(?:the\s+)?search\s*bar\s+(?:to\s+)?",
            "",
            p,
            flags=re.I,
        ).strip()

        def _clean_contact(name: str) -> str:
            c = name.strip()
            # Strip leading articles e.g. "the Yash baniya" -> "Yash baniya"
            c = re.sub(r"^(?:(?:the|a|an)\s+)", "", c, flags=re.I).strip()
            # Strip trailing app or search bar mentions
            c = re.sub(r"\s+(?:on|in)\s+(?:the\s+)?whatsapp$", "", c, flags=re.I).strip()
            c = re.sub(r"\s+(?:in|on|into)\s+(?:the\s+)?search\s*bar$", "", c, flags=re.I).strip()
            return c

        def _clean_msg(msg: str) -> str:
            m = re.sub(r"^(?:(?:a|the)\s+)?(.*?)(?:\s+message)?$", r"\1", msg.strip(), flags=re.I).strip()
            m = re.sub(r"^(?:saying|with|that|to)\s+", "", m, flags=re.I).strip()
            # Strip trailing execution directives (e.g. "and send him", "and send it", "and send")
            m = re.sub(r"(?:^|\s+)and\s+send(?:\s+(?:him|it|her|them|huim|this))?$", "", m, flags=re.I).strip()
            m = re.sub(r"(?:^|\s+)send(?:\s+(?:him|it|her|them|huim|this))?$", "", m, flags=re.I).strip()
            if (m.startswith('"') and m.endswith('"')) or (m.startswith("'") and m.endswith("'")):
                m = m[1:-1].strip()
            return m

        # 1. Verb in middle: open whatsapp (and)? search (for)? <contact> (and)? (text|message|msg|send) (him|her|them|huim)? <msg>
        # Example: "open whatsapp search avnish and text him kal aaega cllg and send"
        m = re.match(
            r"^(?:open|launch)?\s*(?:the\s+)?whatsapp\s+(?:and\s+)?(?:search\s+(?:for\s+)?|find\s+)(.+?)\s+(?:and\s+)?(?:text|message|msg|send(?:\s+a\s+message\s+to)?)\s*(?:to\s+)?(?:him|her|them|huim|it)?\s*(?:to|saying|with|that|:)?\s*(.+)$",
            p,
            re.I,
        )
        if m:
            c = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            if msg:
                return ("send", _clean_contact(c), msg)
            c_real, msg_real = _split_whatsapp_target_and_message(c)
            return ("send", _clean_contact(c_real), _clean_msg(msg_real) or "hello")

        # 2. Verb at end without message after it: open whatsapp (and)? search (for)? <contact_and_msg> (and)? (text|message|msg|send) (him|her|them|huim|it)? (and send)?
        # Example: "open whatsapp search avnish kal aaega cllg text huim and send"
        m = re.match(
            r"^(?:open|launch)?\s*(?:the\s+)?whatsapp\s+(?:and\s+)?(?:search\s+(?:for\s+)?|find\s+)(.+?)\s+(?:and\s+)?(?:text|message|msg|send)\s*(?:to\s+)?(?:him|her|them|huim|it)?(?:\s+and\s+send)?$",
            p,
            re.I,
        )
        if m:
            c, msg = _split_whatsapp_target_and_message(m.group(1))
            return ("send", _clean_contact(c), _clean_msg(msg) or "hello")

        # 3. open (the)? whatsapp (and)? send (a/the )?<msg> to <contact>
        m = re.match(
            r"^(?:open|launch)\s+(?:the\s+)?whatsapp\s+(?:and\s+)?send\s+(?:(?:a|the)\s+)?(.+?)\s+to\s+(.+)$",
            p,
            re.I,
        )
        if m:
            msg = _clean_msg(m.group(1))
            contact = m.group(2).strip()
            return ("send", _clean_contact(contact), msg or "hello")

        # 4. open (the)? whatsapp (and)? (text|message|msg|send message to) <contact> (to|saying|that|with|:) <msg>
        # Handles: "open the whatsapp text yash baniya to aaj game 9:30 bajje khelenege and send him"
        m = re.match(
            r"^(?:open|launch)\s+(?:the\s+)?whatsapp\s+(?:and\s+)?(?:text|message|msg|send(?:\s+a)?\s+message\s+to)\s+(.+?)(?:\s+(?:to|saying|that|with|:))\s+(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            return ("send", _clean_contact(contact), msg or "hello")

        # 5. open (the)? whatsapp and (text|message|msg) <contact> ...
        m = re.match(
            r"^(?:open|launch)\s+(?:the\s+)?whatsapp\s+(?:and\s+)?(?:text|message|msg)\s+(.+?)(?:\s+saying|\s+with)?\s*:\s*(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            return ("send", _clean_contact(contact), msg or "hello")

        # 6. send (a/the )?<msg> to <contact> on/in (the)? whatsapp
        m = re.match(
            r"^send\s+(?:(?:a|the)\s+)?(.+?)\s+to\s+(.+?)\s+(?:on|in)\s+(?:the\s+)?whatsapp$",
            p,
            re.I,
        )
        if m:
            msg = _clean_msg(m.group(1))
            contact = m.group(2).strip()
            return ("send", _clean_contact(contact), msg or "hello")

        # 7. send (a\s+)?message to <contact> on/in (the)? whatsapp saying/with/that/to <msg>
        m = re.match(
            r"^send\s+(?:a\s+)?message\s+to\s+(.+?)\s+(?:on|in)\s+(?:the\s+)?whatsapp\s+(?:saying|with|that|to)\s+(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            return ("send", _clean_contact(contact), msg or "hello")

        # 8. (text|message|msg) <contact> on/in (the)? whatsapp ...
        m = re.match(
            r"^(?:text|message|msg)\s+(.+?)\s+(?:on|in)\s+(?:the\s+)?whatsapp(?:\s+(?:saying|with|that|to))?\s*[:\s]\s*(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            return ("send", _clean_contact(contact), msg or "hello")

        # 9. whatsapp <contact> (saying/with/to)? <msg>
        m = re.match(
            r"^whatsapp\s+(.+?)(?:\s+(?:saying|with|that|to))?\s*[:\s]\s*(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            return ("send", _clean_contact(contact), msg or "hello")

        # 10. In WA context: search <contact_and_msg> text him and send
        m = re.match(
            r"^(?:search\s+(?:for\s+)?|find\s+)(.+?)\s+(?:and\s+)?(?:text|message|msg|send)\s*(?:to\s+)?(?:him|her|them|huim|it)?(?:\s+and\s+send)?$",
            p,
            re.I,
        )
        if m:
            c, msg = _split_whatsapp_target_and_message(m.group(1))
            return ("send", _clean_contact(c), _clean_msg(msg) or "hello")

        # 11. open (the)? whatsapp and/or search for <contact> / find <contact> / open chat with <contact>
        m = re.match(
            r"^(?:open|launch)\s+(?:the\s+)?whatsapp\s+(?:and\s+)?(?:search\s+(?:for\s+)?|find\s+|open\s+chat\s+(?:with\s+)?)(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            return ("open", _clean_contact(contact), "")

        # 12. open chat with <contact> on/in (the)? whatsapp / search <contact> on/in (the)? whatsapp
        m = re.match(
            r"^(?:open\s+(?:the\s+)?(?:chat\s+(?:with|of)\s+)?|search\s+(?:for\s+)?|find\s+)(.+?)\s+(?:on|in)\s+(?:the\s+)?whatsapp$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            return ("open", _clean_contact(contact), "")

        # 13. open (the)? whatsapp chat (with)? <contact>
        m = re.match(
            r"^(?:open|launch)\s+(?:the\s+)?whatsapp\s+chat\s+(?:with\s+)?(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            return ("open", _clean_contact(contact), "")

        # 14. Contextual: search (for)? <contact> / find <contact> / open chat (with)? <contact> when WhatsApp is active
        m = re.match(
            r"^(?:search\s+(?:for\s+)?|find\s+|open\s+chat\s+(?:with\s+)?)(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            return ("open", _clean_contact(contact), "")

        return None

    def _check_fast_path(self, prompt: str) -> str | None:
        """
        Execute deterministic high-frequency OS commands instantly (0.1s)
        when intent is unambiguous, without waiting for local LLM token ingestion.
        """
        if not isinstance(self.provider, OllamaProvider):
            return None

        clean = (prompt or "").strip()
        if not clean:
            return None

        # 1. Deterministic WhatsApp operations (messaging / opening chat)
        wa_intent = self._parse_whatsapp_fast_path(clean)
        if wa_intent is not None:
            action, contact, msg = wa_intent
            from blacky.tools.whatsapp import whatsapp_send_message, whatsapp_open_chat
            start_screen_analysis("executing")
            if action == "send":
                update_screen_analysis(f"Opening WhatsApp and sending message to {contact}...")
                res = whatsapp_send_message(contact=contact, message=msg)
            else:
                update_screen_analysis(f"Opening WhatsApp chat with {contact}...")
                res = whatsapp_open_chat(contact=contact)

            if self._is_ambiguous_result(res):
                stop_screen_analysis("waiting_for_user")
                self._handle_ambiguous_result(res)
                return res

            stop_screen_analysis("task_completed")
            self._reset_task_state()
            return self._finalize_response(res)

        clean_lower = clean.lower()
        import re

        # 2. Conversational greetings, politeness & persona reassurance
        greetings_map = [
            (
                r"^(?:i\s+need\s+(?:a\s+)?good\s+agent.*|work\s+(?:fine|properly|good|well)|be\s+(?:a\s+)?good\s+agent.*)$",
                "I am right here with you! I will ensure every task is executed accurately, quickly, and with great care. How can I assist you right now?",
            ),
            (
                r"^(?:hi|hello|hey|hey\s+blacky|good\s+morning|good\s+evening|good\s+afternoon|namaste|salaam)(?:\s+blacky)?[\!\.]*$",
                "Hello! I'm Blacky, your personal assistant. How can I help you today?",
            ),
            (
                r"^(?:who\s+are\s+you|what\s+is\s+your\s+name|what\s+can\s+you\s+do|help|help\s+me)[\?\.]*$",
                "I am Blacky, your autonomous desktop assistant. I can open apps, send WhatsApp messages, search the web, play videos on YouTube, shop on Blinkit, manage files, and control your Mac through voice or text.",
            ),
            (
                r"^(?:thank\s+you|thanks|thanks\s+a\s+lot|thank\s+you\s+so\s+much|good\s+job|well\s+done)(?:\s+blacky)?[\!\.]*$",
                "You're very welcome! Always happy to help.",
            ),
        ]
        for pattern, reply_text in greetings_map:
            if re.match(pattern, clean_lower):
                stop_screen_analysis("task_completed")
                self._reset_task_state()
                return self._finalize_response(reply_text)

        # 3. Direct time and date queries
        if re.match(r"^(?:what\s+time\s+is\s+it|what\s+is\s+the\s+time|tell\s+me\s+the\s+time|current\s+time|time)[\?\.]*$", clean_lower):
            from datetime import datetime
            time_str = datetime.now().strftime("%I:%M %p").lstrip("0")
            stop_screen_analysis("task_completed")
            self._reset_task_state()
            return self._finalize_response(f"The time is {time_str}.")

        if re.match(r"^(?:what\s+is\s+today'?s\s+date|what\s+date\s+is\s+it|what\s+is\s+the\s+date|today'?s\s+date|date)[\?\.]*$", clean_lower):
            from datetime import datetime
            date_str = datetime.now().strftime("%A, %B %d, %Y")
            stop_screen_analysis("task_completed")
            self._reset_task_state()
            return self._finalize_response(f"Today is {date_str}.")

        # 4. Direct media play & search fast-paths
        m_play = re.match(r"^(?:please\s+)?play\s+(.+?)(?:\s+on\s+youtube)?$", clean_lower)
        if m_play and not any(k in clean_lower for k in (" and ", " then ", " saying ", " text ", " message ")):
            query = m_play.group(1).strip()
            from blacky.tools.web import youtube_play
            start_screen_analysis("executing")
            update_screen_analysis(f"Playing '{query}' on YouTube...")
            res = youtube_play(query=query)
            stop_screen_analysis("task_completed")
            self._reset_task_state()
            return self._finalize_response(res)

        m_search = re.match(r"^(?:please\s+)?search\s+(?:for\s+)?(.+?)\s+on\s+(google|youtube)$", clean_lower)
        if m_search and not any(k in clean_lower for k in (" and ", " then ", " saying ", " text ", " message ")):
            query = m_search.group(1).strip()
            site = m_search.group(2).strip()
            from blacky.tools.web import browser_search
            start_screen_analysis("executing")
            update_screen_analysis(f"Searching for '{query}' on {site.title()}...")
            res = browser_search(query=query, site=site)
            stop_screen_analysis("task_completed")
            self._reset_task_state()
            return self._finalize_response(res)

        # Exclude multi-step commands or dictated messages for app launch
        if any(k in clean_lower for k in (" and ", " then ", " saying ", " text ", " message ", " with ", " chat ", " par ")):
            return None

        match = re.match(r"^(?:please\s+)?(?:open|launch)\s+(?:the\s+)?([a-zA-Z0-9_\s\.\+\-]+?)(?:\s+app|\s+application)?$", clean_lower)
        if match:
            raw_app = match.group(1).strip()
            app_map = {
                "whatsapp": "WhatsApp",
                "chrome": "Google Chrome",
                "google chrome": "Google Chrome",
                "brave": "Brave Browser",
                "brave browser": "Brave Browser",
                "safari": "Safari",
                "spotify": "Spotify",
                "code": "Visual Studio Code",
                "vs code": "Visual Studio Code",
                "vscode": "Visual Studio Code",
                "visual studio code": "Visual Studio Code",
                "cursor": "Cursor",
                "windsurf": "Windsurf",
                "terminal": "Terminal",
                "iterm": "iTerm",
                "iterm2": "iTerm2",
                "warp": "Warp",
                "ghostty": "Ghostty",
                "finder": "Finder",
                "notes": "Notes",
                "calculator": "Calculator",
                "photo booth": "Photo Booth",
                "photobooth": "Photo Booth",
                "settings": "System Settings",
                "system settings": "System Settings",
                "messages": "Messages",
                "mail": "Mail",
                "calendar": "Calendar",
            }
            target_app = app_map.get(raw_app, raw_app.title())
            from blacky.tools.macos import open_application
            start_screen_analysis("executing")
            update_screen_analysis(f"Opening {target_app}")
            open_application(target_app)
            stop_screen_analysis("task_completed")
            self._reset_task_state()
            reply = f"Opened {target_app}."
            return self._finalize_response(reply)

        return None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def run(self, user_prompt: str) -> str:
        """
        Execute user request through the agent loop.
        Handles task state, screen awareness, ambiguity, confirmations, tool
        execution, verification and voice feedback.
        """
        prompt = (user_prompt or "").strip()
        if not prompt:
            return ""

        # Fresh user turn: reset the per-turn executed-tool record.
        self._turn_tool_calls = []
        self._last_model_error = ""

        if self.task_state.get("phase") == "awaiting_clarification":
            # The user is answering a pending question / confirmation.
            return self._handle_clarification_answer(prompt)

        continuing_task = (
            self.task_state.get("phase") == "executing"
            and bool(self.task_state.get("instruction"))
        )
        if continuing_task:
            # A task is logically still in progress -> treat this input as a
            # correction / follow-up that updates the current task context.
            self.task_state["instruction"] = prompt
            self.task_state["answers"].append(prompt)
            self.task_state["stage"] = self._classify_stage(prompt)
            self.task_state["pending_question"] = ""
            self.task_state["pending_candidates"] = []
            self.task_state["pending_action"] = None
            self.task_state["awaiting_confirmation"] = False
        else:
            # New task context
            self._start_new_task(prompt)
            fast_res = self._check_fast_path(prompt)
            if fast_res is not None:
                return fast_res
        response_text = self._run_agent_turn(prompt)

        if self.task_state.get("phase") == "awaiting_clarification":
            self.task_state["phase"] = "awaiting_clarification"
        else:
            self.task_state["phase"] = "completed"
            self.task_state["instruction"] = ""
            self.task_state["stage"] = "other"
            self.task_state["pending_question"] = ""
            self.task_state["pending_candidates"] = []
            self.task_state["pending_action"] = None
            self.task_state["awaiting_confirmation"] = False
            self.task_state["selected"] = None
            self.task_state["answers"] = []

        return response_text

    # ------------------------------------------------------------------
    # Core reasoning turn
    # ------------------------------------------------------------------
    def _run_agent_turn(self, user_text: str) -> str:
        # --- Screen awareness: observe -> analyze -> identify -> process ---
        start_screen_analysis("observing")
        screen_ctx = self._capture_screen_context()
        update_screen_analysis(f"Foreground app: {screen_ctx.get('front_app') or 'unknown'}")
        start_screen_analysis("analyzing")
        image_b64 = self._capture_screen_image(screen_ctx)
        update_screen_analysis("Reading visible UI elements")
        start_screen_analysis("identifying")
        prompt_text = self._build_user_prompt(user_text, screen_ctx)
        start_screen_analysis("processing")
        update_screen_analysis(f"Analyzing with local AI ({self.active_model})...")

        import threading, time
        _model_done = threading.Event()

        def _ticker():
            t0 = time.time()
            try:
                while not _model_done.wait(timeout=1.0):
                    elapsed = int(time.time() - t0)
                    try:
                        update_screen_analysis(f"Analyzing with local AI ({self.active_model})... ({elapsed}s)")
                    except Exception:
                        break
            except Exception:
                pass

        ticker_thread = threading.Thread(target=_ticker, daemon=True)
        ticker_thread.start()
        try:
            response = self._send_model_turn(prompt_text, image_b64)
        finally:
            _model_done.set()
        final_text = None

        if response is None:
            detail = self._last_model_error or "The local model is unavailable."
            final_text = f"Sorry, I could not reach the local AI model. {detail}"
            stop_screen_analysis("error_recovery")
            self._finalize_response(final_text)
            return final_text

        seen_calls: set[str] = set()
        repeated_calls = 0

        for _ in range(self.MAX_TOOL_HOPS):
            calls = self._get_function_calls(response)
            if not calls:
                if response.text and response.text.strip():
                    final_text = response.text.strip()
                elif self._turn_tool_calls:
                    final_text = "Task step completed."
                else:
                    final_text = "I analyzed the screen but didn't execute an action. Please let me know what you would like to do."
                break

            # Confirmation gate: never execute consequential actions without approval.
            gated = [c for c in calls if self._requires_confirmation(c.name, c.arguments or {})]
            if gated:
                call = gated[0]
                self.task_state["awaiting_confirmation"] = True
                self.task_state["pending_action"] = {"tool": call.name, "args": call.arguments or {}}
                question = self._build_confirmation_question(call.name, call.arguments or {})
                self.task_state["pending_question"] = question
                self.task_state["phase"] = "awaiting_clarification"
                stop_screen_analysis("waiting_for_user")
                self.task_state["pending_candidates"] = []
                self._finalize_response(question)
                return question

            ambiguous_result = None
            for call in calls:
                if not registry.has_tool(call.name):
                    result = (
                        f"Error: '{call.name}' is not a registered tool. "
                        "Use one of the tools listed in your instructions."
                    )
                    self.messages.append(self._tool_message(call.name, result))
                    continue

                signature = self._call_signature(call)
                if signature in seen_calls:
                    repeated_calls += 1
                    self.messages.append(
                        self._tool_message(
                            call.name,
                            f"You already ran {call.name} with these exact arguments. "
                            "Its result is above — do not run it again. Answer the user now.",
                        )
                    )
                    continue
                seen_calls.add(signature)

                result = self._execute_tool_call(call)
                self.messages.append(self._tool_message(call.name, result))
                update_screen_analysis(f"Executed {call.name}")
                if self._is_ambiguous_result(result):
                    ambiguous_result = result

            if repeated_calls >= 2:
                # The model is looping on the same call; stop instead of burning hops.
                logs = registry.get_recent_logs(1)
                final_text = (
                    f"{logs[-1]['tool']} finished: {str(logs[-1]['result'])[:400]}"
                    if logs
                    else "I stopped because the model kept repeating the same action."
                )
                break

            self._trim_history()
            start_screen_analysis("processing", "Synthesizing response...")
            self._capture_screen_after_action()

            if ambiguous_result is not None:
                final_text = ambiguous_result
                self._handle_ambiguous_result(ambiguous_result)
                break

            response = self._send_model_turn()
            if response is None:
                logs = registry.get_recent_logs(1)
                if logs and logs[-1].get("success"):
                    final_text = f"{logs[-1]['tool']} completed: {str(logs[-1]['result'])[:400]}"
                else:
                    final_text = "Sorry, the local model stopped responding after the previous step."
                break

        if final_text is None:
            final_text = (response.text if response and response.text else "").strip()
        if not final_text:
            # Empty model turn after tools: report the last observed tool outcome
            # rather than a hollow success claim.
            logs = registry.get_recent_logs(1)
            if logs and logs[-1].get("success"):
                last = logs[-1]
                final_text = f"{last['tool']} finished: {str(last['result'])[:400]}"
            elif self._turn_tool_calls:
                final_text = "Task completed successfully."
            else:
                final_text = "Standing by. Tell me what you'd like me to do."

        # Never let the turn close as "done" when the requested send never happened,
        # or when Blacky ended by asking the user a question. In both cases the task
        # stays open so the next reply continues it instead of starting over.
        final_text, incomplete = self._verify_task_completion(final_text)
        still_asking = self._is_clarifying_question(final_text)
        if incomplete or still_asking or self.task_state.get("phase") == "awaiting_clarification":
            if self.task_state.get("phase") != "awaiting_clarification":
                self.task_state["phase"] = "awaiting_clarification"
                self.task_state["pending_question"] = final_text
                self.task_state["pending_candidates"] = []
            stop_screen_analysis("waiting_for_user")
            self._finalize_response(final_text)
        else:
            stop_screen_analysis("task_completed")
            self.task_state["phase"] = "completed"
            self.task_state["instruction"] = ""
            self.task_state["stage"] = "other"
            self.task_state["pending_question"] = ""
            self.task_state["pending_candidates"] = []
            self.task_state["pending_action"] = None
            self.task_state["awaiting_confirmation"] = False
            self.task_state["selected"] = None
            self.task_state["answers"] = []
            self._finalize_response(final_text)
        self.task_state["pending_action"] = None
        self.task_state["awaiting_confirmation"] = False
        return final_text

    def _is_ambiguous_result(self, result: str) -> bool:
        """Detect ambiguity markers returned by tools (e.g. multiple matches found)."""
        if not result:
            return False
        upper = result.upper()
        return any(k in upper for k in ("AMBIGUOUS", "MULTIPLE_OPTIONS", "ASK THE USER"))

    def _handle_ambiguous_result(self, result: str) -> None:
        """Transition to the awaiting-clarification phase when results are ambiguous."""
        self.task_state["phase"] = "awaiting_clarification"
        self.task_state["pending_question"] = result
        self.task_state["pending_candidates"] = []
        self.task_state["pending_action"] = None
        self.task_state["awaiting_confirmation"] = False
        stop_screen_analysis("waiting_for_user")
        self._finalize_response(result)


def create_agent(speak_replies: bool = False) -> BlackyAgent:
    """Factory function to build a BlackyAgent instance."""
    return BlackyAgent(speak_replies=speak_replies)
