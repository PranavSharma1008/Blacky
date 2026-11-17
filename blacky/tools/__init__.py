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
    browser_search,
    blinkit_add_to_cart,
    blinkit_checkout_flow,
    amazon_checkout_flow,
    youtube_play,
)
from blacky.tools.macos import (
    open_application,
    lock_mac_screen,
    wake_mac_display,
    get_mac_screen_lock_status,
    set_system_volume,
    send_notification,
    get_system_info,
    run_applescript,
    press_key,
    type_text,
    mouse_click,
    take_screenshot,
    photo_booth_take_photo,
    screen_click_text,
    get_screen_context,
    make_window_fullscreen,
)
from blacky.tools.mobile import (
    mobile_get_connected_devices,
    mobile_android_command,
    mobile_run_shortcut,
    mobile_send_imessage,
)
from blacky.tools.screen import (
    analyze_screen,
    solve_mcqs_on_screen,
)
from blacky.tools.whatsapp import (
    whatsapp_open_chat,
    whatsapp_send_message,
    whatsapp_start_video_call,
    whatsapp_start_voice_call,
    whatsapp_click_send_button,
    clean_dictated_message,
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
    "browser_search",
    "blinkit_add_to_cart",
    "blinkit_checkout_flow",
    "amazon_checkout_flow",
    "youtube_play",
    "open_application",
    "lock_mac_screen",
    "wake_mac_display",
    "get_mac_screen_lock_status",
    "set_system_volume",
    "send_notification",
    "get_system_info",
    "run_applescript",
    "press_key",
    "type_text",
    "mouse_click",
    "take_screenshot",
    "photo_booth_take_photo",
    "screen_click_text",
    "mobile_get_connected_devices",
    "mobile_android_command",
    "mobile_run_shortcut",
    "mobile_send_imessage",
    "whatsapp_open_chat",
    "whatsapp_send_message",
    "whatsapp_start_video_call",
    "whatsapp_start_voice_call",
    "whatsapp_click_send_button",
    "clean_dictated_message",
    "get_screen_context",
    "make_window_fullscreen",
    "analyze_screen",
    "solve_mcqs_on_screen",
]
