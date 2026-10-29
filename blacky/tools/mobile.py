"""
Mobile device control tools for BlackyAgent (iOS and Android).
Integrates pymobiledevice3, ADB, Apple Shortcuts, and Messages.
"""

import json
import shutil
import subprocess
from blacky.tools.base import registry


def _find_adb() -> str | None:
    """Locate adb binary if present."""
    paths = [
        shutil.which("adb"),
        "/opt/homebrew/bin/adb",
        "/usr/local/bin/adb",
        "~/Library/Android/sdk/platform-tools/adb",
    ]
    for p in paths:
        if p and shutil.which(p):
            return p
    return None


@registry.register
def mobile_get_connected_devices() -> str:
    """
    Check and list all connected mobile devices (both iOS and Android via USB or Wi-Fi).
    """
    devices_info = []

    # 1. Check iOS devices via pymobiledevice3
    pmd = shutil.which("pymobiledevice3") or "/Library/Frameworks/Python.framework/Versions/3.12/bin/pymobiledevice3"
    try:
        proc = subprocess.run([pmd, "usbmux", "list"], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            out = proc.stdout.strip()
            if out and out != "[]":
                devices_info.append(f"🍏 iOS Devices (via usbmux):\n{out}")
            else:
                devices_info.append("🍏 iOS Devices: No iOS device connected via USB/usbmux.")
    except Exception as e:
        devices_info.append(f"🍏 iOS: Check failed ({e})")

    # 2. Check Android devices via ADB
    adb = _find_adb()
    if adb:
        try:
            proc = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True, timeout=5)
            if proc.returncode == 0:
                lines = [line.strip() for line in proc.stdout.splitlines() if line.strip() and not line.startswith("*")]
                if len(lines) > 1:
                    devices_info.append("🤖 Android Devices (via ADB):\n" + "\n".join(lines[1:]))
                else:
                    devices_info.append("🤖 Android Devices: No Android device connected via ADB.")
        except Exception as e:
            devices_info.append(f"🤖 Android: ADB check error ({e})")
    else:
        devices_info.append("🤖 Android: ADB tool not installed.")

    res = "\n\n".join(devices_info)
    registry.log_call("mobile_get_connected_devices", {}, "Checked mobile connections", success=True)
    return res


@registry.register
def mobile_android_command(command: str) -> str:
    """
    Execute an ADB shell command on a connected Android phone/tablet.
    Examples:
    - 'am start -a android.intent.action.VIEW -d https://google.com' (open website on phone)
    - 'input keyevent 26' (press power button)
    - 'input keyevent 24' (volume up)
    - 'screencap -p /sdcard/screen.png' (take screenshot)
    """
    adb = _find_adb()
    if not adb:
        err = "Error: Android ADB tool is not found."
        registry.log_call("mobile_android_command", {"command": command}, err, success=False)
        return err

    try:
        full_cmd = [adb, "shell"] + command.split()
        proc = subprocess.run(full_cmd, capture_output=True, text=True, timeout=15)
        res = proc.stdout.strip() or proc.stderr.strip() or "Command sent to Android device successfully."
        registry.log_call("mobile_android_command", {"command": command}, res, success=(proc.returncode == 0))
        return res
    except Exception as e:
        err = f"Failed to execute Android command: {str(e)}"
        registry.log_call("mobile_android_command", {"command": command}, err, success=False)
        return err


@registry.register
def mobile_run_shortcut(shortcut_name: str, input_text: str = "") -> str:
    """
    Run an Apple Shortcut by name. Since Shortcuts sync across iCloud, shortcuts can control
    actions on iPhone/iPad or smart home devices.
    """
    try:
        cmd = ["shortcuts", "run", shortcut_name]
        if input_text:
            cmd.extend(["-i", input_text])

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if proc.returncode == 0:
            res = f"Apple Shortcut '{shortcut_name}' ran successfully: {proc.stdout.strip() or 'OK'}"
            registry.log_call("mobile_run_shortcut", {"shortcut_name": shortcut_name}, res, success=True)
            return res
        else:
            err = f"Failed to run shortcut '{shortcut_name}': {proc.stderr.strip()}"
            registry.log_call("mobile_run_shortcut", {"shortcut_name": shortcut_name}, err, success=False)
            return err
    except Exception as e:
        err = f"Error running shortcut '{shortcut_name}': {str(e)}"
        registry.log_call("mobile_run_shortcut", {"shortcut_name": shortcut_name}, err, success=False)
        return err


@registry.register
def mobile_send_imessage(phone_or_email: str, message: str) -> str:
    """
    Send an SMS or iMessage via macOS Apple Messages app.
    WARNING: Do NOT use this tool for WhatsApp requests! For WhatsApp messaging,
    always use `whatsapp_send_message` instead.
    """
    try:
        clean_target = phone_or_email.replace('"', '\\"')
        clean_msg = message.replace('"', '\\"')
        applescript = f'''
        tell application "Messages"
            set targetService to 1st service whose service type = iMessage
            set targetBuddy to participant "{clean_target}" of targetService
            send "{clean_msg}" to targetBuddy
        end tell
        '''
        proc = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            res = f"Message successfully sent to {phone_or_email}"
            registry.log_call("mobile_send_imessage", {"target": phone_or_email}, res, success=True)
            return res
        else:
            err = f"Failed to send message: {proc.stderr.strip()}"
            registry.log_call("mobile_send_imessage", {"target": phone_or_email}, err, success=False)
            return err
    except Exception as e:
        err = f"Failed to send iMessage: {str(e)}"
        registry.log_call("mobile_send_imessage", {"target": phone_or_email}, err, success=False)
        return err
