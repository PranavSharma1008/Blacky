"""
Rich terminal UI utilities for BlackyAgent.
"""

import sys
import threading
import time
import shutil

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# Screen Analysis Animation
# ---------------------------------------------------------------------------
# Visual states that reflect the REAL agent screen-observation lifecycle.
# The animation is driven exclusively by agent execution states (never on its own).

SCREEN_STATES: dict[str, tuple[str, str]] = {
    "observing": ("Observing Screen", "🛰️"),
    "analyzing": ("Analyzing Interface", "🔍"),
    "identifying": ("Identifying Elements", "🎯"),
    "processing": ("Processing Instruction", "🧠"),
    "waiting_for_user": ("Waiting for User", "⏳"),
    "executing": ("Executing Action", "⚡"),
    "verifying": ("Verifying Action", "🧪"),
    "task_completed": ("Task Completed", "🎉"),
    "error_recovery": ("Error Recovery", "⚠️"),
}

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

_screen_state_lock = threading.Lock()
_screen_state = "idle"
_screen_detail = ""
_screen_frame_index = 0
_screen_stop_event: threading.Event | None = None
_screen_thread: threading.Thread | None = None


def _clean_terminal_line() -> None:
    """Clear the active terminal animation line cleanly within terminal width."""
    try:
        width = max(20, min(100, shutil.get_terminal_size(fallback=(80, 24)).columns - 1))
        sys.stdout.write("\r" + " " * width + "\r")
        sys.stdout.flush()
    except Exception:
        pass


def get_screen_state() -> str:
    """Return the current screen-analysis state (e.g. 'observing', 'executing')."""
    with _screen_state_lock:
        return _screen_state


def start_screen_analysis(state: str = "observing", detail: str = "") -> None:
    """
    Start (or transition) the screen-analysis animation in the given state.
    Strictly single-threaded: never leaks background worker threads.
    If an animation is already running, seamlessly updates the state without spawning new threads.
    """
    global _screen_state, _screen_detail, _screen_stop_event, _screen_thread

    with _screen_state_lock:
        _screen_state = state
        _screen_detail = detail or ""

        # If a thread is already actively running and healthy, simply updating the state is sufficient
        if _screen_thread is not None and _screen_thread.is_alive() and _screen_stop_event is not None and not _screen_stop_event.is_set():
            return

        # Stop and join any stale thread before launching a new one
        if _screen_stop_event is not None:
            _screen_stop_event.set()
        if _screen_thread is not None and _screen_thread.is_alive():
            try:
                _screen_thread.join(timeout=0.2)
            except Exception:
                pass

        _screen_stop_event = threading.Event()
        stop_event = _screen_stop_event

    def _worker(event: threading.Event) -> None:
        idx = 0
        while not event.is_set():
            with _screen_state_lock:
                state_now = _screen_state
                detail_now = _screen_detail

            # Do NOT animate or spin when waiting for user input or in terminal/idle states
            if state_now in ("idle", "task_completed", "waiting_for_user"):
                break

            label, icon = SCREEN_STATES.get(state_now, ("Observing Screen", "🛰️"))
            spinner = _SPINNER_FRAMES[idx % len(_SPINNER_FRAMES)]
            idx += 1
            line = f"{icon} Screen Analysis: {label} {spinner}"
            if detail_now.strip():
                line += f" — {detail_now.strip()}"

            try:
                # Keep strictly within terminal columns to prevent line-wrapping artifacts
                term_cols = max(20, min(100, shutil.get_terminal_size(fallback=(80, 24)).columns - 1))
                clipped = line[:term_cols].ljust(term_cols)
                sys.stdout.write("\r" + clipped + "\r")
                sys.stdout.flush()
            except Exception:
                return

            event.wait(0.12)

        _clean_terminal_line()

    if sys.stdout.isatty():
        _screen_thread = threading.Thread(target=lambda: _worker(stop_event), daemon=True)
        _screen_thread.start()
    else:
        # Non-interactive terminals: do not spam lines, keep clean
        pass


def update_screen_analysis(detail: str = "") -> None:
    """Update the detail text shown inside the running screen-analysis animation."""
    global _screen_detail
    with _screen_state_lock:
        _screen_detail = detail or ""


def stop_screen_analysis(final_state: str = "task_completed") -> None:
    """Stop the screen-analysis animation cleanly and render the final state ONCE."""
    global _screen_state, _screen_detail, _screen_stop_event, _screen_thread

    with _screen_state_lock:
        _screen_state = final_state
        _screen_detail = ""
        stop_event = _screen_stop_event
        _screen_stop_event = None
        thread = _screen_thread
        _screen_thread = None

    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        try:
            thread.join(timeout=0.4)
        except Exception:
            pass

    _clean_terminal_line()

    label, icon = SCREEN_STATES.get(final_state, ("Task Completed", "🎉"))
    if final_state == "task_completed":
        console.print(f"[bold green]{icon} Screen Analysis: {label}[/bold green]")
    elif final_state == "waiting_for_user":
        console.print(f"[bold yellow]{icon} Screen Analysis: {label}[/bold yellow]")
    elif final_state == "error_recovery":
        console.print(f"[bold red]{icon} Screen Analysis: {label}[/bold red]")


def clear_screen_analysis() -> None:
    """Stop the animation without printing a final state line."""
    global _screen_state, _screen_detail, _screen_stop_event, _screen_thread

    with _screen_state_lock:
        _screen_state = "idle"
        _screen_detail = ""
        stop_event = _screen_stop_event
        _screen_stop_event = None
        thread = _screen_thread
        _screen_thread = None

    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        try:
            thread.join(timeout=0.4)
        except Exception:
            pass

    _clean_terminal_line()


def print_screen_state(state: str, detail: str = "") -> None:
    """Public helper: render a screen-analysis activity state."""
    start_screen_analysis(state, detail)
    if state == "task_completed":
        stop_screen_analysis("task_completed")


def show_banner() -> None:
    """Print the BlackyAgent Siri-style startup banner."""
    banner_text = Text()
    banner_text.append("✦ ", style="bold cyan")
    banner_text.append("BLACKY AGENT", style="bold magenta")
    banner_text.append(" ✦\n", style="bold cyan")
    banner_text.append("Your Autonomous AI Assistant (Siri-like with Full Control)\n", style="italic white")
    banner_text.append("• Voice (Push-to-Talk)  • Mobile Remote  • Full System Access", style="dim cyan")

    panel = Panel(
        banner_text,
        border_style="magenta",
        padding=(1, 2),
        title="[bold yellow]Ready[/bold yellow]",
        subtitle="[dim]Say or type 'help' for guidance[/dim]",
    )
    console.print(panel)


def print_agent_thought(thought: str) -> None:
    """Display agent reasoning step."""
    console.print(f"[dim magenta]🤔 Thinking:[/dim magenta] [dim italic]{thought}[/dim italic]")


def print_tool_call(tool_name: str, args: dict) -> None:
    """Display when a tool is being called."""
    args_str = ", ".join(f"[bold]{k}[/bold]={repr(v)[:50]}" for k, v in args.items())
    console.print(f"  [bold cyan]⚡ Tool Execution:[/bold cyan] [yellow]{tool_name}[/yellow]({args_str})")


def print_tool_result(tool_name: str, result: str, success: bool = True) -> None:
    """Display tool execution result."""
    style = "green" if success else "red"
    icon = "✓" if success else "✗"
    preview = result.strip()
    if len(preview) > 180:
        preview = preview[:180] + "..."
    console.print(f"    [dim {style}]{icon} {tool_name}: {preview}[/dim {style}]")


def print_agent_response(response: str) -> None:
    """Render agent markdown response cleanly."""
    console.print()
    console.print(Panel(Markdown(response), title="[bold magenta]Blacky[/bold magenta]", border_style="cyan"))


def print_user_prompt(text: str) -> None:
    """Echo user prompt nicely."""
    console.print(f"\n[bold green]You:[/bold green] {text}")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[bold blue]ℹ[/bold blue] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]✖[/bold red] {message}")


def print_mobile_qr(ip_address: str, port: int, public_url: str | None = None, token: str | None = None) -> None:
    """Print mobile remote instructions and ASCII QR code."""
    url = f"http://{ip_address}:{port}"
    suffix = f"?token={token}" if token else ""
    qr_target = f"{public_url or url}{suffix}"
    url = f"{url}{suffix}"
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(qr_target)
        qr.make(fit=True)
        console.print(f"\n[bold green]📱 Mobile Remote Mode Activated![/bold green]")
        if public_url:
            console.print(f"🌐 [bold magenta]Public 5G/Mobile URL:[/bold magenta] [bold cyan]{public_url}[/bold cyan] [green](Works Anywhere / Mobile Data)[/green]")
            console.print(f"🏠 [bold blue]Local Wi-Fi URL:[/bold blue] [cyan]{url}[/cyan] [dim](Requires same Wi-Fi network)[/dim]\n")
            console.print("Scan this QR code with your phone camera to open:")
        else:
            console.print(f"Scan this QR code with your phone camera or open:\n[bold cyan]{url}[/bold cyan]\n")
        qr.print_ascii(invert=True)
    except Exception:
        console.print(f"\n[bold green]📱 Mobile Remote Mode Activated![/bold green]")
        if public_url:
            console.print(f"🌐 [bold magenta]Public 5G/Mobile URL:[/bold magenta] [bold cyan]{public_url}[/bold cyan]")
            console.print(f"🏠 [bold blue]Local Wi-Fi URL:[/bold blue] [cyan]{url}[/cyan]\n")
        else:
            console.print(f"Open this URL on your phone's browser:\n[bold cyan]{url}[/bold cyan]\n")
