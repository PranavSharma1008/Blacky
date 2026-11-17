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
from blacky.core.simplifier import CommandSimplifier
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
    # Hinglish verbs, pronouns, question words, time markers & colloquial terms
    "kal", "aaj", "parso", "tarso", "ab", "abhi", "kaha", "kahan", "kya", "kyu", "kyun", "kyuki", "kyunki", "kyoki", "kyonki", "kaise", "kab", "kitne", "kitna",
    "bhai", "bhaiya", "bro", "yaar", "dost", "sir", "mam", "dude", "man",
    "sun", "suno", "dekh", "dekho", "bhej", "bhejo", "bhejna", "aana", "aao", "aaega", "ayega", "aayega", "aaya", "aaye", "aa",
    "ja", "jaa", "jao", "gaya", "gaye", "jayega", "jaega", "jana",
    "chal", "chalo", "chalega", "khel", "khelte", "khelenge", "khelo", "game", "match",
    "mil", "milte", "milenge", "baat", "phone", "call", "class", "cllg", "college", "school", "lecture", "bunk", "attend", "paper", "exam", "test", "assignment", "notes",
    "ghar", "office", "room", "bahar", "market", "metro", "station",
    "koshish", "kosish", "osish", "try", "trying",
    "krung", "krunga", "karunga", "karenge", "karega", "karegi", "kregi", "krna", "karna", "karo", "kr", "kar", "diya", "de", "do",
    "paya", "paaya", "paunga", "paaunga", "paungi", "sakta", "sakti", "sakte", "sakenge",
    "toh", "to", "bhi", "se", "me", "mein", "mai", "pe", "par", "pr", "ko", "ki", "ke", "ka", "kisi", "kuch", "koi", "sab", "sabko", "apna", "apne",
    "nalr", "nalle", "nalla", "velha", "vella", "free", "busy", "online", "offline", "urgent", "important",
    "ha", "haa", "hai", "hain", "hoga", "hogi", "honge", "tha", "thi", "the", "nahi", "nhi", "ni", "mat", "na",
    "bol", "bolo", "bolna", "bata", "batao", "puch", "pucho", "likh", "likho",
    "time", "baje", "bje",
    # English common words & pronouns
    "the", "a", "an", "hello", "hi", "hey",
    "are", "is", "can", "could", "will", "would", "where", "what", "why", "when", "how", "please", "pls",
    "come", "let", "lets", "see", "meet", "tell", "give", "take", "i", "we", "you", "dont", "not", "thanks",
    "thank", "ok", "okay", "good", "bad", "yes", "no", "sorry",
}


def _split_whatsapp_target_and_message(text: str) -> tuple[str, str]:
    """
    Split combined contact name and message text.
    Handles Hindi/Hinglish phrasing (e.g. 'yash baniya ko message kr kosish krung aaj aa paya...',
    'avnish kal aaega cllg', 'yash baniya osish krung aaj aa paya toh game kyuki nalr ha').
    """
    clean = text.strip()
    if not clean:
        return "", "hello"

    # 1. Explicit connector: <contact> (to|saying|with|that|ki|ke|ye|yeh|:) <msg>
    m_conn = re.match(r"^(.+?)\s+(?:to|saying|with|that|ki|ke|ye|yeh|:)\s+(.+)$", clean, re.I)
    if m_conn:
        return m_conn.group(1).strip(), m_conn.group(2).strip()

    # 2. Hindi <contact> ko (message|msg|text|send|bhej)? <msg>
    m_ko = re.match(
        r"^(.+?)\s+ko(?:\s+(?:message|msg|text|send|bhej|bhejo|bol|bolo|likh|likho)(?:\s+(?:kr|kar|karo|kardo|krde|de|do))?)?\s+(.+)$",
        clean,
        re.I,
    )
    if m_ko:
        return m_ko.group(1).strip(), m_ko.group(2).strip()

    tokens = clean.split()
    if len(tokens) <= 1:
        return clean, "hello"

    # 3. Look for the first token in tokens[1:] that matches _WA_MSG_START_WORDS
    # Contact name is usually 1 to 4 words
    found_idx = None
    for i in range(1, len(tokens)):
        clean_tok = tokens[i].lower().strip(".,?!;:'\"")
        if clean_tok in _WA_MSG_START_WORDS:
            found_idx = i
            break

    if found_idx is not None and 1 <= found_idx <= 4:
        return " ".join(tokens[:found_idx]), " ".join(tokens[found_idx:])

    # Default fallback: 1 token as contact if <= 3 tokens total, otherwise 2 tokens
    if len(tokens) >= 4:
        return " ".join(tokens[:2]), " ".join(tokens[2:])
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
        self.simplifier = CommandSimplifier()
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
        # Sanitize "text file" or "text document" to prevent clashing with "text " (messaging)
        lower_sanitized = re.sub(r"\btext\s+(?:file|document|doc|code)\b", "file", lower)
        if any(k in lower_sanitized for k in ("create", "write", "file", "folder", "code", "binary", "java", "script", "notebook", "txt")):
            return "file_task"
        # If the user only asks to open/launch/close/maximize an app, it is an app/system task, not messaging
        is_open_or_app_action = any(
            lower_sanitized.startswith(prefix) for prefix in ("open ", "launch ", "start ", "show ", "switch to ", "close ", "quit ")
        )
        has_send_or_chat_intent = any(
            k in lower_sanitized for k in ("send", "text ", "message", "msg", "compose", "chat with", "call", "tell ", "bhej", "bolo")
        )
        if any(k in lower_sanitized for k in ("message", "text ", "sms", "email", "compose", "chat", "call", "video call", "voice call")):
            return "messaging"
        if "whatsapp" in lower_sanitized:
            if is_open_or_app_action and not has_send_or_chat_intent:
                return "other"
            return "messaging"
        if any(k in lower_sanitized for k in ("search", "find", "look", "show me", "google", "browse", "which")):
            return "search"
        if any(k in lower_sanitized for k in ("play", "watch", "listen", "video", "music", "song", "movie")):
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

        # Check if the user answer contains both a candidate choice and a next command,
        # e.g., "yash baniya and open youtube", "yash baniya aur spotify chalao", "second one then open chrome"
        next_instruction = ""
        candidate_input = answer.strip()
        split_m = re.split(
            r"\s+(?:and\s+also|and\s+then|and|also|then|aur\s+bhi|aur\s+phir|aur|phir)\s+",
            candidate_input,
            maxsplit=1,
            flags=re.I,
        )
        if len(split_m) == 2:
            test_cand = split_m[0].strip()
            test_res = self._resolve_pending_answer(test_cand)
            if test_res is not None:
                candidate_input = test_cand
                next_instruction = split_m[1].strip()

        resolved = self._resolve_pending_answer(candidate_input)

        # If user gave a candidate that didn't match via ordinals/names in pending_candidates,
        # but we have a pending WhatsApp tool (open_chat or send_message),
        # and the answer is not a whole new instruction, treat the answer itself as the target contact!
        if resolved is None and pending_action and pending_action.get("tool") in ("whatsapp_open_chat", "whatsapp_send_message"):
            if not self._looks_like_new_instruction(candidate_input):
                cand_clean = re.sub(r"^(?:the\s+|a\s+|an\s+|to\s+|ko\s+|bhai\s+)", "", candidate_input, flags=re.I).strip()
                cand_clean = re.sub(r"\s+(?:ko|pe|par|pr|ki|ka|ke)$", "", cand_clean, flags=re.I).strip()
                if cand_clean:
                    resolved = {"name": cand_clean}

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
        chosen_name = resolved.get("name") if isinstance(resolved, dict) else str(resolved)
        # Keep WhatsApp-level disambiguation context in sync for contact flows.
        try:
            from blacky.tools import whatsapp as whatsapp_module
            whatsapp_module._LAST_DISAMBIGUATION_CANDIDATES = self.task_state.get("pending_candidates") or []
            if isinstance(resolved, dict) and resolved.get("x") and resolved.get("y"):
                from blacky.tools.macos import mouse_click
                mouse_click(resolved["x"], resolved["y"])
                time.sleep(0.35)
                whatsapp_module._CURRENT_ACTIVE_CHAT = chosen_name
                whatsapp_module._LAST_DISAMBIGUATION_CANDIDATES = []
        except Exception:
            pass

        # If we have a pending action saved from the ambiguous step, execute it directly now!
        if pending_action:
            p_tool = pending_action.get("tool", "")
            p_args = dict(pending_action.get("args") or {})
            if "contact" in p_args:
                p_args["contact"] = chosen_name
            start_screen_analysis("executing")
            update_screen_analysis(f"Continuing task: executing {p_tool} for {chosen_name}...")
            tool_res = self._execute_tool_call_by_name(p_tool, p_args)

            if self._is_ambiguous_result(tool_res):
                stop_screen_analysis("waiting_for_user")
                self._handle_ambiguous_result(tool_res, pending_action=pending_action)
                return tool_res

            # Task completed! Now if there was a next instruction chained, run it!
            if next_instruction:
                self._reset_task_state()
                next_res = self.run(next_instruction)
                combined = f"{tool_res}\n\n{next_res}"
                stop_screen_analysis("task_completed")
                self._reset_task_state()
                return self._finalize_response(combined)

            stop_screen_analysis("task_completed")
            self._reset_task_state()
            return self._finalize_response(tool_res)

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
        # Strip leading filler/ordinal/action words like 'the', 'a', 'please', 'just', 'text', 'send', 'to'
        while tokens and tokens[0] in (
            "the", "a", "an", "please", "just", "ok", "okay", "now",
            "text", "send", "msg", "message", "open", "to", "with", "for",
            "ko", "bhai", "bro", "arey", "are"
        ):
            tokens.pop(0)
        # Strip trailing Hindi/action markers like 'ko', 'pe', 'par', 'pr', 'bhej', 'send', 'kar'
        while tokens and tokens[-1] in ("ko", "pe", "par", "pr", "bhej", "bhejo", "send", "kar", "kr"):
            tokens.pop()
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
        lowered = key or clean
        # 1. Exact match first!
        for cand in candidates:
            name = str(cand.get("name") or cand.get("norm") or cand.get("label") or "").strip().lower()
            if name and name == lowered:
                return cand
        # 2. Substring fallback
        for cand in candidates:
            name = str(cand.get("name") or cand.get("norm") or cand.get("label") or "").strip().lower()
            if not name:
                continue
            if lowered and (lowered in name or name in lowered):
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

    def _filter_tools_for_request(self, prompt: str) -> list[dict[str, Any]]:
        """Filter tool schemas by request intent to optimize context on local models."""
        p_lower = (prompt or "").lower()

        core = {"open_application", "make_window_fullscreen", "get_current_time"}

        fs_keywords = ("file", "folder", "directory", "python", "script", "code", "sort", "java", "cpp", "write", "read", "create", "delete", "terminal", "command", "run")
        wa_keywords = ("whatsapp", "message", "chat", "text", "msg", "send", "call")
        web_keywords = ("search", "google", "browser", "youtube", "play", "video", "leetcode", "duckduckgo", "web", "site")
        screen_keywords = ("screen", "display", "ocr", "look", "click", "window", "inspect")
        mobile_keywords = ("shortcut", "imessage", "battery", "phone", "mobile")

        selected = set(core)
        if any(k in p_lower for k in fs_keywords):
            selected.update({"write_file", "read_file", "edit_file", "list_files", "create_folder", "delete_item", "run_terminal_command", "run_python_code"})
        if any(k in p_lower for k in wa_keywords):
            selected.update({"whatsapp_send_message", "whatsapp_open_chat", "whatsapp_start_video_call"})
        if any(k in p_lower for k in web_keywords):
            selected.update({"browser_search", "open_in_browser", "youtube_play", "leetcode_problem", "duckduckgo_search"})
        if any(k in p_lower for k in screen_keywords):
            selected.update({"screen_ocr", "screen_find_text", "screen_click_text", "capture_screen", "read_screen_content"})
        if any(k in p_lower for k in mobile_keywords):
            selected.update({"mobile_run_shortcut", "mobile_send_imessage", "mobile_get_battery_status"})

        if selected == core:
            return self.tool_schemas

        return [t for t in self.tool_schemas if (t.get("function", {}).get("name") in selected or t.get("name") in selected)]

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
        active_tools = self._filter_tools_for_request(self.task_state.get("instruction") or "")
        try:
            reply = self.provider.chat(
                conversation,
                tools=active_tools,
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
        Supports English and Hindi/Hinglish phrasing.
        Returns: ("send", contact, message) or ("open", contact, "") or None.
        """
        import re
        clean = (prompt or "").strip()
        if not clean:
            return None
        clean = " ".join(clean.split())
        lower = clean.lower()

        is_wa_context = False
        if any(w in lower for k in ("whatsapp", "whatsap", "whastapp", "whats app", "wp") for w in (k,)):
            is_wa_context = True
        else:
            # Contextual: previous stage was messaging, previous turn ran whatsapp, or WhatsApp is frontmost
            if self.task_state.get("stage") == "messaging":
                is_wa_context = True
            elif self._turn_tool_calls and any("whatsapp" in t for t in self._turn_tool_calls):
                is_wa_context = True
            else:
                try:
                    ctx = self._capture_screen_context()
                    if ctx and ctx.get("front_app", "").lower() == "whatsapp":
                        is_wa_context = True
                except Exception:
                    pass

        if not is_wa_context:
            return None

        # Clean conversational preambles and search bar phrasings
        preamble_re = r"^(?:ya\s+|yeah\s+|yes\s+|yup\s+|ok\s+|okay\s+|hey\s+|now\s+|how\s+|then\s+|also\s+|so\s+|just\s+|please\s+|pls\s+|can\s+you\s+|could\s+you\s+|i\s+want\s+to\s+|i\s+need\s+(?:to\s+)?|i\s+have\s+to\s+|help\s+me\s+|go\s+to\s+|goto\s+)+"
        p = re.sub(preamble_re, "", clean, flags=re.I).strip()
        p = re.sub(r"^(?:in|on|into|through|using)\s+(?:the\s+)?search\s*bar\s+(?:to\s+)?", "", p, flags=re.I).strip()

        _OPEN_V = r"(?:open|launch|khol|kkhol|kholo|chala|chalao)"
        _SEND_V = r"(?:text|message|msg|send|bhej|bhejo|bol|bolo|likh|likho)"
        _WA = r"(?:the\s+)?whatsapp"
        _CONN = r"(?:to|saying|with|that|ki|ke|ye|yeh)"

        def _clean_contact(name: str) -> str:
            c = name.strip()
            # Strip leading articles & prepositions e.g. "to yash" -> "yash", "pe yash" -> "yash"
            c = re.sub(r"^(?:(?:the|a|an|to|ko|pe|par|pr|me|mein)\s+)", "", c, flags=re.I).strip()
            # Strip trailing app or search bar mentions
            c = re.sub(r"\s+(?:on|in|pe|par|pr|me|mein)\s+(?:the\s+)?whatsapp$", "", c, flags=re.I).strip()
            c = re.sub(r"\s+(?:in|on|into)\s+(?:the\s+)?search\s*bar$", "", c, flags=re.I).strip()
            c = re.sub(r"\s+(?:ko|pe|par|pr|ki\s+chat|chat)$", "", c, flags=re.I).strip()
            return c

        def _clean_msg(msg: str) -> str:
            m = re.sub(r"^(?:(?:a|the)\s+)?(.*?)(?:\s+message)?$", r"\1", msg.strip(), flags=re.I).strip()
            m = re.sub(r"^(?:saying|with|that|to|ki|ke|ye|yeh)\s+", "", m, flags=re.I).strip()
            # Strip trailing execution directives (e.g. "and send him", "and send it", "and send")
            m = re.sub(r"(?:^|\s+)(?:and|aur)\s+send(?:\s+(?:him|it|her|them|huim|this))?$", "", m, flags=re.I).strip()
            m = re.sub(r"(?:^|\s+)send(?:\s+(?:him|it|her|them|huim|this))?$", "", m, flags=re.I).strip()
            m = re.sub(r"\s+message$", "", m, flags=re.I).strip()
            if (m.startswith('"') and m.endswith('"')) or (m.startswith("'") and m.endswith("'")):
                m = m[1:-1].strip()
            return m

        # H1. whatsapp (pe)? <contact> ko (message/msg/bhej) (kr/kar/de/do)? <msg>
        # e.g. "ok whatsapp kkhol yash baniya ko message kr kosish krung...", "whatsapp pe yash baniya ko message kar kal cllg chalte hain"
        m = re.match(
            rf"^(?:{_OPEN_V}\s+)?{_WA}(?:\s+(?:pe|par|pr|me|mein))?\s*(?:{_OPEN_V}\s+)?(.+?)\s+ko\s+{_SEND_V}(?:\s+(?:kr|kar|karo|kardo|krde|de|do))?\s+(.+)$",
            p,
            re.I,
        )
        if m:
            return ("send", _clean_contact(m.group(1)), _clean_msg(m.group(2)))

        # H2. <contact> ko whatsapp (pe)? (message/msg/bhej) (kr/kar)? <msg>
        # e.g. "yash baniya ko whatsapp pe message bhej aaj shaam ko milte hain"
        m = re.match(
            rf"^(.+?)\s+ko\s+{_WA}(?:\s+(?:pe|par|pr|me|mein))?\s+(?:{_SEND_V}(?:\s+{_SEND_V})?(?:\s+(?:kr|kar|karo|de|do))?)\s+(.+)$",
            p,
            re.I,
        )
        if m:
            return ("send", _clean_contact(m.group(1)), _clean_msg(m.group(2)))

        # 1. Verb in middle: open whatsapp (and)? search (for)? <contact> (and)? (text|message|msg|send) (him|her|them|huim)? <msg>
        m = re.match(
            rf"^(?:{_OPEN_V}\s+)?{_WA}\s+(?:(?:and|aur)\s+)?(?:(?:search|serch|saerch|seach|srch)\s+(?:for\s+)?|find\s+|dhoondho\s+)(.+?)\s+(?:(?:and|aur)\s+)?{_SEND_V}(?:\s+a\s+message\s+to)?\s*(?:to\s+)?(?:him|her|them|huim|it)?\s*(?:{_CONN}|:)?\s*(.+)$",
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
        m = re.match(
            rf"^(?:{_OPEN_V}\s+)?{_WA}\s+(?:(?:and|aur)\s+)?(?:(?:search|serch|saerch|seach|srch)\s+(?:for\s+)?|find\s+|dhoondho\s+)(.+?)\s+(?:(?:and|aur)\s+)?{_SEND_V}\s*(?:to\s+)?(?:him|her|them|huim|it)?(?:\s+(?:and|aur)\s+send)?$",
            p,
            re.I,
        )
        if m:
            c, msg = _split_whatsapp_target_and_message(m.group(1))
            return ("send", _clean_contact(c), _clean_msg(msg) or "hello")

        # 3. open (the)? whatsapp (and)? send (a/the )?<msg> to <contact>
        m = re.match(
            rf"^(?:{_OPEN_V}\s+)?{_WA}\s+(?:(?:and|aur)\s+)?send\s+(?:(?:a|the)\s+)?(.+?)\s+to\s+(.+)$",
            p,
            re.I,
        )
        if m:
            msg = _clean_msg(m.group(1))
            contact = m.group(2).strip()
            return ("send", _clean_contact(contact), msg or "hello")

        # 4. open (the)? whatsapp (and)? (text|message|msg|send message to) <contact> (to|saying|that|with|:) <msg>
        m = re.match(
            rf"^(?:{_OPEN_V}\s+)?{_WA}\s+(?:(?:and|aur)\s+)?{_SEND_V}(?:\s+(?:a\s+)?message(?:\s+to)?)?\s+(?:to\s+)?(.+?)(?:\s+(?:{_CONN}|:))\s+(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            return ("send", _clean_contact(contact), msg or "hello")

        # 4b. open (the)? whatsapp (and)? text <contact_and_msg> and send him
        m = re.match(
            rf"^(?:{_OPEN_V}\s+)?{_WA}\s+(?:(?:and|aur)\s+)?{_SEND_V}\s+(?:to\s+)?(.+?)(?:\s+(?:and|aur)\s+send(?:\s+(?:him|it|her|them|huim|this))?)$",
            p,
            re.I,
        )
        if m:
            c, msg = _split_whatsapp_target_and_message(m.group(1))
            return ("send", _clean_contact(c), _clean_msg(msg) or "hello")

        # 5. open (the)? whatsapp and (text|message|msg) <contact> ...
        m = re.match(
            rf"^(?:{_OPEN_V}\s+)?{_WA}\s+(?:(?:and|aur)\s+)?{_SEND_V}\s+(?:to\s+)?(.+?)(?:\s+saying|\s+with)?\s*:\s*(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            return ("send", _clean_contact(contact), msg or "hello")

        # 5b. open (the)? whatsapp (and)? (text|message|msg) <contact_and_msg>
        m = re.match(
            rf"^(?:{_OPEN_V}\s+)?{_WA}\s+(?:(?:and|aur)\s+)?{_SEND_V}\s+(?:to\s+)?(.+)$",
            p,
            re.I,
        )
        if m:
            c, msg = _split_whatsapp_target_and_message(m.group(1))
            return ("send", _clean_contact(c), _clean_msg(msg) or "hello")

        # 6. send (a/the )?<msg> to <contact> on/in (the)? whatsapp
        m = re.match(
            rf"^send\s+(?:(?:a|the)\s+)?(.+?)\s+to\s+(.+?)\s+(?:on|in|pe|par|pr)\s+(?:the\s+)?whatsapp$",
            p,
            re.I,
        )
        if m:
            msg = _clean_msg(m.group(1))
            contact = m.group(2).strip()
            return ("send", _clean_contact(contact), msg or "hello")

        # 7. send (a\s+)?message to <contact> on/in (the)? whatsapp saying/with/that/to <msg>
        m = re.match(
            rf"^send\s+(?:a\s+)?message\s+to\s+(.+?)\s+(?:on|in|pe|par|pr)\s+(?:the\s+)?whatsapp\s+(?:saying|with|that|to)\s+(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            return ("send", _clean_contact(contact), msg or "hello")

        # 8. (text|message|msg) <contact> on/in (the)? whatsapp ...
        m = re.match(
            rf"^{_SEND_V}\s+(.+?)\s+(?:on|in|pe|par|pr)\s+(?:the\s+)?whatsapp(?:\s+(?:saying|with|that|to))?\s*[:\s]\s*(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            return ("send", _clean_contact(contact), msg or "hello")

        # 9. whatsapp (to)? <contact> (saying/with/to)? <msg>
        m = re.match(
            rf"^{_WA}\s+(?:to\s+)?([a-zA-Z0-9_\s]+?)(?:\s+{_CONN})?\s*[:\s]\s*(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            c_low = contact.lower()
            if c_low not in ("open", "launch", "khol", "kkhol", "kholo", "chala", "chalao", "pe", "par", "pr", "me", "mein"):
                msg_low = msg.lower()
                if not any(msg_low.endswith(v) or f" {v}" in msg_low for v in ("khol", "kkhol", "kholo", "open", "launch")):
                    return ("send", _clean_contact(contact), msg or "hello")
        if m:
            contact = m.group(1).strip()
            msg = _clean_msg(m.group(2))
            if contact.lower() not in ("open", "launch", "khol", "kkhol", "kholo", "chala", "chalao"):
                return ("send", _clean_contact(contact), msg or "hello")

        # 10. In WA context: search <contact_and_msg> text him and send
        m = re.match(
            rf"^(?:(?:search|serch|saerch|seach|srch)\s+(?:for\s+)?|find\s+|dhoondho\s+)(.+?)\s+(?:and\s+)?{_SEND_V}\s*(?:to\s+)?(?:him|her|them|huim|it)?(?:\s+(?:and|aur)\s+send)?$",
            p,
            re.I,
        )
        if m:
            c, msg = _split_whatsapp_target_and_message(m.group(1))
            return ("send", _clean_contact(c), _clean_msg(msg) or "hello")

        # 11. open (the)? whatsapp and/or search for <contact> / find <contact> / open chat with <contact>
        m = re.match(
            rf"^(?:{_OPEN_V}\s+)?{_WA}(?:\s+(?:pe|par|pr|me|mein))?\s*(?:and\s+)?(?:{_OPEN_V}\s+)?(?:(?:search|serch|saerch|seach|srch)\s+(?:for\s+)?|find\s+|dhoondho\s+|open\s+chat\s+(?:with\s+)?)(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            return ("open", _clean_contact(contact), "")

        # 12. open chat with <contact> on/in (the)? whatsapp / search <contact> on/in (the)? whatsapp
        m = re.match(
            rf"^(?:open\s+(?:the\s+)?(?:chat\s+(?:with|of)\s+)?|(?:search|serch|saerch|seach|srch)\s+(?:for\s+)?|find\s+|dhoondho\s+)(.+?)\s+(?:on|in|pe|par|pr|me|mein)\s+(?:the\s+)?whatsapp$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            return ("open", _clean_contact(contact), "")

        # 13. open (the)? whatsapp chat (with)? <contact> / whatsapp pe <contact> ki chat
        m = re.match(
            rf"^(?:{_OPEN_V}\s+)?{_WA}(?:\s+(?:pe|par|pr|me|mein))?\s*(?:{_OPEN_V}\s+)?(?:chat\s+(?:with\s+)?|ki\s+chat\s+)?(.+?)(?:\s+(?:ki\s+chat|chat))?(?:\s+{_OPEN_V})?$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            return ("open", _clean_contact(contact), "")

        # 14. Contextual: search (for)? <contact> / find <contact> / open chat (with)? <contact> when WhatsApp is active
        m = re.match(
            rf"^(?:(?:search|serch|saerch|seach|srch)\s+(?:for\s+)?|find\s+|dhoondho\s+|open\s+chat\s+(?:with\s+)?)(.+)$",
            p,
            re.I,
        )
        if m:
            contact = m.group(1).strip()
            return ("open", _clean_contact(contact), "")

        return None

    def _filter_tools_for_request(self, prompt: str) -> list[dict[str, Any]]:
        """Filter tool schemas dynamically to keep prompt size small for local models."""
        lower = (prompt or "").lower()
        allowed: set[str] = set()

        # Core tools always available
        core = {
            "open_application", "make_window_fullscreen", "run_terminal_command",
            "mouse_click", "take_screenshot", "get_system_info",
        }
        allowed.update(core)

        # Domain routing
        is_code = any(k in lower for k in ("write", "create", "file", "folder", "script", "code", "python", "java", "sort", "binary", "txt"))
        if is_code:
            allowed.update({"write_file", "read_file", "edit_file", "delete_item", "create_folder", "list_files", "run_python_code"})

        is_wa = any(k in lower for k in ("whatsapp", "message", "msg", "chat", "text", "bhej", "call", "voice call", "video call"))
        if is_wa:
            allowed.update({"whatsapp_open_chat", "whatsapp_send_message", "whatsapp_start_voice_call", "whatsapp_start_video_call", "whatsapp_click_send_button"})

        is_web = any(k in lower for k in ("browser", "search", "google", "web", "find", "url", "youtube", "blinkit", "leetcode"))
        if is_web:
            allowed.update({"browser_search", "open_in_browser", "search_web", "fetch_webpage", "youtube_play", "blinkit_add_to_cart", "blinkit_checkout_flow", "leetcode_problem"})

        if not (is_code or is_wa or is_web):
            return self.tool_schemas

        return [s for s in self.tool_schemas if s.get("function", {}).get("name") in allowed]

    def _parse_filesystem_fast_path(self, prompt: str) -> str | None:
        """Execute deterministic filesystem operations instantly."""
        lower = (prompt or "").lower().strip()

        # 1. Folder creation: e.g. "make a folder named my_project on desktop"
        m_folder = re.search(r"(?:make|create)\s+(?:a\s+)?folder\s+(?:name|named|called)?\s*([a-zA-Z0-9_\-\.]+)\s+on\s+desktop", lower)
        if m_folder:
            name = m_folder.group(1).strip()
            from blacky.tools.filesystem import create_folder
            start_screen_analysis("executing")
            update_screen_analysis(f"Creating folder '{name}' on Desktop...")
            res = create_folder(folder_path=f"~/Desktop/{name}")
            stop_screen_analysis("task_completed")
            self._reset_task_state()
            return self._finalize_response(f"Created folder '{name}' on your Desktop.")

        # 2. File creation: e.g. "in the desktop make a file name a.txt inside this add a code of binary search java code"
        m_file = re.search(
            r"in\s+(?:the\s+)?desktop\s+(?:make|create)\s+(?:me\s+)?(?:a\s+)?(?:text\s+|code\s+)?file\s+(?:name|named|called)?\s*([a-zA-Z0-9_\-\.]+)(?:\s+(?:inside\s+(?:that|this|it)|with|having|and\s+put|and\s+write)\s+(.+))?",
            lower,
        )
        if m_file:
            fn = m_file.group(1).strip()
            desc = m_file.group(2) or ""
            content = ""
            if "binary search" in desc or "binarysearch" in desc:
                if "java" in desc:
                    content = (
                        "public class BinarySearch {\n"
                        "    public static int binarySearch(int[] arr, int target) {\n"
                        "        int left = 0, right = arr.length - 1;\n"
                        "        while (left <= right) {\n"
                        "            int mid = left + (right - left) / 2;\n"
                        "            if (arr[mid] == target) return mid;\n"
                        "            if (arr[mid] < target) left = mid + 1;\n"
                        "            else right = mid - 1;\n"
                        "        }\n"
                        "        return -1;\n"
                        "    }\n"
                        "}\n"
                    )
                else:
                    content = (
                        "def binary_search(arr, target):\n"
                        "    left, right = 0, len(arr) - 1\n"
                        "    while left <= right:\n"
                        "        mid = left + (right - left) // 2\n"
                        "        if arr[mid] == target: return mid\n"
                        "        elif arr[mid] < target: left = mid + 1\n"
                        "        else: right = mid - 1\n"
                        "    return -1\n"
                    )
            from blacky.tools.filesystem import write_file
            start_screen_analysis("executing")
            update_screen_analysis(f"Creating file '{fn}' on Desktop...")
            res = write_file(file_path=f"~/Desktop/{fn}", content=content)
            stop_screen_analysis("task_completed")
            self._reset_task_state()
            return self._finalize_response(f"Created file '{fn}' on your Desktop.")

        return None

    def _parse_leetcode_fast_path(self, prompt: str) -> str | None:
        """Execute deterministic LeetCode problem search, solve and submit operations instantly."""
        lower = (prompt or "").lower().strip()
        if not any(k in lower for k in ("leetcode", "leetocde", "leetcdoe", "leatcode", "letcode", "leetcde")):
            return None

        m_prob = re.search(
            r"^(?:please\s+|can\s+you\s+)?(?:open\s+)?(?:[#qQ]?\s*\d+[\.\:\)\-]?\s*)?(.+?)\s+(?:solve|submit|code|solution|on\s+leet)",
            prompt,
            re.I,
        )
        if not m_prob:
            m_prob = re.search(
                r"(?:search\s+for|find|open)\s+(?:the\s+)?(.+?)\s+(?:ques|problem|on\s+leet)",
                prompt,
                re.I,
            )
        raw_prob = m_prob.group(1).strip() if m_prob else ""
        clean_prob = re.sub(r"^(?:[#qQ]?\s*\d+[\.\:\)\-]?\s*)", "", raw_prob).strip()
        if not clean_prob:
            clean_prob = "Two Sum"

        lang = "python"
        if "java" in lower and "javascript" not in lower:
            lang = "java"
        elif "cpp" in lower or "c++" in lower:
            lang = "cpp"
        elif "javascript" in lower or " js" in lower:
            lang = "javascript"

        solve = "solve" in lower or "solution" in lower or "code" in lower
        submit = "submit" in lower

        from blacky.tools.web import leetcode_problem
        start_screen_analysis("executing")
        update_screen_analysis(f"Opening LeetCode problem '{clean_prob}'...")
        res = leetcode_problem(problem=clean_prob, language=lang, solve=solve, submit=submit)
        stop_screen_analysis("task_completed")
        self._reset_task_state()
        return self._finalize_response(res)

    def _parse_media_fast_path(self, prompt: str) -> str | None:
        """
        Fast-path for media playback and web/video searches.
        Executes youtube_play or browser_search directly in <0.2s.
        """
        clean = (prompt or "").strip()
        if not clean:
            return None
        clean_lower = clean.lower()

        # Extract target browser if present
        browser = ""
        b_match = re.search(r"\b(?:in|on|using|with)\s+(brave(?:\s+browser)?|google\s+chrome|chrome|safari|firefox|edge|arc)\b", clean_lower)
        if b_match:
            b_raw = b_match.group(1).lower()
            if "brave" in b_raw:
                browser = "Brave Browser"
            elif "chrome" in b_raw:
                browser = "Google Chrome"
            elif "safari" in b_raw:
                browser = "Safari"
            elif "firefox" in b_raw:
                browser = "Firefox"
            elif "edge" in b_raw:
                browser = "Microsoft Edge"
            elif "arc" in b_raw:
                browser = "Arc"

        known_apps = {
            "spotify", "whatsapp", "chrome", "google chrome", "brave", "brave browser",
            "safari", "code", "vscode", "vs code", "visual studio code", "cursor", "windsurf",
            "terminal", "iterm", "iterm2", "warp", "ghostty", "finder", "notes", "calculator",
            "photo booth", "photobooth", "settings", "system settings", "messages", "mail",
            "calendar", "blinkit", "amazon", "youtube", "google"
        }

        # 1. English Play Command: e.g. "play bulleya song on youtube in Brave Browser", "play lofi beats"
        m_play = re.match(
            r"^(?:please\s+)?(?:play|start|watch|listen\s+to|listen)\s+(?:the\s+|a\s+)?(.+?)$",
            clean_lower,
        )
        if m_play and not any(k in clean_lower for k in (" saying ", " text ", " message ")):
            raw_q = m_play.group(1).strip()
            # Clean trailing browser mention
            raw_q = re.sub(r"\s+(?:in|on|using|with)\s+(?:brave(?:\s+browser)?|google\s+chrome|chrome|safari|firefox|edge|arc).*$", "", raw_q, flags=re.I).strip()
            # Clean youtube mention
            raw_q = re.sub(r"\s+(?:on|in|pe|par)\s+(?:youtube|yt).*$", "", raw_q, flags=re.I).strip()
            raw_q = re.sub(r"^(?:the|a)\s+", "", raw_q, flags=re.I).strip()

            if raw_q.lower() in known_apps:
                return None

            if raw_q and raw_q not in ("song", "video", "it", "this", "youtube", "the youtube"):
                from blacky.tools.web import youtube_play
                start_screen_analysis("executing")
                update_screen_analysis(f"Playing '{raw_q}' on YouTube...")
                res = youtube_play(query=raw_q, browser=browser)
                stop_screen_analysis("task_completed")
                self._reset_task_state()
                return self._finalize_response(res)

        # 2. Hindi/Hinglish Play Command: e.g. "bulleya song chalao", "youtube pe kesariya bajao"
        m_play_hi = re.match(
            r"^(?:(?:(?:on|in|pe|par)\s+)?youtube(?:\s+(?:pe|par|me|mein))?\s+)?(?:please\s+)?(.+?)\s+(?:chalao|bajao|sunao)(?:\s+(?:on|in|pe|par)\s+youtube)?$",
            clean_lower,
        )
        if m_play_hi and not any(k in clean_lower for k in (" saying ", " text ", " message ")):
            raw_q = m_play_hi.group(1).strip()
            raw_q = re.sub(r"\s+(?:in|on|using|with)\s+(?:brave(?:\s+browser)?|google\s+chrome|chrome|safari|firefox|edge|arc).*$", "", raw_q, flags=re.I).strip()
            raw_q = re.sub(r"^(?:pe|par|me|mein)\s+", "", raw_q, flags=re.I).strip()
            raw_q = re.sub(r"^(?:pe\s+|on\s+|in\s+|par\s+)?(?:youtube|yt)\s+", "", raw_q, flags=re.I).strip()
            raw_q = re.sub(r"\s+(?:on|in|pe|par)\s+(?:youtube|yt).*$", "", raw_q, flags=re.I).strip()
            raw_q = re.sub(r"^(?:the|a)\s+", "", raw_q, flags=re.I).strip()

            if raw_q.lower() in known_apps:
                return None

            if raw_q and raw_q not in ("song", "video", "it", "this", "youtube", "the youtube"):
                from blacky.tools.web import youtube_play
                start_screen_analysis("executing")
                update_screen_analysis(f"Playing '{raw_q}' on YouTube...")
                res = youtube_play(query=raw_q, browser=browser)
                stop_screen_analysis("task_completed")
                self._reset_task_state()
                return self._finalize_response(res)

        # 3. Direct Search Fast-Path: e.g. "search for bulleya on youtube", "search python tutorials on google in Brave Browser"
        m_search = re.match(
            r"^(?:please\s+)?(?:search(?:\s+for)?|find|look\s+for)\s+(?:the\s+|a\s+)?(.+?)\s+on\s+(google|youtube|duckduckgo)(?:\s+(?:in|on|using|with)\s+.+)?$",
            clean_lower,
        )
        if m_search and not any(k in clean_lower for k in (" saying ", " text ", " message ")):
            raw_q = m_search.group(1).strip()
            site = m_search.group(2).strip()
            raw_q = re.sub(r"\s+(?:in|on|using|with)\s+(?:brave(?:\s+browser)?|google\s+chrome|chrome|safari|firefox|edge|arc).*$", "", raw_q, flags=re.I).strip()
            raw_q = re.sub(r"^(?:the|a)\s+", "", raw_q, flags=re.I).strip()

            if raw_q:
                from blacky.tools.web import browser_search
                start_screen_analysis("executing")
                update_screen_analysis(f"Searching for '{raw_q}' on {site.title()}...")
                res = browser_search(query=raw_q, site=site, browser=browser)
                stop_screen_analysis("task_completed")
                self._reset_task_state()
                return self._finalize_response(res)

        return None

    def _check_fast_path(self, prompt: str) -> str | None:
        """
        Execute deterministic high-frequency OS commands instantly (0.1s)
        when intent is unambiguous, without waiting for local LLM token ingestion.
        """
        import re

        # Fast-paths only apply to real or mock Ollama providers, not generic script runners
        from blacky.core.ollama_client import OllamaProvider
        if not isinstance(self.provider, OllamaProvider):
            return None

        clean = (prompt or "").strip()
        if not clean:
            return None

        # 0. Screen analyzing mode activation fast-path
        clean_lower_for_screen = clean.lower()
        if re.search(r"\b(?:activate|open|start)?\s*(?:the\s+)?screen(?:\s+analyzing)?\s+mode\b", clean_lower_for_screen):
            from blacky.web.server import ensure_screen_mode_active
            ensure_screen_mode_active()
            stop_screen_analysis("task_completed")
            self._reset_task_state()
            return self._finalize_response("Screen Analyzing Mode Activated: Floating Companion window is now live over your screen.")

        # 0a. Deterministic media playback & web/video search fast-path
        media_res = self._parse_media_fast_path(clean)
        if media_res is not None:
            return media_res

        # 0b. LeetCode fast-path
        lc_res = self._parse_leetcode_fast_path(clean)
        if lc_res is not None:
            return lc_res

        # 0c. Filesystem fast-path
        fs_res = self._parse_filesystem_fast_path(clean)
        if fs_res is not None:
            return fs_res

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
                pending_act = {
                    "tool": "whatsapp_send_message" if action == "send" else "whatsapp_open_chat",
                    "args": {"contact": contact, "message": msg} if action == "send" else {"contact": contact},
                }
                self._handle_ambiguous_result(res, pending_action=pending_act)
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

        # Exclude multi-step commands or dictated messages for app launch
        if any(k in clean_lower for k in (" and ", " then ", " saying ", " text ", " message ", " with ", " chat ", " par ")):
            return None

        clean_app = re.sub(
            r"^(?:ya\s+|yeah\s+|yes\s+|yup\s+|hey\s+(?:blacky\s+)?|yo\s+|ok\s+(?:blacky\s+)?|okay\s+(?:blacky\s+)?|blacky\s+|now\s+|how\s+|then\s+|also\s+|so\s+|just\s+|please\s+|kindly\s+|can\s+you\s+|could\s+you\s+|will\s+you\s+|would\s+you\s+|(?:i\s+)?want\s+to\s+|(?:i\s+)?need\s+(?:to\s+)?|(?:i\s+)?have\s+to\s+|help\s+me\s+|bhai\s+|yaar\s+|sun\s+|suno\s+|dekh\s+|dekho\s+|are\s+|arey\s+|arre\s+|ek\s+kaam\s+kar\s+|zara\s+)+",
            "",
            clean_lower,
            flags=re.I,
        ).strip()

        new_tab = bool(re.search(r"\b(?:in\s+a\s+new\s+tab|new\s+tab)\b", clean_lower))
        clean_app = re.sub(r"\b(?:in\s+a\s+new\s+tab|new\s+tab)\b", "", clean_app).strip()

        match = re.match(r"^(?:please\s+)?(?:open|launch|khol|kkhol|kholo|chala|chalao)\s+(?:the\s+)?([a-zA-Z0-9_\s\.\+\-]+?)(?:\s+app|\s+application)?$", clean_app)
        if not match:
            # Suffix form: e.g. "chrome kholo", "spotify chalao", "whatsapp khol"
            match = re.match(r"^([a-zA-Z0-9_\s\.\+\-]+?)\s+(?:app\s+|application\s+)?(?:khol|kkhol|kholo|kholna|khol\s+de|khol\s+do|chala|chalao)$", clean_app)
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
                "youtube": "YouTube",
                "blinkit": "Blinkit",
                "amazon": "Amazon",
                "github": "GitHub",
                "linkedin": "LinkedIn",
                "netflix": "Netflix",
            }
            target_app = app_map.get(raw_app, raw_app.title())
            from blacky.tools.macos import open_application
            start_screen_analysis("executing")
            update_screen_analysis(f"Opening {target_app}")
            res = open_application(target_app, new_tab=new_tab)
            stop_screen_analysis("task_completed")
            self._reset_task_state()
            if "already open" in (res or "").lower():
                reply = res
            else:
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
        raw_prompt = (user_prompt or "").strip()
        if not raw_prompt:
            return ""

        # Fresh user turn: reset the per-turn executed-tool record.
        self._turn_tool_calls = []
        self._last_model_error = ""

        if self.task_state.get("phase") == "awaiting_clarification":
            # The user is answering a pending question / confirmation.
            return self._handle_clarification_answer(raw_prompt)

        # Simplify rambling, conversational or voice-dictated instructions
        prompt = self.simplifier.simplify(raw_prompt)
        if prompt != raw_prompt and len(raw_prompt) > len(prompt) + 5:
            try:
                from blacky.ui.console import console
                console.print(f"[dim]🎯 Simplified Intent:[/dim] [cyan]{prompt}[/cyan]")
            except Exception:
                pass

        # LeetCode problem solving fast-path
        lc_res = self._parse_leetcode_fast_path(raw_prompt) or self._parse_leetcode_fast_path(prompt)
        if lc_res is not None:
            return lc_res

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
                pending_act = None
                for call in (response.tool_calls or []):
                    if call.name in ("whatsapp_send_message", "whatsapp_open_chat"):
                        pending_act = {"tool": call.name, "args": call.arguments or {}}
                        break
                self._handle_ambiguous_result(ambiguous_result, pending_action=pending_act)
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
        if self.task_state.get("phase") != "awaiting_clarification":
            self.task_state["pending_action"] = None
            self.task_state["awaiting_confirmation"] = False
        return final_text

    def _is_ambiguous_result(self, result: str) -> bool:
        """Detect ambiguity markers returned by tools (e.g. multiple matches found)."""
        if not result:
            return False
        upper = result.upper()
        return any(k in upper for k in ("AMBIGUOUS", "MULTIPLE_OPTIONS", "ASK THE USER"))

    def _handle_ambiguous_result(self, result: str, pending_action: dict | None = None) -> None:
        """Transition to the awaiting-clarification phase when results are ambiguous."""
        self.task_state["phase"] = "awaiting_clarification"
        self.task_state["pending_question"] = result
        self.task_state["pending_action"] = pending_action

        # Try to parse candidates from _LAST_DISAMBIGUATION_CANDIDATES or result string
        candidates = []
        try:
            from blacky.tools import whatsapp as whatsapp_module
            if whatsapp_module._LAST_DISAMBIGUATION_CANDIDATES:
                candidates = list(whatsapp_module._LAST_DISAMBIGUATION_CANDIDATES)
        except Exception:
            pass

        if not candidates:
            # Fallback: parse quoted names from result string e.g. 'Yashika G2', 'Yash Baniya'
            m_quotes = re.findall(r"['\"]([^'\"]+)['\"]", result)
            if m_quotes:
                candidates = [{"name": q} for q in m_quotes if q.lower() not in ("whatsapp", "contact", "chat")]

        self.task_state["pending_candidates"] = candidates
        self.task_state["awaiting_confirmation"] = False
        stop_screen_analysis("waiting_for_user")
        self._finalize_response(result)


def create_agent(speak_replies: bool = False) -> BlackyAgent:
    """Factory function to build a BlackyAgent instance."""
    return BlackyAgent(speak_replies=speak_replies)
