"""
Base tool definitions and execution registry for BlackyAgent.
"""

from typing import Callable, Any
from blacky.ui.console import print_tool_call, print_tool_result


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
        """Return list of all registered callable tools for Gemini."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Callable | None:
        """Get tool callable by name."""
        return self._tools.get(name)

    def log_call(self, name: str, args: dict, result: str, success: bool = True) -> None:
        """Log a tool execution."""
        entry = {
            "tool": name,
            "args": args,
            "result": result,
            "success": success,
        }
        self._logs.append(entry)
        print_tool_call(name, args)
        print_tool_result(name, result, success=success)

    def get_recent_logs(self, limit: int = 10) -> list[dict[str, Any]]:
        """Retrieve recent tool execution logs."""
        return self._logs[-limit:]


registry = ToolRegistry()
