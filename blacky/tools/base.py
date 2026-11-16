"""
Base tool definitions and execution registry for BlackyAgent.
"""

import inspect
import re
import typing
from pathlib import Path
from typing import Any, Callable

from blacky.ui.console import print_tool_call, print_tool_result

# Keep tool descriptions short: small local models have limited context and
# long docstrings crowd out the actual task.
_MAX_DESCRIPTION_CHARS = 400


def _short_description(func: Callable) -> str:
    """First paragraph of a tool docstring, collapsed to one line."""
    doc = inspect.getdoc(func) or ""
    if not doc:
        return f"Run the {func.__name__} tool."
    first = re.split(r"\n\s*\n", doc.strip(), maxsplit=1)[0]
    text = " ".join(first.split())
    if len(text) > _MAX_DESCRIPTION_CHARS:
        text = text[: _MAX_DESCRIPTION_CHARS - 1].rstrip() + "…"
    return text


def _param_descriptions(func: Callable) -> dict[str, str]:
    """Pull optional per-argument descriptions out of a docstring Args section."""
    doc = inspect.getdoc(func) or ""
    found: dict[str, str] = {}
    for line in doc.splitlines():
        match = re.match(r"^\s{2,}([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\([^)]*\))?\s*[:\-]\s*(.+)$", line)
        if not match:
            continue
        name, desc = match.group(1), " ".join(match.group(2).split())
        if name in inspect.signature(func).parameters and desc:
            found[name] = desc[:160]
    return found


def _json_type_for(annotation: Any) -> dict[str, Any]:
    """Map a Python type annotation to a JSON-schema fragment."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin in (typing.Union, getattr(typing, "UnionType", typing.Union)):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _json_type_for(non_none[0])
        return {"type": "string"}
    if origin in (list, set, tuple):
        item = _json_type_for(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item}
    if origin is dict:
        return {"type": "object"}
    if origin is typing.Literal:
        return {"type": "string", "enum": [str(a) for a in args]}

    mapping = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        dict: {"type": "object"},
        list: {"type": "array", "items": {"type": "string"}},
        Path: {"type": "string"},
    }
    return dict(mapping.get(annotation, {"type": "string"}))


def build_function_schema(func: Callable) -> dict[str, Any]:
    """Build an Ollama/OpenAI-style function tool definition for one callable."""
    signature = inspect.signature(func)
    try:
        hints = typing.get_type_hints(func)
    except Exception:
        hints = {}
    described = _param_descriptions(func)

    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in signature.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        schema = _json_type_for(hints.get(name, param.annotation))
        if name in described:
            schema["description"] = described[name]
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            default = param.default
            if isinstance(default, (str, int, float, bool)):
                schema["default"] = default
        properties[name] = schema

    parameters: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        parameters["required"] = required

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": _short_description(func),
            "parameters": parameters,
        },
    }


class ToolRegistry:
    """Manages available agent tools and execution logging."""

    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._logs: list[dict[str, Any]] = []

    def register(self, func: Callable) -> Callable:
        """Decorator to register a tool function."""
        name = func.__name__
        self._tools[name] = func
        return func

    def get_all_tools(self) -> list[Callable]:
        """Return all registered callable tools."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Callable | None:
        """Get tool callable by name."""
        return self._tools.get(name)

    def tool_names(self) -> list[str]:
        """Names of every registered tool (the execution allowlist)."""
        return list(self._tools)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """JSON-schema tool definitions for the local model."""
        return [build_function_schema(fn) for fn in self._tools.values()]

    def log_call(self, name: str, args: dict, result: str, success: bool = True) -> None:
        """Log a tool execution (de-duplicated: some tools log themselves)."""
        if self._logs:
            last = self._logs[-1]
            if last["tool"] == name and last["args"] == args and last["result"] == result:
                return
        entry = {
            "tool": name,
            "args": args,
            "result": result,
            "success": success,
        }
        self._logs.append(entry)
        print_tool_call(name, args)
        print_tool_result(name, result, success=success)

    def log_count(self) -> int:
        """Number of logged tool executions (used to avoid double logging)."""
        return len(self._logs)

    def get_recent_logs(self, limit: int = 10) -> list[dict[str, Any]]:
        """Retrieve recent tool execution logs."""
        return self._logs[-limit:]


registry = ToolRegistry()
