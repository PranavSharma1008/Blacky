"""
UI module for BlackyAgent.
"""
from blacky.ui.console import (
    console,
    show_banner,
    print_agent_thought,
    print_tool_call,
    print_tool_result,
    print_agent_response,
    print_user_prompt,
    print_info,
    print_warning,
    print_error,
    print_mobile_qr,
    start_screen_analysis,
    update_screen_analysis,
    stop_screen_analysis,
    clear_screen_analysis,
    print_screen_state,
    get_screen_state,
    SCREEN_STATES,
)

__all__ = [
    "console",
    "show_banner",
    "print_agent_thought",
    "print_tool_call",
    "print_tool_result",
    "print_agent_response",
    "print_user_prompt",
    "print_info",
    "print_warning",
    "print_error",
    "print_mobile_qr",
    "start_screen_analysis",
    "update_screen_analysis",
    "stop_screen_analysis",
    "clear_screen_analysis",
    "print_screen_state",
    "get_screen_state",
    "SCREEN_STATES",
]
