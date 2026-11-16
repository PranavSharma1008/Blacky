"""
Main CLI entry point for BlackyAgent.
Supports Interactive REPL, Push-to-Talk Voice mode, Mobile Remote mode, and one-shot execution.
"""

import sys
import argparse
from blacky.config import config
from blacky.core.agent import BlackyAgent
from blacky.core.ollama_client import OllamaProvider
from blacky.voice import voice_listener, voice_engine, post_system_notification
from blacky.ui.console import (
    console,
    show_banner,
    print_user_prompt,
    print_info,
    print_error,
    clear_screen_analysis,
)


def run_repl(agent: BlackyAgent) -> None:
    """Run interactive terminal chat REPL."""
    show_banner()
    console.print("[dim]Type your command, or type 'exit' or 'quit' to close.[/dim]\n")

    while True:
        try:
            clear_screen_analysis()
            prompt = console.input("[bold magenta]Blacky 🐾 > [/bold magenta]").strip()
            if not prompt:
                continue
            if prompt.lower() in ("exit", "quit", "q", "bye"):
                console.print("\n[bold cyan]Goodbye! Have a great day![/bold cyan]")
                if agent.speak_replies:
                    voice_engine.speak("Goodbye! Have a great day!", wait=True)
                break

            print_user_prompt(prompt)
            agent.run(prompt)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session closed.[/dim]")
            break


def run_voice_loop(agent: BlackyAgent) -> None:
    """Run Global Push-to-Talk voice loop."""
    show_banner()
    console.print("[bold cyan]🎙️  Global Siri Voice Mode Active[/bold cyan]")
    console.print(
        "[dim]👉 Hold [Fn] (Globe 🌐) or [Option] (⌥) anywhere across macOS to speak (e.g. while in Blinkit, Chrome, Safari).\n"
        "   Release when done. Or press [ENTER] in terminal. Say 'exit' to quit.[/dim]\n"
    )

    if agent.speak_replies:
        voice_engine.speak("Blacky is listening. How can I help you?", wait=False)

    while True:
        try:
            user_text = voice_listener.listen_push_to_talk()
            if not user_text:
                continue

            if user_text.lower() in ("exit", "quit", "goodbye", "bye", "stop"):
                console.print("\n[bold cyan]Goodbye![/bold cyan]")
                if agent.speak_replies:
                    voice_engine.speak("Goodbye!", wait=True)
                break

            # Optional correction window: the transcript is shown and the user
            # can fix it before anything is executed.
            if config.BLACKY_STT_CONFIRM:
                corrected = console.input(
                    f"[bold green]Heard:[/bold green] [italic]\"{user_text}\"[/italic] "
                    "[dim](press Enter to run, or type the corrected command)[/dim]\n> "
                ).strip()
                if corrected:
                    user_text = corrected

            print_user_prompt(user_text)
            response_text = agent.run(user_text)

            # Post macOS notification with result so user sees it even when looking at Blinkit/Browser
            if response_text:
                first_line = response_text.strip().split("\n")[0][:120].strip()
                post_system_notification("Blacky", first_line)

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Voice session closed.[/dim]")
            break


def cli_entrypoint() -> None:
    """Main CLI entrypoint parser."""
    parser = argparse.ArgumentParser(
        prog="blacky",
        description="BlackyAgent: Autonomous Siri-like AI Assistant for macOS and Mobile with Full Control",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        help="Direct one-shot command for Blacky to execute immediately (e.g. 'make a folder named code and write binary search')",
    )
    parser.add_argument(
        "-v",
        "--voice",
        action="store_true",
        help="Start in Push-to-Talk Siri Voice mode",
    )
    parser.add_argument(
        "-m",
        "--mobile",
        action="store_true",
        help="Start Mobile Remote web server to control Blacky from your phone",
    )
    parser.add_argument(
        "-s",
        "--speak",
        action="store_true",
        help="Enable speech output (TTS) after tasks (disabled by default)",
    )
    parser.add_argument(
        "--no-voice",
        action="store_true",
        help="Disable speech output (TTS)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.MOBILE_SERVER_PORT,
        help="Port for mobile remote web server (default: 8000)",
    )

    args = parser.parse_args()

    # Check configuration and the local model server before doing anything else.
    if not config.validate():
        print_error("OLLAMA_MODEL is not configured! Set it in your .env file (e.g. OLLAMA_MODEL=qwen3:4b).")
        sys.exit(1)

    provider = OllamaProvider()
    connected, detail = provider.check_connection()
    if not connected:
        from blacky.core.ollama_client import ensure_server_running
        print_info("Ollama is not running. Starting local Ollama server...")
        if ensure_server_running(provider.base_url):
            provider.refresh()
            connected, detail = provider.check_connection()

    if not connected:
        print_error(detail)
        print_error("Install/start Ollama, then pull a model: ollama pull " + config.OLLAMA_MODEL)
        sys.exit(1)
    if not provider.has_model(config.OLLAMA_MODEL):
        print_error(f"Model '{config.OLLAMA_MODEL}' is not installed. Run: ollama pull {config.OLLAMA_MODEL}")
        sys.exit(1)

    # 1. Mobile Remote Mode
    if args.mobile or (args.command and args.command.lower() in ("mobile", "server", "web")):
        from blacky.web.server import run_server
        show_banner()
        run_server(port=args.port)
        return

    # Determine if agent speaks replies:
    # Enabled in Voice Mode (--voice) or when explicitly requested (--speak).
    # Voice feedback speaks concise operational actions (e.g. "Calling Satyam") without reciting long message bodies.
    should_speak = False
    if args.no_voice:
        should_speak = False
    elif args.speak or args.voice:
        should_speak = True
        voice_engine.enabled = True
    else:
        should_speak = config.BLACKY_VOICE_ENABLED

    # Create agent (local Ollama model; no API key required)
    agent = BlackyAgent(speak_replies=should_speak, provider=provider)

    # 2. One-shot direct command execution
    if args.command:
        print_user_prompt(args.command)
        agent.run(args.command)
        return

    # 3. Push-to-Talk Voice Mode
    if args.voice:
        run_voice_loop(agent)
        return

    # 4. Interactive Terminal REPL Mode (Default)
    run_repl(agent)


if __name__ == "__main__":
    cli_entrypoint()
