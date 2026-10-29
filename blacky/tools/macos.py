"""
macOS system control and automation tools for BlackyAgent.
"""

import subprocess
import shutil
import psutil
from blacky.tools.base import registry


@registry.register
def open_application(app_name: str) -> str:
    """
    Open an application on macOS (e.g., 'Spotify', 'Google Chrome', 'Notes', 'Calculator', 'Terminal', 'Visual Studio Code').
    """
    try:
        cmd = ["open", "-a", app_name]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            res = f"Application '{app_name}' launched successfully."
            registry.log_call("open_application", {"app_name": app_name}, res, success=True)
            return res
        else:
            err = f"Could not open application '{app_name}': {proc.stderr.strip()}"
            registry.log_call("open_application", {"app_name": app_name}, err, success=False)
            return err
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
