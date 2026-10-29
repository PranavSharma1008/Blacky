#!/usr/bin/env bash
# BlackyAgent Terminal Controller & Launcher
# Allows running BlackyAgent commands directly or spawning them into separate macOS Terminal windows.

set -e

# Resolve project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Ensure Python virtual/system environment finds blacky
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH"

# Function to spawn a command into a new terminal (VS Code tab if in VS Code, else native Terminal.app)
spawn_in_new_terminal() {
    local title="$1"
    local cmd="$2"

    local ide_app=""
    local ide_proc=""

    if [ "$TERM_PROGRAM" = "vscode" ] || pgrep -x "Code" >/dev/null 2>&1; then
        ide_app="Visual Studio Code"
        ide_proc="Code"
    elif pgrep -x "Cursor" >/dev/null 2>&1; then
        ide_app="Cursor"
        ide_proc="Cursor"
    fi

    if [ -n "$ide_app" ]; then
        osascript - "$PROJECT_DIR" "$cmd" "$ide_app" "$ide_proc" <<'EOF' >/dev/null 2>&1
on run argv
    set projectDir to item 1 of argv
    set commandToRun to item 2 of argv
    set appName to item 3 of argv
    set procName to item 4 of argv
    tell application appName to activate
    tell application "System Events"
        tell process procName
            try
                click menu item "New Terminal" of menu "Terminal" of menu bar 1
                delay 0.4
                keystroke "cd " & quoted form of projectDir & " && export PATH=\"/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH\" && " & commandToRun & return
            end try
        end tell
    end tell
end run
EOF
        echo "🚀 Opened '$title' in a new $ide_app terminal tab!"
        return 0
    fi

    # Fallback to macOS Terminal.app if not in an IDE
    osascript - "$PROJECT_DIR" "$cmd" "$title" <<'EOF' >/dev/null 2>&1
on run argv
    set projectDir to item 1 of argv
    set commandToRun to item 2 of argv
    tell application "Terminal"
        activate
        do script "cd " & quoted form of projectDir & " && export PATH=\"/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH\" && " & commandToRun
    end tell
end run
EOF
    echo "🚀 Launched '$title' in a new Terminal window!"
}

# If arguments were passed, check for special flags or execute directly
if [ "$#" -gt 0 ]; then
    case "$1" in
        -v|--voice)
            exec python3 -m blacky.main --voice
            ;;
        -m|--mobile)
            exec python3 -m blacky.main --mobile
            ;;
        --new-voice)
            spawn_in_new_terminal "BlackyAgent - Voice Mode" "python3 -m blacky.main --voice"
            exit 0
            ;;
        --new-mobile)
            spawn_in_new_terminal "BlackyAgent - Mobile Server" "python3 -m blacky.main --mobile"
            exit 0
            ;;
        --new-chat)
            spawn_in_new_terminal "BlackyAgent - Chat REPL" "python3 -m blacky.main"
            exit 0
            ;;
        --new-all)
            spawn_in_new_terminal "BlackyAgent - Mobile Server" "python3 -m blacky.main --mobile"
            sleep 1
            spawn_in_new_terminal "BlackyAgent - Voice Mode" "python3 -m blacky.main --voice"
            exit 0
            ;;
        *)
            # Run command directly in current terminal
            exec python3 -m blacky.main "$@"
            ;;
    esac
fi

# If no arguments provided, show the interactive Launcher Menu
clear 2>/dev/null || true
echo "=========================================================="
echo "           🐾 BLACKY AGENT TERMINAL LAUNCHER 🐾           "
echo "=========================================================="
if [ "$TERM_PROGRAM" = "vscode" ] || pgrep -x "Code" >/dev/null 2>&1; then
    echo "  📍 Environment: Visual Studio Code Integrated Terminal"
fi
echo ""
echo "Choose how you want to run BlackyAgent:"
echo ""
echo "  [1] 🎙️  Open Voice Mode in a NEW Terminal Tab"
echo "  [2] 📱  Open Mobile Server in a NEW Terminal Tab"
echo "  [3] 💬  Open Chat REPL in a NEW Terminal Tab"
echo "  [4] 🚀  Open BOTH (Mobile Server + Voice Mode in 2 Tabs)"
echo "  [5] ⚡  Run Interactive Chat right here in this Terminal"
echo "  [6] 🎙️  Run Voice Mode right here in this Terminal"
echo "  [0] ✖   Exit"
echo ""
echo "=========================================================="
read -p "Select an option [1-6]: " choice

case "$choice" in
    1)
        spawn_in_new_terminal "BlackyAgent - Voice Mode" "python3 -m blacky.main --voice"
        ;;
    2)
        spawn_in_new_terminal "BlackyAgent - Mobile Server" "python3 -m blacky.main --mobile"
        ;;
    3)
        spawn_in_new_terminal "BlackyAgent - Chat REPL" "python3 -m blacky.main"
        ;;
    4)
        spawn_in_new_terminal "BlackyAgent - Mobile Server" "python3 -m blacky.main --mobile"
        sleep 1
        spawn_in_new_terminal "BlackyAgent - Voice Mode" "python3 -m blacky.main --voice"
        ;;
    5)
        exec python3 -m blacky.main
        ;;
    6)
        exec python3 -m blacky.main --voice
        ;;
    0|q|exit)
        echo "Goodbye!"
        exit 0
        ;;
    *)
        echo "Invalid selection. Running Interactive Chat in this terminal..."
        exec python3 -m blacky.main
        ;;
esac
