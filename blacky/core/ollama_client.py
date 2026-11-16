"""
Ollama provider for BlackyAgent.

This is the ONLY LLM backend used by the agent: a locally running Ollama
instance over its HTTP API (via the official `ollama` Python client).

There is deliberately no cloud fallback here. If Ollama is down, the caller
gets a clear, actionable error instead of a silent switch to another provider.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Sequence

import ollama

from blacky.config import config


class OllamaError(RuntimeError):
    """Base error for local model problems."""


class OllamaUnavailableError(OllamaError):
    """Ollama server is not reachable."""


class OllamaModelMissingError(OllamaError):
    """The configured model is not installed locally."""


@dataclass
class ToolCall:
    """Provider-neutral representation of a model-triggered tool call."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelReply:
    """Normalized model response (text + optional tool calls)."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str = ""
    model: str = ""
    raw: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


def _normalize_model_name(name: str) -> str:
    """Ollama treats 'qwen3:4b' and 'qwen3:4b:latest' inconsistently; normalize."""
    clean = (name or "").strip()
    if not clean:
        return ""
    # 'qwen3:4b:latest' and 'qwen3:4b' are the same local model.
    if clean.endswith(":latest") and clean.count(":") > 1:
        clean = clean[: -len(":latest")]
    if ":" not in clean:
        return f"{clean}:latest"
    return clean


def _strip_inline_reasoning(text: str) -> str:
    """
    Some models inline their chain of thought into `content`, ending it with a
    ``</think>`` marker or starting with reasoning monologue. Keep only the actual answer.
    """
    if not text:
        return ""
    if "</think>" in text:
        tail = text.rsplit("</think>", 1)[1].strip()
        if tail:
            return tail
        return ""

    clean = text.strip()
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
    lower = clean.lower()
    if any(lower.startswith(prefix) for prefix in reasoning_prefixes):
        for marker in ("\n\nfinal answer:", "\n\nresponse:", "\n\nanswer:", "\n\nresult:"):
            if marker in lower:
                idx = lower.rfind(marker)
                tail = clean[idx + len(marker):].strip()
                if tail:
                    return tail
        return ""

    return text


def _extract_json_tool_call(text: str, allowed: Iterable[str] | None = None) -> dict | None:
    """
    Recover a tool call that a small model printed as text instead of emitting
    through the native tool-calling channel.

    Returns {"name": ..., "arguments": {...}} or None. Strict by design: only
    JSON objects or Python function calls that carry a known tool name are accepted.
    """
    if not text:
        return None

    candidates: list[str] = []
    # 1. XML <tool_call> tags (standard for Qwen3 / Ollama tool calling format)
    xml_calls = re.findall(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL)
    candidates.extend(xml_calls)
    # 2. Fenced code blocks
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates.extend(fenced)
    # 3. Bare JSON objects (balanced-ish)
    candidates.extend(re.findall(r"\{[^{}]*\"(?:name|tool)\"[^{}]*\}", text, re.DOTALL))

    for blob in candidates:
        try:
            data = json.loads(blob)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("name") or data.get("tool") or data.get("function")
        if isinstance(name, dict):
            name = name.get("name")
        args = data.get("arguments", data.get("parameters", data.get("args", {})))
        if not isinstance(name, str) or not name:
            continue
        if allowed is not None and name not in set(allowed):
            continue
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (ValueError, TypeError):
                args = {}
        if not isinstance(args, dict):
            args = {}
        return {"name": name, "arguments": args}

    # 4. Python-style function calls: tool_name(arg1="val1", arg2="val2")
    if allowed:
        import ast
        pattern = r"(?:\b)(" + "|".join(re.escape(t) for t in allowed) + r")\s*\((.*?)\)"
        matches = re.findall(pattern, text, re.DOTALL)
        for name, raw_args in matches:
            try:
                expr = ast.parse(f"f({raw_args})", mode="eval")
                call = expr.body
                kwargs = {}
                for kw in getattr(call, "keywords", []):
                    if kw.arg:
                        kwargs[kw.arg] = ast.literal_eval(kw.value)
                if kwargs:
                    return {"name": name, "arguments": kwargs}
            except Exception:
                continue

    return None


def ensure_server_running(base_url: str = "http://localhost:11434", timeout_seconds: float = 8.0) -> bool:
    """Ensure the local Ollama daemon is running, attempting to start it if needed."""
    import urllib.request
    import shutil
    import subprocess
    import time
    from pathlib import Path

    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=1) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass

    # Launch macOS Ollama app if installed, or fallback to 'ollama serve'
    app_path = Path("/Applications/Ollama.app")
    if app_path.exists():
        try:
            subprocess.Popen(["open", "-ga", str(app_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    elif shutil.which("ollama"):
        try:
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            with urllib.request.urlopen(f"{base_url}/api/tags", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)

    return False


class OllamaProvider:
    """Thin, testable wrapper around a local Ollama server."""

    def __init__(
        self,
        model: str | None = None,
        vision_model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        keep_alive: str | None = None,
        temperature: float | None = None,
        num_ctx: int | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = (model or config.OLLAMA_MODEL).strip()
        self.vision_model = (vision_model if vision_model is not None else config.OLLAMA_VISION_MODEL).strip()
        self.base_url = (base_url or config.OLLAMA_BASE_URL).rstrip("/")
        self.timeout = float(timeout if timeout is not None else config.OLLAMA_TIMEOUT)
        self.keep_alive = keep_alive if keep_alive is not None else config.OLLAMA_KEEP_ALIVE
        self.temperature = float(temperature if temperature is not None else config.OLLAMA_TEMPERATURE)
        self.num_ctx = int(num_ctx if num_ctx is not None else config.OLLAMA_NUM_CTX)
        self._client = client
        self._custom_client = client is not None
        self._models_cache: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # Low-level client / discovery
    # ------------------------------------------------------------------
    @property
    def client(self) -> Any:
        """Lazily build the official client so import errors surface as messages."""
        if self._client is None:
            try:
                self._client = ollama.Client(host=self.base_url, timeout=self.timeout)
            except Exception as exc:  # pragma: no cover - construction is trivial
                raise OllamaUnavailableError(f"Could not create the Ollama client: {exc}") from exc
        return self._client

    def _list_models(self) -> list[dict[str, Any]]:
        if self._models_cache is not None:
            return self._models_cache
        try:
            response = self.client.list()
        except Exception as exc:
            raise OllamaUnavailableError(
                f"Cannot reach Ollama at {self.base_url}. Is it running? ({exc})"
            ) from exc

        models = getattr(response, "models", None)
        if models is None and isinstance(response, dict):
            models = response.get("models", [])

        parsed: list[dict[str, Any]] = []
        for entry in models or []:
            name = getattr(entry, "model", None) or getattr(entry, "name", None)
            if not name and isinstance(entry, dict):
                name = entry.get("model") or entry.get("name")
            caps = getattr(entry, "capabilities", None)
            if caps is None and isinstance(entry, dict):
                caps = entry.get("capabilities")
            parsed.append({"name": name or "", "capabilities": list(caps or [])})

        # The Python client's models sometimes omit `capabilities`; read them
        # straight from the HTTP API so vision/thinking detection stays accurate.
        if parsed and not any(m["capabilities"] for m in parsed):
            caps_map = self._capabilities_over_http()
            for entry in parsed:
                entry["capabilities"] = caps_map.get(_normalize_model_name(entry["name"]), [])

        self._models_cache = parsed
        return parsed

    def _capabilities_over_http(self) -> dict[str, list[str]]:
        """Fetch /api/tags capabilities (stdlib only, localhost)."""
        try:
            import json as _json
            import urllib.request as _urllib

            with _urllib.urlopen(f"{self.base_url}/api/tags", timeout=5) as resp:
                payload = _json.loads(resp.read().decode("utf-8"))
            return {
                _normalize_model_name(m.get("model") or m.get("name") or ""): list(
                    m.get("capabilities") or []
                )
                for m in payload.get("models", [])
            }
        except Exception:
            return {}

    def refresh(self) -> None:
        """Forget cached model list (e.g. after pulling a model)."""
        self._models_cache = None

    def is_available(self) -> bool:
        """True when the Ollama HTTP API answers."""
        try:
            self._list_models()
            return True
        except OllamaUnavailableError:
            return False

    def check_connection(self) -> tuple[bool, str]:
        """Return (ok, human-readable detail) for startup validation."""
        try:
            models = self._list_models()
        except OllamaUnavailableError as exc:
            return False, str(exc)
        if not models:
            return False, (
                "Ollama is running but has no models installed. "
                f"Run: ollama pull {self.model}"
            )
        return True, f"Ollama is running at {self.base_url} ({len(models)} model(s) available)."

    def available_models(self) -> list[str]:
        return [m["name"] for m in self._list_models() if m.get("name")]

    def has_model(self, name: str) -> bool:
        target = _normalize_model_name(name)
        for existing in self.available_models():
            if _normalize_model_name(existing) == target:
                return True
        return False

    def model_capabilities(self, name: str | None = None) -> list[str]:
        target = _normalize_model_name(name or self.model)
        for entry in self._list_models():
            if _normalize_model_name(entry.get("name", "")) == target:
                return entry.get("capabilities", [])
        return []

    def ensure_model(self) -> None:
        """Raise a friendly error when the configured text model is missing."""
        if not self.has_model(self.model):
            raise OllamaModelMissingError(
                f"Model '{self.model}' is not installed locally. Run: ollama pull {self.model}"
            )

    # ------------------------------------------------------------------
    # Vision
    # ------------------------------------------------------------------
    def vision_status(self) -> tuple[bool, str]:
        """Whether screen understanding is possible with a local vision model."""
        if not self.vision_model:
            return False, (
                "Screen-image understanding is disabled (no OLLAMA_VISION_MODEL configured). "
                "Blacky falls back to app/window context only."
            )
        try:
            models = self._list_models()
        except OllamaUnavailableError as exc:
            return False, str(exc)
        if not self.has_model(self.vision_model):
            return False, (
                f"Vision model '{self.vision_model}' is not installed. "
                f"Run: ollama pull {self.vision_model}"
            )
        caps = self.model_capabilities(self.vision_model)
        if caps and "vision" not in caps:
            return False, f"Model '{self.vision_model}' does not report vision support."
        del models
        return True, f"Vision model '{self.vision_model}' is ready."

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    def _options(self, model: str | None = None) -> dict[str, Any]:
        temp = self.temperature
        # If the model uses thinking, prevent low-entropy circular reasoning loops
        if "thinking" in self.model_capabilities(model or self.model) and temp < 0.5:
            temp = 0.5
        num_predict = int(getattr(config, "OLLAMA_NUM_PREDICT", 512))
        return {"temperature": temp, "num_ctx": self.num_ctx, "num_predict": num_predict}

    def _think_param(self, model: str) -> bool | None:
        """Only send `think` to models that actually support thinking."""
        if "thinking" not in self.model_capabilities(model):
            return None
        return bool(config.OLLAMA_THINK)

    def _build_kwargs(self, model: str, tools: Sequence[dict] | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "options": self._options(model),
            "keep_alive": self.keep_alive,
        }
        if tools:
            kwargs["tools"] = list(tools)
        think = self._think_param(model)
        if think is not None:
            # When tools are provided to a thinking-capable model, never send think=False:
            # Ollama suppresses the thinking tags and spills internal monologue into content,
            # corrupting tool calls and leaking thoughts to the user.
            if tools and think is False and "thinking" in self.model_capabilities(model):
                pass
            else:
                kwargs["think"] = think
        return kwargs

    def chat(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict] | None = None,
        model: str | None = None,
        allowed_tools: Iterable[str] | None = None,
    ) -> ModelReply:
        """Send a non-streaming chat turn and normalize the reply."""
        use_model = model or self.model
        try:
            response = self.client.chat(
                messages=list(messages), **self._build_kwargs(use_model, tools)
            )
        except Exception as exc:
            err = self._translate_error(exc)
            if isinstance(err, OllamaUnavailableError) and not self._custom_client:
                if ensure_server_running(self.base_url, timeout_seconds=6.0):
                    self.refresh()
                    self._client = None
                    try:
                        response = self.client.chat(
                            messages=list(messages), **self._build_kwargs(use_model, tools)
                        )
                        return self._normalize_reply(response, use_model, allowed_tools)
                    except Exception as retry_exc:
                        raise self._translate_error(retry_exc) from retry_exc
            raise err from exc
        return self._normalize_reply(response, use_model, allowed_tools)

    def stream_chat(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict] | None = None,
        model: str | None = None,
    ) -> Iterator[str]:
        """Yield text deltas. Tool calls are only guaranteed on non-streaming turns."""
        use_model = model or self.model
        try:
            stream = self.client.chat(
                messages=list(messages), stream=True, **self._build_kwargs(use_model, tools)
            )
            for chunk in stream:
                message = getattr(chunk, "message", None)
                text = getattr(message, "content", "") if message is not None else ""
                if text:
                    yield text
        except Exception as exc:
            raise self._translate_error(exc) from exc

    def _translate_error(self, exc: Exception) -> OllamaError:
        text = str(exc)
        lowered = text.lower()
        if "not found" in lowered or "pull" in lowered:
            return OllamaModelMissingError(
                f"Model '{self.model}' is not available. Run: ollama pull {self.model} ({text})"
            )
        if any(k in lowered for k in ("connect", "refused", "timeout", "timed out", "unreachable", "connection")):
            return OllamaUnavailableError(
                f"Ollama did not respond at {self.base_url}. Make sure `ollama serve` is running. ({text})"
            )
        return OllamaError(f"Ollama request failed: {text}")

    def _normalize_reply(
        self,
        response: Any,
        model: str,
        allowed_tools: Iterable[str] | None = None,
    ) -> ModelReply:
        message = getattr(response, "message", None)
        if message is None and isinstance(response, dict):
            message = response.get("message", {})

        text = getattr(message, "content", None)
        if text is None and isinstance(message, dict):
            text = message.get("content")
        thinking = getattr(message, "thinking", None) or ""

        calls: list[ToolCall] = []
        raw_calls = getattr(message, "tool_calls", None)
        if raw_calls is None and isinstance(message, dict):
            raw_calls = message.get("tool_calls")

        for raw in raw_calls or []:
            fn = getattr(raw, "function", None)
            if fn is None and isinstance(raw, dict):
                fn = raw.get("function", {})
            name = getattr(fn, "name", None) if fn is not None else None
            if name is None and isinstance(fn, dict):
                name = fn.get("name")
            args = getattr(fn, "arguments", None) if fn is not None else None
            if args is None and isinstance(fn, dict):
                args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (ValueError, TypeError):
                    args = {}
            if not isinstance(args, dict):
                args = {}
            if isinstance(name, str) and name:
                calls.append(ToolCall(name=name, arguments=args))

        reply_text = _strip_inline_reasoning((text or "").strip())

        # Small local models sometimes print the call as text instead of using
        # the native channel; recover it only when it names a known tool.
        if not calls:
            # Check raw content, thinking tags, and stripped reply text
            recovered = _extract_json_tool_call(text or "", allowed_tools)
            if not recovered and thinking:
                recovered = _extract_json_tool_call(thinking, allowed_tools)
            if not recovered and reply_text:
                recovered = _extract_json_tool_call(reply_text, allowed_tools)
            if recovered:
                calls.append(ToolCall(name=recovered["name"], arguments=recovered["arguments"]))
                reply_text = ""

        return ModelReply(
            text=reply_text,
            tool_calls=calls,
            thinking=(thinking or "").strip(),
            model=model,
            raw=response,
        )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        """Status payload shared by the CLI and the mobile API."""
        ok, detail = self.check_connection()
        model_ok = False
        if ok:
            try:
                model_ok = self.has_model(self.model)
            except OllamaUnavailableError:
                model_ok = False
        vision_ok, vision_detail = self.vision_status()
        return {
            "provider": "ollama",
            "base_url": self.base_url,
            "connected": ok,
            "detail": detail,
            "model": self.model,
            "model_available": model_ok,
            "vision_model": self.vision_model or None,
            "vision_available": vision_ok,
            "vision_detail": vision_detail,
        }
