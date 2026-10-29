"""
Main CLI entry point for BlackyAgent.
Supports Interactive REPL, Push-to-Talk Voice mode, Mobile Remote mode, and one-shot execution.
"""

import sys
import argparse
from blacky.config import config
from blacky.core.agent import BlackyAgent
from blacky.voice import voice_listener, voice_engine
from blacky.ui.console import (
    console,
    show_banner,
    print_user_prompt,
    print_info,
    print_error,
)


def run_repl(agent: BlackyAgent) -> None:
    """Run interactive terminal chat REPL."""
    show_banner()
    console.print("[dim]Type your command, or type 'exit' or 'quit' to close.[/dim]\n")

    while True:
        try:
            prompt = console.input("[bold magenta]Blacky 🐾 > [/bold magenta]").strip()
            if not prompt:
                continue
            if prompt.lower() in ("exit", "quit", "q", "bye"):
                console.print("\n[bold cyan]Goodbye! Have a great day![/bold cyan]")
                if agent.speak_replies:
                    voice_engine.speak("Goodbye! Have a great day!", wait=True)
                break

            agent.run(prompt)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session closed.[/dim]")
            break


def run_voice_loop(agent: BlackyAgent) -> None:
    """Run Push-to-Talk voice loop."""
    show_banner()
    console.print("[bold cyan]🎙️ Push-to-Talk Siri Voice Mode Active[/bold cyan]")
    console.print("[dim]HOLD the [Fn] key to talk (or press Enter / type command). Say 'exit' to quit.[/dim]\n")

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

            print_user_prompt(user_text)
            agent.run(user_text)

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

    # Check configuration
    if not config.validate():
        print_error("GEMINI_API_KEY is missing! Please configure your API key in .env")
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

    # Create agent
    agent = BlackyAgent(speak_replies=should_speak)

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
