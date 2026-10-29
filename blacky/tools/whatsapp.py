"""
WhatsApp desktop automation tools for BlackyAgent on macOS.
Supports opening chats, searching contacts, sending messages, and initiating video/voice calls.
"""

import subprocess
import time
import re
from blacky.tools.base import registry


def _ensure_whatsapp_running() -> bool:
    """Ensure WhatsApp application is launched, open, and frontmost on macOS."""
    try:
        subprocess.run(["open", "whatsapp://"], capture_output=True, timeout=5)
        time.sleep(0.4)
        script = '''
        tell application "WhatsApp" to activate
        tell application "System Events"
            tell process "WhatsApp"
                if (count of windows) is 0 then
                    try
                        click menu item "WhatsApp" of menu "Window" of menu bar 1
                    on error
                        keystroke "n" using {command down}
                    end try
                    delay 0.4
                end if
            end tell
        end tell
        '''
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def _set_clipboard(text: str) -> None:
    """Copy text to macOS system clipboard using pbcopy for reliable emoji & unicode input."""
    proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    proc.communicate(text.encode("utf-8"))


def _clean_phone(target: str) -> str | None:
    """Check if target string is a phone number."""
    cleaned = re.sub(r"[\s\-\(\)]", "", target.strip())
    if re.match(r"^\+?\d{7,15}$", cleaned):
        return cleaned
    return None


@registry.register
def whatsapp_open_chat(contact: str) -> str:
    """
    Open a chat with a specific contact name (e.g. 'Satyam') or phone number in WhatsApp on macOS.
    Use this when the user asks to open WhatsApp and search for or open a chat with someone.
    """
    if not _ensure_whatsapp_running():
        err = "Could not open WhatsApp. Please ensure WhatsApp is installed in /Applications/WhatsApp.app."
        registry.log_call("whatsapp_open_chat", {"contact": contact}, err, success=False)
        return err

    phone = _clean_phone(contact)
    if phone:
        # Use direct URL scheme for phone numbers
        url = f"whatsapp://send?phone={phone}"
        subprocess.run(["open", url], capture_output=True)
        time.sleep(0.8)
        res = f"Opened WhatsApp chat with phone number: {phone}"
        registry.log_call("whatsapp_open_chat", {"contact": contact}, res, success=True)
        return res

    # Use UI search for contact names
    clean_contact = contact.replace('"', '\\"').strip()
    script = f'''
    tell application "WhatsApp" to activate
    delay 0.4
    tell application "System Events"
        tell process "WhatsApp"
            -- Focus search box
            keystroke "f" using {{command down}}
            delay 0.3
            keystroke "a" using {{command down}}
            delay 0.1
            keystroke "{clean_contact}"
            delay 0.8
            -- Select first contact result
            key code 125 -- Down arrow
            delay 0.2
            key code 36  -- Return
            delay 0.4
        end tell
    end tell
    '''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    if proc.returncode == 0:
        res = f"Opened WhatsApp chat for contact: '{contact}'"
        registry.log_call("whatsapp_open_chat", {"contact": contact}, res, success=True)
        return res
    else:
        err = f"Failed to search and open WhatsApp chat for '{contact}': {proc.stderr.strip()}"
        registry.log_call("whatsapp_open_chat", {"contact": contact}, err, success=False)
        return err


@registry.register
def whatsapp_send_message(contact: str, message: str) -> str:
    """
    Send a message to a contact name (e.g. 'Satyam') or phone number on WhatsApp.
    ALWAYS use this tool when the user wants to text, chat, or send a message on WhatsApp.
    NEVER use mobile_send_imessage for WhatsApp!
    """
    if not _ensure_whatsapp_running():
        err = "Could not open WhatsApp. Please ensure WhatsApp is installed."
        registry.log_call("whatsapp_send_message", {"contact": contact, "message": message}, err, success=False)
        return err

    phone = _clean_phone(contact)
    if phone:
        import urllib.parse
        encoded_msg = urllib.parse.quote(message)
        url = f"whatsapp://send?phone={phone}&text={encoded_msg}"
        subprocess.run(["open", url], capture_output=True)
        time.sleep(1.0)
        # Press Return to send
        press_return = '''
        tell application "WhatsApp" to activate
        tell application "System Events"
            tell process "WhatsApp"
                key code 36
            end tell
        end tell
        '''
        subprocess.run(["osascript", "-e", press_return], capture_output=True)
        res = f"Message sent to {contact} via WhatsApp: '{message}'"
        registry.log_call("whatsapp_send_message", {"contact": contact}, res, success=True)
        return res

    # For contact names, navigate to chat and paste-send message
    clean_contact = contact.replace('"', '\\"').strip()
    _set_clipboard(message)

    script = f'''
    tell application "WhatsApp" to activate
    delay 0.4
    tell application "System Events"
        tell process "WhatsApp"
            -- Focus search
            keystroke "f" using {{command down}}
            delay 0.3
            keystroke "a" using {{command down}}
            delay 0.1
            keystroke "{clean_contact}"
            delay 0.8
            -- Navigate to first search result
            key code 125 -- Down arrow
            delay 0.2
            key code 36  -- Return to open chat
            delay 0.5
            -- Paste message and send
            keystroke "v" using {{command down}}
            delay 0.2
            key code 36 -- Return to send message
            delay 0.3
        end tell
    end tell
    '''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    if proc.returncode == 0:
        res = f"Message successfully sent to {contact} on WhatsApp: '{message}'"
        registry.log_call("whatsapp_send_message", {"contact": contact}, res, success=True)
        return res
    else:
        err = f"Failed to send WhatsApp message to '{contact}': {proc.stderr.strip()}"
        registry.log_call("whatsapp_send_message", {"contact": contact}, err, success=False)
        return err


@registry.register
def whatsapp_start_video_call(contact: str = "") -> str:
    """
    Start a WhatsApp Video Call with a specified contact name (e.g. 'Satyam'),
    or with the currently active WhatsApp chat if contact is empty.
    ALWAYS use this when the user says 'video call on WhatsApp' or 'click on video call'.
    """
    if not _ensure_whatsapp_running():
        err = "Could not open WhatsApp. Please ensure WhatsApp is installed."
        registry.log_call("whatsapp_start_video_call", {"contact": contact}, err, success=False)
        return err

    # If contact provided, verify if chat is already open; if not, open it
    if contact.strip():
        check_script = '''
        tell application "System Events"
            tell process "WhatsApp"
                repeat with mb in (menu bar items of menu bar 1)
                    if (name of mb as string) contains "Chat" then
                        repeat with mi in (menu items of menu 1 of mb)
                            if (name of mi as string) contains "Video Call" then
                                return (value of attribute "AXEnabled" of mi as string)
                            end if
                        end repeat
                    end if
                end repeat
                return "false"
            end tell
        end tell
        '''
        check_proc = subprocess.run(["osascript", "-e", check_script], capture_output=True, text=True)
        if "true" not in check_proc.stdout.lower():
            whatsapp_open_chat(contact)
            time.sleep(0.5)

    # Click Video Call menu item under Chat menu
    script = '''
    tell application "WhatsApp" to activate
    delay 0.3
    tell application "System Events"
        tell process "WhatsApp"
            repeat with mb in (menu bar items of menu bar 1)
                if (name of mb as string) contains "Chat" then
                    repeat with mi in (menu items of menu 1 of mb)
                        if (name of mi as string) contains "Video Call" then
                            click mi
                            return "Video Call started"
                        end if
                    end repeat
                end if
            end repeat
            return "Video Call menu item not currently available"
        end tell
    end tell
    '''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    out = proc.stdout.strip()
    if proc.returncode == 0 and "Video Call started" in out:
        target_name = f"with '{contact}'" if contact.strip() else "in active chat"
        res = f"WhatsApp Video Call initiated {target_name}."
        registry.log_call("whatsapp_start_video_call", {"contact": contact}, res, success=True)
        return res
    else:
        err = f"Could not start Video Call: {proc.stderr.strip() or out}"
        registry.log_call("whatsapp_start_video_call", {"contact": contact}, err, success=False)
        return err


@registry.register
def whatsapp_start_voice_call(contact: str = "") -> str:
    """
    Start a WhatsApp Voice / Audio Call with a specified contact name (e.g. 'Satyam'),
    or with the currently active WhatsApp chat if contact is empty.
    """
    if not _ensure_whatsapp_running():
        err = "Could not open WhatsApp. Please ensure WhatsApp is installed."
        registry.log_call("whatsapp_start_voice_call", {"contact": contact}, err, success=False)
        return err

    # If contact provided, verify if chat is already open; if not, open it
    if contact.strip():
        check_script = '''
        tell application "System Events"
            tell process "WhatsApp"
                repeat with mb in (menu bar items of menu bar 1)
                    if (name of mb as string) contains "Chat" then
                        repeat with mi in (menu items of menu 1 of mb)
                            if (name of mi as string) contains "Video Call" then
                                return (value of attribute "AXEnabled" of mi as string)
                            end if
                        end repeat
                    end if
                end repeat
                return "false"
            end tell
        end tell
        '''
        check_proc = subprocess.run(["osascript", "-e", check_script], capture_output=True, text=True)
        if "true" not in check_proc.stdout.lower():
            whatsapp_open_chat(contact)
            time.sleep(0.5)

    # Click Voice Call menu item under Chat menu
    script = '''
    tell application "WhatsApp" to activate
    delay 0.3
    tell application "System Events"
        tell process "WhatsApp"
            repeat with mb in (menu bar items of menu bar 1)
                if (name of mb as string) contains "Chat" then
                    repeat with mi in (menu items of menu 1 of mb)
                        if (name of mi as string) contains "Voice Call" then
                            click mi
                            return "Voice Call started"
                        end if
                    end repeat
                end if
            end repeat
            return "Voice Call menu item not currently available"
        end tell
    end tell
    '''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    out = proc.stdout.strip()
    if proc.returncode == 0 and "Voice Call started" in out:
        target_name = f"with '{contact}'" if contact.strip() else "in active chat"
        res = f"WhatsApp Voice Call initiated {target_name}."
        registry.log_call("whatsapp_start_voice_call", {"contact": contact}, res, success=True)
        return res
    else:
        err = f"Could not start Voice Call: {proc.stderr.strip() or out}"
        registry.log_call("whatsapp_start_voice_call", {"contact": contact}, err, success=False)
        return err
