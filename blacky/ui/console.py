"""
Rich terminal UI utilities for BlackyAgent.
"""

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.table import Table

console = Console()


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


def print_mobile_qr(ip_address: str, port: int, public_url: str | None = None) -> None:
    """Print mobile remote instructions and ASCII QR code."""
    url = f"http://{ip_address}:{port}"
    qr_target = public_url or url
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
