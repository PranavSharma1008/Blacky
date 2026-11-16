#!/usr/bin/env bash
# BlackyAgent Terminal Controller & Launcher
# Allows running BlackyAgent commands directly or spawning them into separate terminal tabs/windows
# in whichever IDE or terminal emulator you are currently running (VS Code, Cursor, Windsurf, iTerm2, Terminal, etc.).

set -e

# Resolve project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Ensure Python virtual/system environment finds blacky
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH"

# Detect the exact terminal environment where the command is being executed
detect_environment() {
    # 1. Walk up the ancestor process tree of the current shell session
    local pid=$$
    local ancestors=""
    while [ -n "$pid" ] && [ "$pid" -gt 1 ]; do
        local line
        line=$(ps -o ppid=,comm= -p "$pid" 2>/dev/null) || break
        local ppid
        ppid=$(echo "$line" | awk '{print $1}')
        local comm
        comm=$(echo "$line" | awk '{$1=""; print $0}')
        ancestors="$ancestors $comm"
        [ -z "$ppid" ] && break
        pid=$ppid
    done

    # Check ancestors first (most reliable: identifies the host app of the current terminal process)
    if [[ "$ancestors" =~ [Cc]ursor ]]; then
        echo "cursor"
        return
    elif [[ "$ancestors" =~ [Ww]indsurf ]]; then
        echo "windsurf"
        return
    elif [[ "$ancestors" =~ Visual\ Studio\ Code ]] || [[ "$ancestors" =~ /Code\.app/ ]] || [[ "$ancestors" =~ Code\ Helper ]] || [[ "$ancestors" =~ /MacOS/Code ]]; then
        echo "vscode"
        return
    elif [[ "$ancestors" =~ [Pp]y[Cc]harm ]] || [[ "$ancestors" =~ [Ii]ntelli[Jj] ]] || [[ "$ancestors" =~ [Ii]dea ]] || [[ "$ancestors" =~ [Ww]eb[Ss]torm ]]; then
        echo "jetbrains"
        return
    elif [[ "$ancestors" =~ [Ii][Tt]erm ]]; then
        echo "iterm"
        return
    elif [[ "$ancestors" =~ [Ww]arp ]]; then
        echo "warp"
        return
    elif [[ "$ancestors" =~ [Gg]hostty ]]; then
        echo "ghostty"
        return
    elif [[ "$ancestors" =~ [Tt]erminal\.app ]] || [[ "$ancestors" =~ /Contents/MacOS/Terminal ]]; then
        echo "terminal"
        return
    fi

    # 2. Inspect session environment variables as fallback
    local env_combined="${GIT_ASKPASS} ${VSCODE_GIT_ASKPASS_NODE} ${VSCODE_GIT_ASKPASS_MAIN} ${CURSOR_APPLICATION_SUPPORT_DIR} ${CURSOR_VERSION}"
    if [[ "$env_combined" =~ [Cc]ursor ]]; then
        echo "cursor"
        return
    elif [[ "$env_combined" =~ [Ww]indsurf ]]; then
        echo "windsurf"
        return
    elif [[ "$env_combined" =~ Visual\ Studio\ Code ]] || [[ "$env_combined" =~ Code\.app ]] || [ "$TERM_PROGRAM" = "vscode" ]; then
        echo "vscode"
        return
    elif [ "$TERM_PROGRAM" = "iTerm.app" ]; then
        echo "iterm"
        return
    elif [ "$TERM_PROGRAM" = "WarpTerminal" ]; then
        echo "warp"
        return
    elif [ "$TERM_PROGRAM" = "ghostty" ]; then
        echo "ghostty"
        return
    elif [[ "$TERMINAL_EMULATOR" =~ JetBrains ]]; then
        echo "jetbrains"
        return
    elif [ "$TERM_PROGRAM" = "Apple_Terminal" ]; then
        echo "terminal"
        return
    fi

    # Default fallback
    echo "terminal"
}

get_environment_label() {
    local env_type="$1"
    case "$env_type" in
        vscode)    echo "Visual Studio Code Integrated Terminal" ;;
        cursor)    echo "Cursor Integrated Terminal" ;;
        windsurf)  echo "Windsurf Integrated Terminal" ;;
        jetbrains) echo "JetBrains IDE Integrated Terminal" ;;
        iterm)     echo "iTerm2 Terminal" ;;
        warp)      echo "Warp Terminal" ;;
        ghostty)   echo "Ghostty Terminal" ;;
        *)         echo "macOS Terminal (Terminal.app)" ;;
    esac
}

# Function to spawn a command into a new terminal tab/window in the currently used environment
spawn_in_new_terminal() {
    local title="$1"
    local cmd="$2"
    local env_type
    env_type="$(detect_environment)"

    case "$env_type" in
        vscode)
            osascript - "$PROJECT_DIR" "$cmd" "Visual Studio Code" "Code" <<'EOF' >/dev/null 2>&1
on run argv
    set projectDir to item 1 of argv
    set commandToRun to item 2 of argv
    set appName to item 3 of argv
    set procName to item 4 of argv
    tell application appName to activate
    delay 0.3
    tell application "System Events"
        tell process procName
            try
                click menu item "New Terminal" of menu "Terminal" of menu bar 1
            on error
                keystroke "`" using {control down, shift down}
            end try
            delay 0.5
            keystroke "cd " & quoted form of projectDir & " && export PATH=\"/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH\" && " & commandToRun & return
        end tell
    end tell
end run
EOF
            echo "🚀 Opened '$title' in a new Visual Studio Code terminal tab!"
            ;;

        cursor)
            osascript - "$PROJECT_DIR" "$cmd" "Cursor" "Cursor" <<'EOF' >/dev/null 2>&1
on run argv
    set projectDir to item 1 of argv
    set commandToRun to item 2 of argv
    set appName to item 3 of argv
    set procName to item 4 of argv
    tell application appName to activate
    delay 0.3
    tell application "System Events"
        tell process procName
            try
                click menu item "New Terminal" of menu "Terminal" of menu bar 1
            on error
                keystroke "`" using {control down, shift down}
            end try
            delay 0.5
            keystroke "cd " & quoted form of projectDir & " && export PATH=\"/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH\" && " & commandToRun & return
        end tell
    end tell
end run
EOF
            echo "🚀 Opened '$title' in a new Cursor terminal tab!"
            ;;

        windsurf)
            osascript - "$PROJECT_DIR" "$cmd" "Windsurf" "Windsurf" <<'EOF' >/dev/null 2>&1
on run argv
    set projectDir to item 1 of argv
    set commandToRun to item 2 of argv
    set appName to item 3 of argv
    set procName to item 4 of argv
    tell application appName to activate
    delay 0.3
    tell application "System Events"
        tell process procName
            try
                click menu item "New Terminal" of menu "Terminal" of menu bar 1
            on error
                keystroke "`" using {control down, shift down}
            end try
            delay 0.5
            keystroke "cd " & quoted form of projectDir & " && export PATH=\"/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH\" && " & commandToRun & return
        end tell
    end tell
end run
EOF
            echo "🚀 Opened '$title' in a new Windsurf terminal tab!"
            ;;

        iterm)
            osascript - "$PROJECT_DIR" "$cmd" <<'EOF' >/dev/null 2>&1
on run argv
    set projectDir to item 1 of argv
    set commandToRun to item 2 of argv
    tell application "iTerm"
        activate
        if (count of windows) = 0 then
            create window with default profile
            tell current session of current window
                write text "cd " & quoted form of projectDir & " && export PATH=\"/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH\" && " & commandToRun
            end tell
        else
            tell current window
                create tab with default profile
                tell current session
                    write text "cd " & quoted form of projectDir & " && export PATH=\"/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH\" && " & commandToRun
                end tell
            end tell
        end if
    end tell
end run
EOF
            echo "🚀 Opened '$title' in a new iTerm tab!"
            ;;

        warp)
            osascript - "$PROJECT_DIR" "$cmd" <<'EOF' >/dev/null 2>&1
on run argv
    set projectDir to item 1 of argv
    set commandToRun to item 2 of argv
    tell application "Warp" to activate
    delay 0.3
    tell application "System Events"
        tell process "Warp"
            keystroke "t" using command down
            delay 0.5
            keystroke "cd " & quoted form of projectDir & " && export PATH=\"/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH\" && " & commandToRun & return
        end tell
    end tell
end run
EOF
            echo "🚀 Opened '$title' in a new Warp tab!"
            ;;

        ghostty)
            osascript - "$PROJECT_DIR" "$cmd" <<'EOF' >/dev/null 2>&1
on run argv
    set projectDir to item 1 of argv
    set commandToRun to item 2 of argv
    tell application "Ghostty" to activate
    delay 0.3
    tell application "System Events"
        tell process "Ghostty"
            keystroke "t" using command down
            delay 0.5
            keystroke "cd " & quoted form of projectDir & " && export PATH=\"/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH\" && " & commandToRun & return
        end tell
    end tell
end run
EOF
            echo "🚀 Opened '$title' in a new Ghostty tab!"
            ;;

        *)
            # Native Terminal.app fallback (for Apple Terminal, JetBrains, or any other environment)
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
            ;;
    esac
}

# Ensure local Ollama server is running before executing any agent operation
ensure_ollama_running() {
    # Check if Ollama HTTP API is responding
    if curl -s -f -m 1 http://localhost:11434/api/tags >/dev/null 2>&1; then
        return 0
    fi

    echo "⚙️  Ollama is not running. Starting local Ollama server..."
    if [ -d "/Applications/Ollama.app" ]; then
        open -ga /Applications/Ollama.app
    elif command -v ollama >/dev/null 2>&1; then
        nohup ollama serve >/dev/null 2>&1 &
    fi

    # Wait up to 10 seconds for Ollama to become responsive
    local retries=20
    while [ $retries -gt 0 ]; do
        if curl -s -f -m 1 http://localhost:11434/api/tags >/dev/null 2>&1; then
            echo "✓ Ollama server is online and ready!"
            return 0
        fi
        sleep 0.5
        retries=$((retries - 1))
    done

    # Fallback to direct 'nohup ollama serve' if app launch didn't start the API in time
    if command -v ollama >/dev/null 2>&1; then
        nohup ollama serve >/dev/null 2>&1 &
        sleep 2
        if curl -s -f -m 1 http://localhost:11434/api/tags >/dev/null 2>&1; then
            echo "✓ Ollama server is online and ready!"
            return 0
        fi
    fi

    echo "⚠️ Warning: Ollama could not be started automatically. Please run 'ollama serve'."
}

# Automatically ensure Ollama is up and running
ensure_ollama_running

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
CURRENT_ENV="$(detect_environment)"
ENV_LABEL="$(get_environment_label "$CURRENT_ENV")"

echo "=========================================================="
echo "           🐾 BLACKY AGENT TERMINAL LAUNCHER 🐾           "
echo "=========================================================="
echo "  📍 Environment: $ENV_LABEL"
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
