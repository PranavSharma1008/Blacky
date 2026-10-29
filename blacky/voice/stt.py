"""
Speech-to-Text (STT) and Push-to-Talk input handler for BlackyAgent.
Supports holding the Mac [Fn] (Globe) key to speak (releases to stop),
or pressing [ENTER] / typing directly in terminal.
Uses macOS native ffmpeg recording + Google Speech Recognition.
"""

import os
import sys
import time
import select
import shutil
import ctypes
import subprocess
import tempfile
from blacky.ui.console import console

# Load CoreGraphics and Carbon for macOS hardware key state detection
try:
    _cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    _cg.CGEventSourceFlagsState.restype = ctypes.c_uint64
    _cg.CGEventSourceFlagsState.argtypes = [ctypes.c_int32]
    _cg.CGEventSourceKeyState.restype = ctypes.c_bool
    _cg.CGEventSourceKeyState.argtypes = [ctypes.c_int32, ctypes.c_uint16]
except Exception:
    _cg = None

try:
    _carbon = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Carbon.framework/Carbon")
    class _KeyMap(ctypes.Structure):
        _fields_ = [("map", ctypes.c_uint32 * 4)]
except Exception:
    _carbon = None


class VoiceListener:
    """Handles push-to-talk microphone recording and audio transcription."""

    def __init__(self):
        self._ffmpeg_bin = (
            shutil.which("ffmpeg")
            or "/opt/homebrew/bin/ffmpeg"
            or "/usr/local/bin/ffmpeg"
        )
        self._recognizer = None

    def _get_recognizer(self):
        if self._recognizer is None:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
        return self._recognizer

    def _is_fn_pressed(self) -> bool:
        """Check if Mac [Fn] (Globe) key is currently held down."""
        if _cg is not None:
            try:
                # 0x00800000 = kCGEventFlagMaskSecondaryFn
                # Check both HIDSystemState (1) and CombinedSessionState (0)
                if (_cg.CGEventSourceFlagsState(1) & 0x00800000) or (_cg.CGEventSourceFlagsState(0) & 0x00800000):
                    return True
                # Virtual keycode 63 (0x3F) is Fn key on Apple keyboards
                if _cg.CGEventSourceKeyState(1, 63) or _cg.CGEventSourceKeyState(0, 63):
                    return True
            except Exception:
                pass

        if _carbon is not None:
            try:
                km = _KeyMap()
                _carbon.GetKeys(ctypes.byref(km))
                if (km.map[1] >> 31) & 1:
                    return True
            except Exception:
                pass

        return False

    def listen_push_to_talk(self) -> str:
        """
        Push-to-Talk mode:
        1. Hold [Fn] key to talk: records while held, stops and transcribes when released.
        2. Or press [ENTER] to record, or type command directly.
        """
        import speech_recognition as sr

        console.print("\n[bold cyan]🎙️  Push-to-Talk Siri Voice Mode[/bold cyan]")
        console.print("[bold green]👉 HOLD the [Fn] key to speak[/bold green] [dim](release when finished speaking)[/dim]")
        console.print("[dim]Or press [ENTER] to record, or type your command directly:[/dim]")

        if not self._ffmpeg_bin or not os.path.exists(self._ffmpeg_bin):
            console.print("[dim yellow]ffmpeg audio recorder not found. Please type command:[/dim yellow]")
            return input("💬 > ").strip()

        sys.stdout.write("💬 > ")
        sys.stdout.flush()

        recorded_via_fn = False

        # If not running in an interactive terminal, fallback to standard input
        if not sys.stdin.isatty():
            return input().strip()

        # Monitor loop: watch for [Fn] key press OR terminal keyboard input
        while True:
            if self._is_fn_pressed():
                recorded_via_fn = True
                break

            r, _, _ = select.select([sys.stdin], [], [], 0.04)
            if r:
                line = sys.stdin.readline()
                if not line:
                    return "exit"
                typed_text = line.strip()
                if typed_text:
                    return typed_text
                # User pressed Enter with no text -> manual Enter recording
                break

        temp_wav = os.path.join(tempfile.gettempdir(), "blacky_mic_input.wav")
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass

        try:
            # Start recording from macOS default microphone (:0)
            cmd = [
                self._ffmpeg_bin,
                "-y",
                "-f", "avfoundation",
                "-i", ":0",
                "-ac", "1",
                "-ar", "16000",
                temp_wav,
            ]
            record_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            if recorded_via_fn:
                console.print("\n[bold red]🔴 [Fn] Held — Recording... (Speak now, release [Fn] to finish)[/bold red]")
                start_time = time.time()
                # Record while [Fn] key is held down
                while self._is_fn_pressed():
                    time.sleep(0.04)
                duration = time.time() - start_time
                console.print("[bold yellow]⏹️  [Fn] Released — Processing speech...[/bold yellow]")

                if duration < 0.35:
                    record_proc.terminate()
                    try:
                        record_proc.wait(timeout=1)
                    except Exception:
                        record_proc.kill()
                    console.print("[dim yellow]Key hold was too brief. Please HOLD [Fn] while speaking.[/dim yellow]")
                    return ""
            else:
                console.print("[bold red]🔴 Recording from Microphone... (Speak your command now)[/bold red]")
                input("   [dim]Press [ENTER] when you are finished speaking...[/dim] > ")

            # Stop recording
            record_proc.terminate()
            try:
                record_proc.wait(timeout=2)
            except Exception:
                record_proc.kill()

            if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 2000:
                console.print("[dim yellow]Audio was too short or empty. Please try again.[/dim yellow]")
                return ""

            console.print("[bold yellow]⏳ Transcribing speech...[/bold yellow]")
            recognizer = self._get_recognizer()
            with sr.AudioFile(temp_wav) as source:
                audio_data = recognizer.record(source)

            transcription = recognizer.recognize_google(audio_data)
            console.print(f"[bold green]🗣️  Heard:[/bold green] [italic]\"{transcription}\"[/italic]")
            return transcription.strip()

        except sr.UnknownValueError:
            console.print("[dim yellow]Could not understand speech. Please try speaking clearly or type command.[/dim yellow]")
            return ""
        except sr.RequestError as e:
            console.print(f"[dim yellow]Speech service unreachable ({e}). Please type command:[/dim yellow]")
            return input("You: ").strip()
        except Exception as e:
            console.print(f"[dim yellow]Microphone recording notice ({e}). Falling back to typing:[/dim yellow]")
            return input("You: ").strip()
        finally:
            if os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except Exception:
                    pass


voice_listener = VoiceListener()
