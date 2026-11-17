"""
Screen-analysis mode for BlackyAgent.

Provides the engine behind the screen-analysis window: it captures the display,
reads the visible text with the bundled OCR binary, asks the local vision model
about the screen, and can work through an MCQ paper question by question
(answer the current MCQ, click Next, repeat).

Everything stays local: screenshots go to /tmp and only the local Ollama
vision model is used.
"""

import base64
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from blacky.core.ollama_client import OllamaError, OllamaProvider

SCREENSHOT_PATH = "/tmp/blacky_screen_mode.jpg"
MAX_OCR_CHARS = 6000

# Labels that advance to the next question on common exam / quiz screens.
NEXT_LABELS = (
    "Save & Next",
    "Save and Next",
    "Save & Next Question",
    "Save & Next question",
    "Submit & Next",
    "Next question",
    "Next Question",
    "Next >",
    "Next",
    "Continue",
    "Proceed",
    "Done",
    "NEXT",
    ">",
)

_ANALYST_RULES = (
    "You are Blacky's screen analyst running fully locally on this Mac. "
    "You see one screenshot of the user's display plus OCR text. "
    "Use only what is actually visible; never invent UI elements. "
    "Be concise and concrete."
)

_MCQ_PROMPT = """You are reading an exam paper from a macOS screenshot.
Visible OCR text from the screen:
--- OCR START ---
{ocr}
--- OCR END ---

Read the CURRENT question and its options from the screenshot.
Return ONLY one JSON object (no markdown, no prose) with exactly these keys:
{{"question": "...", "options": ["...", "..."], "answer_index": 0, "explanation": "one short sentence", "has_next": true}}

Rules:
- answer_index is the 0-based index of the correct option.
- options must contain the option texts exactly as shown on screen.
- has_next is false only when no next/continue control is visible.
- If no multiple-choice question is visible, return
  {{"question": "", "options": [], "answer_index": -1, "explanation": "no MCQ visible", "has_next": false}}.
"""


def activate_app(app_name: str) -> str:
    """Bring the app holding the paper to the front (best effort)."""
    target = (app_name or "").strip()
    if not target or target.lower() == "auto":
        from blacky.tools.macos import get_screen_context
        try:
            ctx = get_screen_context()
            front = ctx.get("front_app", "")
            if front and front not in ("Terminal", "iTerm2", "Code", "Cursor", "Blacky", "Google Chrome App"):
                target = front
        except Exception:
            pass
        if not target or target.lower() == "auto":
            for candidate in ("Google Chrome", "Brave Browser", "Safari", "Preview", "Arc", "Microsoft Edge"):
                try:
                    res = subprocess.run(
                        ["osascript", "-e", f'tell application "System Events" to (exists process "{candidate}")'],
                        capture_output=True,
                        text=True,
                        timeout=1.5,
                    )
                    if res.stdout.strip().lower() == "true":
                        target = candidate
                        break
                except Exception:
                    pass

    if target and target.lower() != "auto":
        safe = target.replace('"', '\\"').strip()
        try:
            subprocess.run(
                ["osascript", "-e", f'tell application "{safe}" to activate'],
                capture_output=True,
                text=True,
                timeout=8,
            )
            time.sleep(0.4)
        except Exception:
            pass
    return target


def capture_screen_base64(target_app: str = "") -> str:
    """Capture the display as base64 JPEG (empty string when unavailable)."""
    path = _capture_screen(target_app)
    try:
        with open(path, "rb") as handle:
            return base64.b64encode(handle.read()).decode("ascii")
    except OSError:
        return ""


def _capture_screen(target_app: str = "") -> str:
    from blacky.tools.macos import capture_display_screen
    try:
        from blacky.web.companion import companion_capture_guard
    except ImportError:
        companion_capture_guard = None

    if companion_capture_guard is not None:
        with companion_capture_guard():
            capture_display_screen(SCREENSHOT_PATH, app_name=target_app)
    else:
        capture_display_screen(SCREENSHOT_PATH, app_name=target_app)
    return SCREENSHOT_PATH


def _ocr_binary() -> Path | None:
    candidate = Path(__file__).resolve().parent.parent / "bin" / "ocr_fast"
    if candidate.exists():
        return candidate
    fallback = Path("/tmp/ocr_fast")
    return fallback if fallback.exists() else None


def read_screen_text(image_path: str = SCREENSHOT_PATH) -> str:
    """Visible text on the screenshot, in reading order (≈ OCR)."""
    binary = _ocr_binary()
    if binary is None:
        return ""
    try:
        out = subprocess.check_output([str(binary), image_path], text=True, timeout=30)
    except Exception:
        return ""

    lines: list[str] = []
    seen: set[str] = set()
    for raw in out.splitlines():
        text = raw.split("->", 1)[1].strip() if "->" in raw else ""
        if not text or text in seen:
            continue
        seen.add(text)
        lines.append(text)
    return "\n".join(lines)[:MAX_OCR_CHARS]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """First balanced JSON object in a model reply."""
    cleaned = re.sub(r"```(?:json)?", "", text or "")
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(cleaned[start : index + 1])
                    except ValueError:
                        data = None
                    if isinstance(data, dict):
                        return data
                    break
        start = cleaned.find("{", start + 1)
    return None


def _answer_index(data: dict[str, Any], options: list[str]) -> int:
    """Resolve the correct option index from a model JSON reply."""
    raw = data.get("answer_index")
    if isinstance(raw, bool):
        raw = None
    try:
        index = int(raw)
    except (TypeError, ValueError):
        index = -1

    if 0 <= index < len(options):
        return index

    # Models sometimes answer "B", "2" (1-based) or repeat the option text.
    text = str(raw if raw is not None else data.get("answer") or "").strip()
    letter = text.upper()[:1]
    if letter and letter in "ABCDEFGH" and len(text) <= 2:
        candidate = ord(letter) - ord("A")
        if 0 <= candidate < len(options):
            return candidate
    if 1 <= index <= len(options) and text.isdigit():
        return index - 1
    for i, option in enumerate(options):
        if text and (text in option or option in text):
            return i
    return -1


class ScreenSession:
    """Vision-based screen understanding and MCQ solving."""

    def __init__(
        self,
        provider: OllamaProvider | None = None,
        emit: Callable[[str, str], None] | None = None,
    ) -> None:
        self.provider = provider or OllamaProvider()
        self.emit = emit or (lambda kind, text: None)
        try:
            self.vision_ready, self.vision_detail = self.provider.vision_status()
        except OllamaError as exc:
            self.vision_ready, self.vision_detail = False, str(exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        try:
            self.vision_ready, self.vision_detail = self.provider.vision_status()
        except Exception as exc:
            self.vision_ready, self.vision_detail = False, str(exc)
        return {
            "ready": self.vision_ready,
            "detail": self.vision_detail,
            "vision_model": self.provider.vision_model or None,
            "text_model": self.provider.model,
        }

    def analyze(self, instruction: str, target_app: str = "") -> str:
        """Answer a free-form instruction about what is on screen."""
        if not self.vision_ready:
            return self._vision_missing()

        prompt = (instruction or "Analyze my screen and tell me what I am looking at.").strip()
        self.emit("state", "Observing screen")
        try:
            activate_app(target_app)
            image_path = _capture_screen(target_app)
            ocr = read_screen_text(image_path)
        except Exception as exc:
            return f"Could not capture the screen: {exc}"

        self.emit("state", "Analyzing interface")
        user_prompt = (
            f"User command: {prompt}\n\n"
            "Visible OCR text from the screen:\n"
            "--- OCR START ---\n"
            f"{ocr or '(no text recognized)'}\n"
            "--- OCR END ---\n\n"
            "Answer the user command using the screenshot. If they ask what is on "
            "screen, name the app/page and the most important visible content."
        )
        reply = self._ask_vision(user_prompt, image_path)

        self.emit("state", "Task completed")
        if reply:
            return reply
        if ocr:
            return "The vision model returned no answer. Visible text on screen:\n" + ocr[:1500]
        return (
            "I captured the screen but could not read it. Make sure a vision model is "
            f"installed (OLLAMA_VISION_MODEL, currently '{self.provider.vision_model or 'unset'}')."
        )

    def solve_mcqs(
        self,
        count: int = 10,
        auto_advance: bool = True,
        target_app: str = "",
        on_question_solved: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Solve visible MCQs one by one, optionally clicking Next after each."""
        solved: list[dict[str, Any]] = []
        count = max(1, min(int(count or 10), 50))

        if not self.vision_ready:
            return {"solved": solved, "message": self._vision_missing()}

        last_question = ""
        message = "Finished the requested number of questions."
        for number in range(1, count + 1):
            self.emit("state", f"Reading question {number}")
            try:
                activate_app(target_app)
                image_path = _capture_screen(target_app)
                ocr = read_screen_text(image_path)
            except Exception as exc:
                message = f"Could not capture the screen: {exc}"
                break

            if not ocr and not self.vision_ready:
                message = self._vision_missing()
                break

            reply = self._ask_vision(_MCQ_PROMPT.format(ocr=ocr or "(no text recognized)"), image_path)
            data = _extract_json_object(reply)
            if data is None:
                message = "The local vision model did not return a readable answer. Try a clearer view of the question."
                break

            options = [str(o).strip() for o in (data.get("options") or []) if str(o).strip()]
            question = str(data.get("question") or "").strip()
            index = _answer_index(data, options)

            if index < 0 or not options:
                self.emit("state", "No MCQ visible")
                message = (
                    str(data.get("explanation") or "").strip()
                    or "No multiple-choice question was visible on screen."
                )
                break

            if question and question == last_question:
                message = (
                    "The same question is still on screen — I could not advance. "
                    "Select an answer or click Next manually, then continue."
                )
                break
            last_question = question

            choice = options[index]
            letter = chr(ord('A') + index)
            self.emit("state", f"Selecting answer {letter}")
            clicked = self._click_option(choice, target_app, letter=letter)
            record = {
                "number": len(solved) + 1,
                "question": question or f"Question {number}",
                "options": options,
                "answer_index": index,
                "answer": choice,
                "answer_letter": letter,
                "explanation": str(data.get("explanation") or "").strip(),
                "clicked": clicked,
                "advanced": False,
            }

            if auto_advance:
                time.sleep(0.7)
                self.emit("state", "Clicking Next")
                advanced, label = self._click_next(target_app)
                record["advanced"] = advanced
                if not advanced:
                    solved.append(record)
                    self.emit("answer", self._format_answer(record))
                    if on_question_solved:
                        try:
                            on_question_solved(record)
                        except Exception:
                            pass
                    message = "Answered the question but could not find a Next button."
                    break
                record["next_label"] = label
                time.sleep(0.9)

            solved.append(record)
            self.emit("answer", self._format_answer(record))
            if on_question_solved:
                try:
                    on_question_solved(record)
                except Exception:
                    pass

            if not auto_advance:
                message = "Answered the visible question. Continue when the next one is on screen."
                break

        self.emit("state", "Task completed")
        return {"solved": solved, "message": message}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _vision_missing(self) -> str:
        return (
            "Screen understanding needs a local vision model. "
            "Set OLLAMA_VISION_MODEL in .env (for example qwen3.5:4b or llava:7b), then run: "
            f"ollama pull {self.provider.vision_model or 'qwen3.5:4b'}"
        )

    def _ask_vision(self, prompt: str, image_path: str) -> str:
        try:
            with open(image_path, "rb") as handle:
                image_b64 = base64.b64encode(handle.read()).decode("ascii")
        except OSError:
            return ""

        messages = [
            {"role": "system", "content": _ANALYST_RULES},
            {"role": "user", "content": prompt, "images": [image_b64]},
        ]
        try:
            reply = self.provider.chat(messages, model=self.provider.vision_model, think=False)
        except OllamaError as exc:
            return f"Local vision model error: {exc}"
        return (reply.text or "").strip()

    def _click_option(self, choice: str, target_app: str, letter: str = "") -> bool:
        """Click an option by its text, backing off to shorter prefixes and option letter."""
        from blacky.tools.macos import screen_click_text

        candidates = [choice]
        if letter:
            candidates.extend([
                f"{letter}. {choice}",
                f"{letter}) {choice}",
                f"({letter}) {choice}",
            ])
        words = choice.split()
        if len(words) > 6:
            candidates.append(" ".join(words[:6]))
        if len(words) > 3:
            candidates.append(" ".join(words[:3]))
        candidates.append(choice[:40])

        if letter:
            candidates.extend([f"{letter}. ", f"{letter})", f"({letter})", letter])

        for label in candidates:
            label = label.strip()
            if not label:
                continue
            result = screen_click_text(label, app_name=target_app) or ""
            if "not found" not in result.lower() and "failed" not in result.lower():
                return True
        return False

    def _click_next(self, target_app: str) -> tuple[bool, str]:
        from blacky.tools.macos import screen_click_text

        for label in NEXT_LABELS:
            result = screen_click_text(label, app_name=target_app) or ""
            lowered = result.lower()
            if "not found" not in lowered and "failed" not in lowered:
                return True, label
        return False, ""

    @staticmethod
    def _format_answer(record: dict[str, Any]) -> str:
        letter = record["answer_letter"]
        lines = [
            f"Q{record['number']}. {record['question']}",
            *[
                f"   {chr(ord('A') + i)}. {option}"
                + ("   ✅" if i == record["answer_index"] else "")
                for i, option in enumerate(record["options"])
            ],
            f"Answer: {letter} — {record['answer']}",
        ]
        if record.get("explanation"):
            lines.append(f"Why: {record['explanation']}")
        return "\n".join(lines)


def format_solved_summary(result: dict[str, Any]) -> str:
    """Plain-text summary of a solve_mcqs run (used by the tool and the API)."""
    solved = result.get("solved") or []
    blocks = [ScreenSession._format_answer(record) for record in solved]
    header = f"Solved {len(solved)} question(s)." if solved else "No questions solved."
    tail = str(result.get("message") or "").strip()
    parts = [header, *blocks]
    if tail:
        parts.append(tail)
    return "\n\n".join(parts)


def is_mcq_request(prompt: str) -> bool:
    """True when a chat command asks to work through MCQs on screen."""
    text = (prompt or "").lower()
    triggers = (
        "mcq",
        "mcqs",
        "multiple choice",
        "question paper",
        "sample paper",
        "answer paper",
        "solve the paper",
        "solve this paper",
        "solve all questions",
        "solve all mcqs",
        "solve all mcq",
        "one by one",
        "one mcq solve next",
        "next then next",
        "solve mcq",
        "solve paper",
        "solve sample paper",
        "solve test",
        "solve quiz",
        "solve exam",
        "solve questions",
        "answer the questions",
    )
    return any(trigger in text for trigger in triggers)


def extract_question_count(prompt: str, default: int = 10) -> int:
    """Optional 'solve 20 mcqs' support."""
    match = re.search(r"\b(\d{1,2})\s*(?:mcqs?|questions?)\b", (prompt or "").lower())
    if match:
        return max(1, min(int(match.group(1)), 50))
    return default
