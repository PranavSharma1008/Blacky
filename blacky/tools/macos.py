"""
macOS system control and automation tools for BlackyAgent.
"""

import subprocess
import shutil
import time
import re
from pathlib import Path
import psutil
from blacky.tools.base import registry


_fullscreen_cache: dict[str, float] = {}


@registry.register
def make_window_fullscreen(app_name: str = "") -> str:
    """
    Ensure the target application (or active front app if empty) is in macOS Full Screen ("Entire Screen") mode.
    Prioritizes native macOS Full Screen (View -> Enter Full Screen, AXFullScreenButton, Ctrl+Cmd+F).
    Strictly idempotent: if already in Entire Screen mode, does nothing and NEVER toggles or shuffles to half mode.
    Uses ultra-fast in-memory caching to eliminate redundant AppleScript delays.
    """
    now = time.time()
    clean_app = app_name.replace('"', '\\"').strip() if app_name else ""
    if clean_app and (now - _fullscreen_cache.get(clean_app, 0.0) < 3.0):
        res = "Already in Entire Screen mode (skipped)"
        registry.log_call("make_window_fullscreen", {"app_name": app_name}, res, success=True)
        return res

    if clean_app:
        target_clause = f'set targetProc to "{clean_app}"'
    else:
        target_clause = '''tell application "System Events"
        set targetProc to name of first application process whose frontmost is true
        if targetProc is in {"Terminal", "iTerm2", "Alacritty", "Finder", "Code", "Cursor"} then
            repeat with a in (name of every application process whose background only is false)
                set an to a as string
                if an is not in {"Terminal", "iTerm2", "Alacritty", "Finder", "Code", "Cursor"} then
                    set targetProc to an
                    exit repeat
                end if
            end repeat
        end if
    end tell'''

    script = f'''
    {target_clause}
    tell application targetProc to activate
    delay 0.1
    tell application "System Events"
        tell process targetProc
            -- 1. Check if window is already in native Entire Screen mode
            try
                if exists (menu item "Exit Full Screen" of menu 1 of menu bar item "View" of menu bar 1) then
                    return "Already in Entire Screen mode (skipped)"
                end if
            end try

            try
                if (value of attribute "AXFullScreen" of front window) is true then
                    return "Already in Entire Screen mode (skipped)"
                end if
            end try

            try
                repeat with w in every window
                    if (value of attribute "AXFullScreen" of w) is true then
                        return "Already in Entire Screen mode (skipped)"
                    end if
                end repeat
            end try

            -- 2. If in half / windowed mode, enter full screen mode
            -- Priority A: View -> Enter Full Screen menu item (works for WhatsApp, Safari, Chrome, etc.)
            try
                if exists (menu item "Enter Full Screen" of menu 1 of menu bar item "View" of menu bar 1) then
                    click menu item "Enter Full Screen" of menu 1 of menu bar item "View" of menu bar 1
                    delay 0.4
                    return "Entered Full Screen via View menu"
                end if
            end try

            -- Priority B: Click macOS green AXFullScreenButton on window
            try
                click (first button whose subrole is "AXFullScreenButton") of front window
                delay 0.4
                return "Entered Full Screen via AXFullScreenButton"
            end try

            -- Priority C: Standard macOS shortcut Ctrl+Cmd+F
            keystroke "f" using {{control down, command down}}
            delay 0.4
            return "Pressed Ctrl+Cmd+F to enter Entire Screen mode"
        end tell
    end tell
    '''
    try:
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
        res = proc.stdout.strip() or "OK"
        if "Already in Entire Screen" in res or "Entered Full Screen" in res or "Pressed Ctrl+Cmd+F" in res:
            if clean_app:
                _fullscreen_cache[clean_app] = time.time()
        registry.log_call("make_window_fullscreen", {"app_name": app_name}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to ensure full screen for '{app_name}': {str(e)}"
        registry.log_call("make_window_fullscreen", {"app_name": app_name}, err, success=False)
        return err


def get_screen_context() -> dict[str, str]:
    """
    Capture the currently active foreground application, window title, and browser URL on macOS.
    Allows Blacky to analyze the active screen before deciding actions.
    Uses single-pass osascript execution for 2x faster context retrieval.
    Returns:
        dict with keys: 'front_app', 'window_title', 'browser_url', 'active_site'.
    """
    context = {
        "front_app": "",
        "window_title": "",
        "browser_url": "",
        "active_site": "",
    }
    script = '''
    set frontApp to ""
    set winTitle to ""
    set browserURL to ""
    tell application "System Events"
        try
            set frontApp to name of first application process whose frontmost is true
            if frontApp is in {"Terminal", "iTerm2", "Alacritty", "Finder", "Code", "Cursor"} then
                repeat with a in (name of every application process whose background only is false)
                    set an to a as string
                    if an is not in {"Terminal", "iTerm2", "Alacritty", "Finder", "Code", "Cursor"} then
                        set frontApp to an
                        exit repeat
                    end if
                end repeat
            end if
            try
                set winTitle to name of front window of first application process whose name is frontApp
            end try
        end try
    end tell
    if frontApp is in {"Brave Browser", "Google Chrome", "Chromium", "Arc", "Microsoft Edge"} then
        try
            if frontApp is "Brave Browser" then
                tell application "Brave Browser"
                    set winTitle to (title of active tab of front window as string)
                    set browserURL to (URL of active tab of front window as string)
                end tell
            else if frontApp is "Google Chrome" then
                tell application "Google Chrome"
                    set winTitle to (title of active tab of front window as string)
                    set browserURL to (URL of active tab of front window as string)
                end tell
            else if frontApp is "Microsoft Edge" then
                tell application "Microsoft Edge"
                    set winTitle to (title of active tab of front window as string)
                    set browserURL to (URL of active tab of front window as string)
                end tell
            else if frontApp is "Arc" then
                tell application "Arc"
                    set winTitle to (title of active tab of front window as string)
                    set browserURL to (URL of active tab of front window as string)
                end tell
            end if
        end try
    else if frontApp is "Safari" then
        try
            tell application "Safari"
                set winTitle to (name of current tab of front window as string)
                set browserURL to (URL of current tab of front window as string)
            end tell
        end try
    end if
    return frontApp & " ||| " & winTitle & " ||| " & browserURL
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and "|||" in res.stdout:
            parts = [p.strip() for p in res.stdout.strip().split("|||", 2)]
            context["front_app"] = parts[0]
            if len(parts) > 1 and parts[1]:
                context["window_title"] = parts[1]
            if len(parts) > 2 and parts[2]:
                context["browser_url"] = parts[2]
    except Exception:
        pass

    # If URL is still empty (e.g. running inside IDE terminal), check default browser active tab
    if not context["browser_url"]:
        try:
            b_script = '''
            tell application "Brave Browser"
                try
                    return (title of active tab of front window) & " ||| " & (URL of active tab of front window)
                on error
                    return ""
                end try
            end tell
            '''
            b_res = subprocess.run(["osascript", "-e", b_script], capture_output=True, text=True, timeout=2)
            if b_res.returncode == 0 and "|||" in b_res.stdout:
                b_parts = [p.strip() for p in b_res.stdout.strip().split("|||", 1)]
                if b_parts[0]:
                    context["window_title"] = b_parts[0]
                if len(b_parts) > 1 and b_parts[1]:
                    context["browser_url"] = b_parts[1]
        except Exception:
            pass

    # Extract high-level active service / site
    url_lower = context["browser_url"].lower()
    title_lower = context["window_title"].lower()
    app_lower = context["front_app"].lower()

    if "blinkit.com" in url_lower or "blinkit" in title_lower:
        context["active_site"] = "blinkit"
    elif "amazon." in url_lower or "amazon" in title_lower:
        context["active_site"] = "amazon"
    elif "flipkart.com" in url_lower or "flipkart" in title_lower:
        context["active_site"] = "flipkart"
    elif "github.com" in url_lower or "github" in title_lower:
        context["active_site"] = "github"
        m = re.search(r'github\.com/([a-zA-Z0-9_\-]+)(?:/([a-zA-Z0-9_\-]+))?', context["browser_url"])
        if m:
            user_part = m.group(1)
            if user_part not in ("search", "features", "explore", "trending", "pulls", "issues"):
                context["github_user"] = user_part
                if m.group(2):
                    context["github_repo"] = m.group(2)
    elif "youtube.com" in url_lower or "youtube" in title_lower:
        context["active_site"] = "youtube"
    elif "google.com" in url_lower:
        context["active_site"] = "google"
    elif "whatsapp" in app_lower:
        context["active_site"] = "whatsapp"
    elif "spotify" in app_lower:
        context["active_site"] = "spotify"

    return context


COMMON_WEB_SERVICES = {
    "blinkit": "https://blinkit.com",
    "amazon": "https://amazon.in",
    "flipkart": "https://flipkart.com",
    "youtube": "https://youtube.com",
    "netflix": "https://netflix.com",
    "chatgpt": "https://chatgpt.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "instagram": "https://instagram.com",
    "facebook": "https://facebook.com",
    "reddit": "https://reddit.com",
    "linkedin": "https://linkedin.com",
    "swiggy": "https://swiggy.com",
    "zomato": "https://zomato.com",
    "github": "https://github.com",
    "google": "https://google.com",
    "gmail": "https://mail.google.com",
    "spotify": "https://open.spotify.com",
}


@registry.register
def open_application(app_name: str) -> str:
    """
    Open an application on macOS (e.g., 'WhatsApp', 'Spotify', 'Google Chrome', 'Notes', 'Calculator', 'Terminal', 'Visual Studio Code').
    If no native macOS app exists (e.g. 'Blinkit', 'Amazon', 'YouTube', 'Netflix'), automatically opens it in Brave Browser in full screen.
    Always opens and expands in Entire Screen mode.
    """
    try:
        cmd = ["open", "-a", app_name]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            time.sleep(0.5)
            if app_name.lower() == "whatsapp":
                from blacky.tools.whatsapp import _ensure_whatsapp_running
                _ensure_whatsapp_running()
            make_window_fullscreen(app_name)
            res = f"Application '{app_name}' launched successfully in full screen."
            registry.log_call("open_application", {"app_name": app_name}, res, success=True)
            return res
        else:
            # If no native Mac desktop application is installed, fallback to the system default browser in Entire Screen mode
            clean_key = re.sub(r'[^a-zA-Z0-9]', '', app_name).lower()
            url = COMMON_WEB_SERVICES.get(clean_key)
            if not url:
                if "." in app_name:
                    url = f"https://{app_name.strip()}"
                else:
                    url = f"https://www.{clean_key}.com"
            from blacky.tools.web import open_in_browser, get_default_browser
            default_b = get_default_browser()
            open_in_browser(url, browser=default_b)
            res = f"No native Mac app found for '{app_name}'. Opened {url} in {default_b} in full screen."
            registry.log_call("open_application", {"app_name": app_name}, res, success=True)
            return res
    except Exception as e:
        err = f"Failed to open '{app_name}': {str(e)}"
        registry.log_call("open_application", {"app_name": app_name}, err, success=False)
        return err


@registry.register
def set_system_volume(level: int) -> str:
    """
    Set macOS system audio volume from 0 to 100.
    """
    try:
        level = max(0, min(100, level))
        # AppleScript volume is 0-7 or 0-100 output volume
        script = f"set volume output volume {level}"
        subprocess.run(["osascript", "-e", script], check=True)
        res = f"System volume set to {level}%."
        registry.log_call("set_system_volume", {"level": level}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to set system volume: {str(e)}"
        registry.log_call("set_system_volume", {"level": level}, err, success=False)
        return err


@registry.register
def send_notification(title: str, message: str) -> str:
    """
    Display a native macOS Notification banner.
    """
    try:
        clean_title = title.replace('"', '\\"')
        clean_message = message.replace('"', '\\"')
        script = f'display notification "{clean_message}" with title "{clean_title}"'
        subprocess.run(["osascript", "-e", script], check=True)
        res = f"Notification delivered: '{title}'"
        registry.log_call("send_notification", {"title": title, "message": message}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to send notification: {str(e)}"
        registry.log_call("send_notification", {"title": title, "message": message}, err, success=False)
        return err


@registry.register
def get_system_info() -> str:
    """
    Get current macOS system health: CPU usage, RAM utilization, and battery percentage.
    """
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        battery = psutil.sensors_battery()

        ram_used_gb = ram.used / (1024 ** 3)
        ram_total_gb = ram.total / (1024 ** 3)

        info = [
            f"CPU Usage: {cpu}%",
            f"RAM Usage: {ram.percent}% ({ram_used_gb:.1f} GB used of {ram_total_gb:.1f} GB)",
        ]

        if battery:
            plugged = "Plugged in / Charging" if battery.power_plugged else "On Battery"
            info.append(f"Battery: {battery.percent}% ({plugged})")
        else:
            info.append("Battery: Desktop Mac or Battery status unavailable")

        res = "macOS System Status:\n" + "\n".join(info)
        registry.log_call("get_system_info", {}, f"CPU: {cpu}%, RAM: {ram.percent}%", success=True)
        return res
    except Exception as e:
        err = f"Failed to get system info: {str(e)}"
        registry.log_call("get_system_info", {}, err, success=False)
        return err


@registry.register
def lock_mac_screen() -> str:
    """
    Lock the macOS screen immediately.
    """
    try:
        subprocess.run(["pmset", "displaysleepnow"], check=True)
        res = "macOS screen locked successfully."
        registry.log_call("lock_mac_screen", {}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to lock macOS screen: {str(e)}"
        registry.log_call("lock_mac_screen", {}, err, success=False)
        return err


@registry.register
def wake_mac_display() -> str:
    """
    Wake up the macOS display from sleep and illuminate the screen.
    """
    try:
        subprocess.run(["caffeinate", "-u", "-t", "2"], check=True)
        res = "macOS display illuminated and woken up from sleep."
        registry.log_call("wake_mac_display", {}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to wake macOS display: {str(e)}"
        registry.log_call("wake_mac_display", {}, err, success=False)
        return err


@registry.register
def get_mac_screen_lock_status() -> str:
    """
    Check whether the macOS display is currently locked or unlocked.
    """
    try:
        import ctypes
        cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

        cg.CGSessionCopyCurrentDictionary.restype = ctypes.c_void_p
        cf.CFDictionaryGetValue.restype = ctypes.c_void_p
        cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFBooleanGetValue.restype = ctypes.c_bool
        cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]

        session = cg.CGSessionCopyCurrentDictionary()
        if not session:
            return "Screen status: Unlocked (Active console session)"
        key = cf.CFStringCreateWithCString(None, b"CGSSessionScreenIsLocked", 0x08000100)
        val = cf.CFDictionaryGetValue(session, key)
        is_locked = cf.CFBooleanGetValue(val) if val else False
        status_str = "Locked" if is_locked else "Unlocked"
        res = f"macOS Screen Status: {status_str}"
        registry.log_call("get_mac_screen_lock_status", {}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to get screen lock status: {str(e)}"
        registry.log_call("get_mac_screen_lock_status", {}, err, success=False)
        return err


@registry.register
def run_applescript(script: str) -> str:
    """
    Run custom AppleScript automation on macOS for deep control of apps (Finder, Music, Safari, Mail).
    """
    try:
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
        if proc.returncode == 0:
            res = f"AppleScript executed successfully. Output: {proc.stdout.strip() or 'OK'}"
            registry.log_call("run_applescript", {"snippet": script[:50]}, res, success=True)
            return res
        else:
            err = f"AppleScript error: {proc.stderr.strip()}"
            registry.log_call("run_applescript", {"snippet": script[:50]}, err, success=False)
            return err
    except Exception as e:
        err = f"Failed to run AppleScript: {str(e)}"
        registry.log_call("run_applescript", {"snippet": script[:50]}, err, success=False)
        return err


@registry.register
def press_key(key: str, modifiers: str = "") -> str:
    """
    Simulate pressing a keyboard key on macOS, optionally with modifier keys (e.g. Command, Shift, Option, Control).
    Args:
        key: Key to press (e.g. 'return', 'enter', 'tab', 'escape', 'space', 'down', 'up', 'left', 'right', 'delete', or single character 'f', 'v', 'c').
        modifiers: Comma-separated modifiers, e.g. 'command', 'command,shift', 'option', 'control'.
    """
    try:
        k = key.lower().strip()
        mods = [m.strip().lower() for m in modifiers.split(",") if m.strip()]
        mod_clause = ""
        if mods:
            mod_items = [f"{m} down" for m in mods]
            mod_clause = f" using {{{', '.join(mod_items)}}}"

        key_codes = {
            "return": 36, "enter": 76, "tab": 48, "space": 49,
            "delete": 51, "backspace": 51, "escape": 53,
            "down": 125, "up": 126, "left": 123, "right": 124,
        }

        if k in key_codes:
            code = key_codes[k]
            script = f'tell application "System Events" to key code {code}{mod_clause}'
        else:
            clean_k = key.replace('"', '\\"')
            script = f'tell application "System Events" to keystroke "{clean_k}"{mod_clause}'

        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            res = f"Pressed key '{key}' with modifiers '{modifiers}'."
            registry.log_call("press_key", {"key": key, "modifiers": modifiers}, res, success=True)
            return res
        else:
            err = f"Failed to press key: {proc.stderr.strip()}"
            registry.log_call("press_key", {"key": key, "modifiers": modifiers}, err, success=False)
            return err
    except Exception as e:
        err = f"Error pressing key: {str(e)}"
        registry.log_call("press_key", {"key": key, "modifiers": modifiers}, err, success=False)
        return err


@registry.register
def type_text(text: str) -> str:
    """
    Type or paste text into the active, frontmost application or input field on macOS.
    Supports unicode, emojis, and multiline text.
    """
    try:
        # Use pbcopy + Command+V for fast, 100% reliable emoji and unicode typing
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(text.encode("utf-8"))
        time.sleep(0.1)

        script = 'tell application "System Events" to keystroke "v" using {command down}'
        subprocess.run(["osascript", "-e", script], check=True)
        res = f"Successfully typed/pasted {len(text)} characters into active window."
        registry.log_call("type_text", {"preview": text[:40]}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to type text: {str(e)}"
        registry.log_call("type_text", {"preview": text[:40]}, err, success=False)
        return err


@registry.register
def mouse_click(x: int = -1, y: int = -1) -> str:
    """
    Click the left mouse button at specific (x, y) coordinates on the Mac screen,
    or at the current cursor position if x and y are -1.
    CRITICAL: NEVER use this tool to click contacts, chats, or search results in WhatsApp!
    Always use whatsapp_open_chat, whatsapp_send_message, or whatsapp_start_voice_call for WhatsApp contacts.
    """
    try:
        import ctypes
        class CGPoint(ctypes.Structure):
            _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

        cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        cg.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
        cg.CGEventPost.restype = None
        cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]

        if x >= 0 and y >= 0:
            pt = CGPoint(float(x), float(y))
        else:
            # Current mouse position
            class HIPoint(ctypes.Structure):
                _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]
            cg.CGEventGetLocation.restype = CGPoint
            cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
            ev = cg.CGEventCreate(None)
            pt = cg.CGEventGetLocation(ev)

        down = cg.CGEventCreateMouseEvent(None, 1, pt, 0)
        up = cg.CGEventCreateMouseEvent(None, 2, pt, 0)
        cg.CGEventPost(0, down)
        cg.CGEventPost(0, up)

        res = f"Clicked mouse at ({int(pt.x)}, {int(pt.y)})."
        registry.log_call("mouse_click", {"x": x, "y": y}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to click mouse: {str(e)}"
        registry.log_call("mouse_click", {"x": x, "y": y}, err, success=False)
        return err


@registry.register
def take_screenshot(output_path: str = "") -> str:
    """
    Take a screenshot of the active macOS display and save it to a file.
    Default destination is /tmp/blacky_screenshot.png.
    """
    try:
        import os
        if not output_path:
            output_path = "/tmp/blacky_screenshot.png"
        disp = capture_display_screen(output_path)
        size = os.path.getsize(output_path)
        res = f"Screenshot of display {disp['display_num']} saved to '{output_path}' ({size} bytes, scale={disp['scale']})."
        registry.log_call("take_screenshot", {"output_path": output_path}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to take screenshot: {str(e)}"
        registry.log_call("take_screenshot", {"output_path": output_path}, err, success=False)
        return err


@registry.register
def photo_booth_take_photo() -> str:
    """
    Open Photo Booth application on macOS and capture/click a photo using the Mac camera.
    Use this whenever the user asks to open Photo Booth and click an image, take a picture, or capture a photo.
    """
    try:
        # Launch and activate Photo Booth in full screen
        subprocess.run(["open", "-a", "Photo Booth"], check=True)
        time.sleep(0.5)
        make_window_fullscreen("Photo Booth")
        time.sleep(0.5)  # Allow camera sensor & preview to initialize

        script = '''
        tell application "Photo Booth" to activate
        tell application "System Events"
            tell process "Photo Booth"
                try
                    click menu item "Take Photo" of menu 1 of menu bar item "File" of menu bar 1
                on error
                    try
                        click button "take photo" of group 1 of window 1
                    on error
                        key code 49 -- Spacebar triggers shutter
                    end try
                end try
            end tell
        end tell
        '''
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            res = "Photo Booth opened and photo captured successfully."
            registry.log_call("photo_booth_take_photo", {}, res, success=True)
            return res
        else:
            err = f"Failed to trigger Photo Booth shutter: {proc.stderr.strip()}"
            registry.log_call("photo_booth_take_photo", {}, err, success=False)
            return err
    except Exception as e:
        err = f"Error in Photo Booth: {str(e)}"
        registry.log_call("photo_booth_take_photo", {}, err, success=False)
        return err


def get_display_info(app_name: str = "", target_site: str = "") -> dict:
    """
    Get the display bounds, display index, and scale factor for the display
    hosting `app_name` or `target_site` (or the frontmost window / mouse location if unspecified).
    Returns dict:
        {
            "display_num": int,     # 1-based index for screencapture -D
            "origin_x": float,       # Top-left x in macOS global coordinate points
            "origin_y": float,       # Top-left y in macOS global coordinate points
            "width": float,          # Width in macOS points
            "height": float,         # Height in macOS points
            "scale": float,          # Display scale factor (e.g. 1.0 or 2.0)
        }
    """
    import ctypes
    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]
    class CGSize(ctypes.Structure):
        _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]
    class CGRect(ctypes.Structure):
        _fields_ = [("origin", CGPoint), ("size", CGSize)]

    displays = []
    try:
        cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cg.CGDisplayBounds.restype = CGRect
        cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
        cg.CGGetActiveDisplayList.restype = ctypes.c_int32
        cg.CGGetActiveDisplayList.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]

        count = ctypes.c_uint32(0)
        cg.CGGetActiveDisplayList(0, None, ctypes.byref(count))
        display_ids = (ctypes.c_uint32 * count.value)()
        cg.CGGetActiveDisplayList(count.value, display_ids, ctypes.byref(count))

        for i in range(count.value):
            did = display_ids[i]
            r = cg.CGDisplayBounds(did)
            displays.append({
                "display_num": i + 1,
                "id": did,
                "origin_x": float(r.origin.x),
                "origin_y": float(r.origin.y),
                "width": float(r.size.width),
                "height": float(r.size.height),
                "scale": 1.0,
            })
    except Exception:
        pass

    if not displays:
        displays = [{"display_num": 1, "id": 1, "origin_x": 0.0, "origin_y": 0.0, "width": 1920.0, "height": 1080.0, "scale": 1.0}]

    if len(displays) == 1:
        return displays[0]

    # Multiple displays connected - determine which display contains app_name or target_site
    wx = None
    target_proc = app_name.strip()
    if not target_proc and target_site:
        target_proc = "Brave Browser"

    site_filter = target_site.strip().lower()

    if target_proc:
        script = f'''
        set wx to ""
        if "{target_proc}" is in {{"Brave Browser", "Google Chrome", "Safari", "Microsoft Edge", "Arc"}} then
            try
                tell application "{target_proc}"
                    set foundWin to false
                    if "{site_filter}" is not "" then
                        repeat with w_idx from 1 to (count of windows)
                            set w to window w_idx
                            repeat with i from 1 to (count of tabs of w)
                                set tab_url to ""
                                set tab_title to ""
                                try
                                    set tab_url to (URL of tab i of w as string)
                                end try
                                try
                                    set tab_title to (title of tab i of w as string)
                                end try
                                if (tab_url contains "{site_filter}") or (tab_title contains "{site_filter}") then
                                    set b to bounds of w
                                    set wx to (item 1 of b as string)
                                    set foundWin to true
                                    exit repeat
                                end if
                            end repeat
                            if foundWin then exit repeat
                        end repeat
                    end if
                    if not foundWin then
                        set b to bounds of window 1
                        set wx to (item 1 of b as string)
                    end if
                end tell
            end try
        end if
        if wx is "" then
            tell application "System Events"
                tell process "{target_proc}"
                    repeat with w in windows
                        try
                            if (value of attribute "AXSubrole" of w as string) is "AXStandardWindow" then
                                set s to size of w
                                if (item 2 of s) > 150 then
                                    set pos to position of w
                                    set wx to (item 1 of pos as string)
                                    exit repeat
                                end if
                            end if
                        end try
                    end repeat
                    if wx is "" then
                        repeat with w in windows
                            try
                                set s to size of w
                                if (item 2 of s) > 150 then
                                    set pos to position of w
                                    set wx to (item 1 of pos as string)
                                    exit repeat
                                end if
                            end try
                        end repeat
                    end if
                end tell
            end tell
        end if
        return wx
        '''
        try:
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2)
            out = res.stdout.strip()
            if out:
                wx = float(out)
        except Exception:
            pass

    if wx is None:
        # Check active frontmost process
        script = f'''
        set wx to ""
        tell application "System Events"
            try
                set p to first application process whose frontmost is true
                set pn to name of p
                if pn is in {{"Brave Browser", "Google Chrome", "Safari", "Microsoft Edge", "Arc"}} then
                    try
                        tell application pn
                            set foundWin to false
                            if "{site_filter}" is not "" then
                                repeat with w_idx from 1 to (count of windows)
                                    set w to window w_idx
                                    repeat with i from 1 to (count of tabs of w)
                                        set tab_url to ""
                                        set tab_title to ""
                                        try
                                            set tab_url to (URL of tab i of w as string)
                                        end try
                                        try
                                            set tab_title to (title of tab i of w as string)
                                        end try
                                        if (tab_url contains "{site_filter}") or (tab_title contains "{site_filter}") then
                                            set b to bounds of w
                                            set wx to (item 1 of b as string)
                                            set foundWin to true
                                            exit repeat
                                        end if
                                    end repeat
                                    if foundWin then exit repeat
                                end repeat
                            end if
                            if not foundWin then
                                set b to bounds of window 1
                                set wx to (item 1 of b as string)
                            end if
                        end tell
                    end try
                end if
                if wx is "" then
                    repeat with w in windows of p
                        try
                            if (value of attribute "AXSubrole" of w as string) is "AXStandardWindow" then
                                set s to size of w
                                if (item 2 of s) > 150 then
                                    set pos to position of w
                                    set wx to (item 1 of pos as string)
                                    exit repeat
                                end if
                            end if
                        end try
                    end repeat
                end if
            end try
        end tell
        return wx
        '''
        try:
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2)
            out = res.stdout.strip()
            if out:
                wx = float(out)
        except Exception:
            pass

    if wx is not None:
        for d in displays:
            if d["origin_x"] <= wx < (d["origin_x"] + d["width"]):
                return d

    return displays[0]


def capture_display_screen(output_path: str, app_name: str = "", target_site: str = "") -> dict:
    """
    Capture the screen of the display containing app_name or target_site (or frontmost window).
    Determines and attaches dynamic display scale factor and origin offsets.
    Uses native macOS hardware JPEG compression for .jpg/.jpeg paths for 6x faster capture.
    """
    disp = get_display_info(app_name, target_site=target_site)
    display_num = disp["display_num"]
    if output_path.lower().endswith((".jpg", ".jpeg")):
        cmd = ["screencapture", "-x", "-t", "jpg", "-D", str(display_num), output_path]
    else:
        cmd = ["screencapture", "-x", "-D", str(display_num), output_path]
    subprocess.run(cmd, check=True)

    # Determine exact scale factor from captured image pixel dimensions
    try:
        from PIL import Image
        with Image.open(output_path) as im:
            pw, _ = im.size
        disp["scale"] = max(1.0, round(pw / disp["width"]))
    except Exception:
        disp["scale"] = 2.0 if disp["width"] > 1400 and disp["origin_x"] > 0 else 1.0

    return disp


def get_screen_scale_factor(image_path: str = "") -> float:
    """
    Dynamically determine display scale factor (1.0 for 1080p/standard displays, 2.0 for Retina displays).
    Prevents coordinate misalignments on external or non-Retina monitors.
    """
    if image_path and Path(image_path).exists():
        try:
            from PIL import Image
            with Image.open(image_path) as im:
                w, _ = im.size
            if w <= 1920:
                return 1.0
            elif w >= 2560:
                return 2.0
            disp = get_display_info()
            return max(1.0, round(w / disp["width"]))
        except Exception:
            pass
    disp = get_display_info()
    return disp.get("scale", 1.0)


@registry.register
def screen_click_text(target_text: str, app_name: str = "", match_index: int = 0) -> str:
    """
    Find any visible text, button, or link on the macOS screen using fast OCR and click it.
    Args:
        target_text: The label/text to look for and click (e.g. 'ADD', 'Proceed', 'My Cart', 'Checkout', 'Buy Now').
        app_name: Optional macOS app name to bring frontmost before capturing/clicking (e.g. 'Brave Browser', 'Google Chrome').
        match_index: Index of the match if multiple exist on screen (0 = first match, 1 = second match).
    CRITICAL: NEVER use this tool for WhatsApp contacts! Always use whatsapp_open_chat or whatsapp_send_message.
    """
    try:
        if app_name.strip():
            if app_name.strip().lower() == "whatsapp" and target_text.lower() not in ("call", "video call", "chats", "updates"):
                return "For WhatsApp contacts, please use whatsapp_open_chat or whatsapp_send_message directly to ensure safe contact disambiguation."
            subprocess.run(["osascript", "-e", f'tell application "{app_name}" to activate'])
            time.sleep(0.4)

        ocr_bin = Path(__file__).resolve().parent.parent / "bin" / "ocr_fast"
        if not ocr_bin.exists():
            fallback = Path("/tmp/ocr_fast")
            if fallback.exists():
                ocr_bin = fallback
            else:
                return "OCR tool not available."

        target_site = ""
        try:
            ctx = get_screen_context()
            target_site = ctx.get("active_site", "")
        except Exception:
            pass

        shot_path = "/tmp/blacky_ocr_screen.png"
        disp = capture_display_screen(shot_path, app_name=app_name, target_site=target_site)
        scale = disp["scale"]
        origin_x = disp["origin_x"]
        origin_y = disp["origin_y"]

        out = subprocess.check_output([str(ocr_bin), shot_path], text=True)
        target_clean = target_text.strip()
        target_lower = target_clean.lower()
        target_words = [w for w in re.sub(r'[^a-zA-Z0-9\s]', '', target_lower).split() if len(w) >= 2]

        is_add_btn = (target_lower == "add")
        if is_add_btn:
            from blacky.tools.macos import get_screen_context
            ctx = get_screen_context()
            if ctx.get("active_site") == "blinkit" or "blinkit" in app_name.lower():
                return "For Blinkit grocery products, please invoke blinkit_add_to_cart(query='[Product Name]') with the full product name and variant instead of generic screen_click_text('ADD') to avoid clicking sponsored ads or incorrect products."

        matches = []

        for line in out.splitlines():
            if "->" in line:
                coords_str, found_text = line.split("->", 1)
                found_text = found_text.strip()
                f_lower = found_text.lower()

                # If searching for "ADD" button, skip long sentences/terminal outputs
                if is_add_btn and len(found_text.split()) > 2:
                    continue

                m = re.match(r'\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]', coords_str.strip())
                if not m:
                    continue
                px, py, pw, ph = map(int, m.groups())

                # In browsers, exclude the top address / search input bar (py < 120pt) unless explicitly targeting it
                is_browser = any(b in app_name.lower() for b in ("brave", "chrome", "safari", "edge", "browser")) or (not app_name)
                is_search_box_target = any(k in target_lower for k in ("search", "address", "url", "tab", "input box", "search bar"))
                if is_browser and not is_search_box_target and py < int(120 * scale):
                    continue

                score = 0
                # Level 1: Exact match
                if f_lower == target_lower:
                    score = 100
                # Level 2: Whole word boundary match
                elif re.search(rf'\b{re.escape(target_lower)}\b', f_lower):
                    score = 50
                # Level 3: All words present
                elif target_words and all(w in f_lower for w in target_words):
                    score = 30
                # Level 4: Substring (only if not a short token like "add")
                elif not is_add_btn and target_lower in f_lower:
                    score = 10

                if score > 0:
                    lx = int((px + pw / 2) / scale)
                    ly = int((py + ph / 2) / scale)
                    gx = int(origin_x + lx)
                    gy = int(origin_y + ly)
                    matches.append((score, found_text, gx, gy))

        if not matches:
            res = f"Text '{target_text}' not found on screen."
            registry.log_call("screen_click_text", {"target_text": target_text}, res, success=False)
            return res

        # Sort by match score descending, then by vertical coordinate (top-to-bottom)
        matches.sort(key=lambda x: (-x[0], x[3]))
        idx = min(match_index, len(matches) - 1)
        _, found_label, click_x, click_y = matches[idx]
        mouse_click(click_x, click_y)
        res = f"Found '{found_label}' on screen and clicked at ({click_x}, {click_y})."
        registry.log_call("screen_click_text", {"target_text": target_text, "app_name": app_name}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to click text on screen: {str(e)}"
        registry.log_call("screen_click_text", {"target_text": target_text}, err, success=False)
        return err
