"""
BlackyAgent Tools package.
Imports all tool modules to register them automatically.
"""

from blacky.tools.base import registry, ToolRegistry
from blacky.tools.filesystem import (
    create_folder,
    write_file,
    read_file,
    edit_file,
    list_directory,
    delete_item,
)
from blacky.tools.terminal import (
    run_terminal_command,
    run_python_code,
)
from blacky.tools.web import (
    search_web,
    fetch_webpage,
    open_in_browser,
)
from blacky.tools.macos import (
    open_application,
    set_system_volume,
    send_notification,
    get_system_info,
    run_applescript,
)
from blacky.tools.mobile import (
    mobile_get_connected_devices,
    mobile_android_command,
    mobile_run_shortcut,
    mobile_send_imessage,
)
from blacky.tools.whatsapp import (
    whatsapp_open_chat,
    whatsapp_send_message,
    whatsapp_start_video_call,
    whatsapp_start_voice_call,
)

__all__ = [
    "registry",
    "ToolRegistry",
    "create_folder",
    "write_file",
    "read_file",
    "edit_file",
    "list_directory",
    "delete_item",
    "run_terminal_command",
    "run_python_code",
    "search_web",
    "fetch_webpage",
    "open_in_browser",
    "open_application",
    "set_system_volume",
    "send_notification",
    "get_system_info",
    "run_applescript",
    "mobile_get_connected_devices",
    "mobile_android_command",
    "mobile_run_shortcut",
    "mobile_send_imessage",
    "whatsapp_open_chat",
    "whatsapp_send_message",
    "whatsapp_start_video_call",
    "whatsapp_start_voice_call",
]
