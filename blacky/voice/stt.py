"""
Speech-to-Text (STT) and Push-to-Talk input handler for BlackyAgent.
Supports pressing [ENTER] to speak with live volume meter and auto-silence stop,
holding the Mac [Fn] key, or typing commands directly into the terminal.
Uses macOS native ffmpeg microphone stream + Google Speech Recognition.
"""

import os
import sys
import io
import re
import time
import math
import wave
import select
import shutil
import struct
import ctypes
import subprocess
from blacky.ui.console import console

# Load CoreGraphics and Carbon for optional macOS hardware key state detection
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


def normalize_speech_text(text: str) -> str:
    """Normalize common speech recognition acoustic/phonetic misrecognitions for Indian English / accents."""
    if not text:
        return text
    t = text
    t = re.sub(r'\b(whats app|what\'s app|watssapp|whatsap|watsap)\b', 'WhatsApp', t, flags=re.IGNORECASE)
    # Wake word phonetics (Indian English acoustic misrecognitions for "Hey Blacky")
    t = re.sub(r'\b(hitler ki|hitler key|hitler kee|hail blacky|hey blecky|hey blackie)\b', 'Hey Blacky', t, flags=re.IGNORECASE)
    # Indian names & contact phonetics
    t = re.sub(r'\b(rishabh|rishav)\b', 'Rishab', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(ajauli|ajoli|azoli|ajawli)\b', 'Ajouli', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(avinash|avdhesh|awdesh|avneesh|abnesh|avnsish|avnis)\b', 'Avnish', t, flags=re.IGNORECASE)
    # Blinkit phonetics (e.g. blanket, blickit)
    t = re.sub(r'\b(blanket|blickit|blenkit|blankit|blinket)\b', 'Blinkit', t, flags=re.IGNORECASE)
    # Diet Coke phonetics (e.g. diet book, diet cake)
    t = re.sub(r'\b(diet book|diet cake|diet cook|dark coke|died coke|died cake)\b', 'diet coke', t, flags=re.IGNORECASE)
    # Snacks, Kurkure & Bingo Mad Angles phonetics (e.g. "a charlie flavour", "charlie", "one crore packet")
    t = re.sub(r'\b(one crore|one crDre|one cror|karkare|kulkure)\s*(packet)?\b', 'Kurkure packet', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(a charlie|charlie)\s*(flavour|flavor)?\b', 'Achari Masti', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(mad angle|mad angles)\b', 'Mad Angles', t, flags=re.IGNORECASE)
    # Checkout phonetics (e.g. cheque book checkout)
    t = re.sub(r'\b(cheque book checkout|cheque book|check book)\b', 'checkout', t, flags=re.IGNORECASE)
    # Amazon phonetics
    t = re.sub(r'\b(amazom|amazone|amzon)\b', 'Amazon', t, flags=re.IGNORECASE)
    # App & Tool phonetics
    t = re.sub(r'\b(wisporflow|whisper flow|whisperflow)\b', 'WhisperFlow', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(photo both|photo boot|photo shoot|photobooth)\b', 'Photo Booth', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(full scrren|full screen)\b', 'full screen', t, flags=re.IGNORECASE)
    # Project & Agent Name Phonetics
    t = re.sub(r'\b(balcky|blackie|blacki|blakey|blecky|blackee)\b', 'Blacky', t, flags=re.IGNORECASE)
    # Repo / GitHub phonetics
    t = re.sub(r'\b(\d+)repo\b', r'\1 repo', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(git hub|git-hub)\b', 'GitHub', t, flags=re.IGNORECASE)
    return t


import threading


def _run_detached_bg_command(cmd: list[str]) -> None:
    """Run a quick background command in a daemon thread without blocking or resource warnings."""
    def _worker():
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.wait()
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()


def play_feedback_sound(sound_name: str) -> None:
    """Play macOS system audio chime asynchronously (e.g. 'Ping', 'Tink')."""
    sound_path = f"/System/Library/Sounds/{sound_name}.aiff"
    if os.path.exists(sound_path):
        _run_detached_bg_command(["afplay", "-v", "0.6", sound_path])


def post_system_notification(title: str, message: str) -> None:
    """Post an instant system notification banner on macOS."""
    clean_title = title.replace('"', '\\"')
    clean_msg = message.replace('"', '\\"')
    script = f'display notification "{clean_msg}" with title "{clean_title}"'
    _run_detached_bg_command(["osascript", "-e", script])


class VoiceListener:
    """Handles push-to-talk microphone recording and audio transcription."""

    def __init__(self):
        self._ffmpeg_bin = (
            shutil.which("ffmpeg")
            or "/opt/homebrew/bin/ffmpeg"
            or "/usr/local/bin/ffmpeg"
        )
        self._recognizer = None
        self._audio_device = ":0"

    def _get_recognizer(self):
        if self._recognizer is None:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
        return self._recognizer

    def _is_global_trigger_pressed(self) -> bool:
        """
        Check if any global push-to-talk trigger key is pressed anywhere on macOS.
        Works globally regardless of which application is active (Blinkit, Chrome, Safari, etc.).
        Supported keys:
        - [Fn] / Globe key (Physical Fn on Mac keyboards)
        - [Right Option] key (Bottom-right modifier next to space/arrows)
        - [Control + Space] or [Option + Space] (Universal hotkeys)
        """
        if _cg is not None:
            try:
                f1 = _cg.CGEventSourceFlagsState(1)
                f0 = _cg.CGEventSourceFlagsState(0)

                # 1. Fn / Globe key (SecondaryFn modifier 0x00800000 or keycode 63)
                if (f1 & 0x00800000) or (f0 & 0x00800000):
                    return True
                if _cg.CGEventSourceKeyState(1, 63) or _cg.CGEventSourceKeyState(0, 63):
                    return True

                # 2. Right Option key (keycode 61)
                if _cg.CGEventSourceKeyState(1, 61) or _cg.CGEventSourceKeyState(0, 61):
                    return True

                # 3. Control + Space (0x40000 + keycode 49) or Option + Space (0x80000 + keycode 49)
                if (f1 & 0x00040000 or f0 & 0x00040000) and (_cg.CGEventSourceKeyState(1, 49) or _cg.CGEventSourceKeyState(0, 49)):
                    return True
                if (f1 & 0x00080000 or f0 & 0x00080000) and (_cg.CGEventSourceKeyState(1, 49) or _cg.CGEventSourceKeyState(0, 49)):
                    return True
            except Exception:
                pass

        if _carbon is not None:
            try:
                km = _KeyMap()
                _carbon.GetKeys(ctypes.byref(km))
                # Bit 31: Fn key (keycode 63)
                if (km.map[1] >> 31) & 1:
                    return True
                # Bit 29: Right Option key (keycode 61)
                if (km.map[1] >> 29) & 1:
                    return True
            except Exception:
                pass

        return False

    def _is_fn_pressed(self) -> bool:
        """Alias for backward compatibility."""
        return self._is_global_trigger_pressed()

    def _record_streaming_audio(self, fn_mode: bool = False) -> bytes:
        """
        Record audio from Mac microphone via ffmpeg PCM stream.
        Shows live volume meter and auto-detects when the user finishes speaking.
        Works seamlessly from any app (e.g. Blinkit in browser) with audio chimes and native notifications.
        """
        cmd = [
            self._ffmpeg_bin,
            "-f", "avfoundation",
            "-i", self._audio_device,
            "-f", "s16le",
            "-ac", "1",
            "-ar", "16000",
            "pipe:1",
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        # Audio chime & notification so user knows Blacky is listening even when viewing Blinkit
        play_feedback_sound("Ping")
        post_system_notification("🎙️ Blacky", "Listening... Speak your command")

        frames = []
        speech_detected = False
        silence_start = None
        was_held = False
        initial_key_released = False
        start_time = time.time()
        max_duration = 20.0  # Max 20s recording
        silence_cutoff_seconds = 0.65  # Fast, snappy speech endpointing (stops 0.45s sooner when done speaking)

        console.print("[bold red]🔴 Recording from Microphone... (Speak now)[/bold red]")
        console.print("[dim]Tap or hold [Fn] / [Right Option] to speak. Auto-detects completion.[/dim]")

        # Meter visual bars
        meter_chars = [" ", " ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

        try:
            while True:
                now = time.time()
                elapsed = now - start_time
                if elapsed > max_duration:
                    break

                is_trigger_down = self._is_global_trigger_pressed()

                # Key state tracking for global push-to-talk (Walkie-talkie & Tap-to-Talk)
                if fn_mode:
                    if is_trigger_down:
                        was_held = True
                    elif was_held and not is_trigger_down:
                        # Instant stop when user releases the held hotkey!
                        if speech_detected or len(frames) >= 3:
                            break
                    if not is_trigger_down:
                        initial_key_released = True
                    # Tap-to-talk: tapping key a second time stops recording immediately
                    if initial_key_released and elapsed > 0.35 and is_trigger_down:
                        break
                else:
                    # In terminal enter mode, check if user pressed Enter in terminal to stop early
                    if sys.stdin.isatty():
                        r, _, _ = select.select([sys.stdin], [], [], 0.0)
                        if r:
                            sys.stdin.readline()
                            break

                # Read 100ms chunk (1600 samples * 2 bytes = 3200 bytes)
                raw = proc.stdout.read(3200)
                if not raw:
                    break
                frames.append(raw)

                # Compute RMS volume level
                count = len(raw) // 2
                shorts = struct.unpack(f"{count}h", raw)
                sum_sq = sum(s * s for s in shorts)
                rms = math.sqrt(sum_sq / count) if count > 0 else 0

                # Render animated level meter in console
                level_idx = min(len(meter_chars) - 1, int(rms / 350))
                bar = meter_chars[level_idx] * 4
                sys.stdout.write(f"\r   🎙️  [bold green][{bar:<4}][/bold green] [dim]Listening... (RMS: {int(rms)})[/dim]")
                sys.stdout.flush()

                # Speech activity detection (VAD)
                if rms > 450:
                    speech_detected = True
                    silence_start = None
                elif speech_detected:
                    # If user is actively holding the push-to-talk key (Walkie-talkie mode), NEVER cut them off on silence!
                    if fn_mode and is_trigger_down:
                        silence_start = None
                    else:
                        if silence_start is None:
                            silence_start = now
                        elif now - silence_start >= silence_cutoff_seconds:
                            # User stopped speaking for silence_cutoff_seconds
                            break

                # Graceful timeout if user tapped trigger and never said anything
                if not speech_detected and elapsed > 5.0:
                    break

                time.sleep(0.01)

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except Exception:
                proc.kill()
            sys.stdout.write("\r" + " " * 60 + "\r")
            sys.stdout.flush()

            # Play completion chime so user knows recording finished
            play_feedback_sound("Tink")

        return b"".join(frames)

    def listen_push_to_talk(self) -> str:
        """
        Global Push-to-Talk / Voice Mode:
        1. Tap or Hold [Fn] or [Right Option] key anywhere (even while in Blinkit / Chrome / Safari).
        2. Or press [ENTER] to speak in the terminal.
        3. Or type your command directly in the terminal prompt.
        """
        import speech_recognition as sr

        console.print("\n[bold cyan]🎙️  Global Siri Voice Mode Active[/bold cyan]")
        console.print("[bold green]👉 Tap or Hold [Fn] / [Right Option] anywhere[/bold green] [dim](works in Blinkit, Chrome, Safari, or press [ENTER] here):[/dim]")

        if not self._ffmpeg_bin or not os.path.exists(self._ffmpeg_bin):
            console.print("[dim yellow]ffmpeg audio recorder not found. Please type command:[/dim yellow]")
            return input("💬 > ").strip()

        sys.stdout.write("💬 > ")
        sys.stdout.flush()

        recorded_via_fn = False

        if not sys.stdin.isatty():
            return input().strip()

        # Monitor loop: watch for global trigger key press OR terminal keyboard input
        while True:
            if self._is_global_trigger_pressed():
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
                # User pressed Enter with no text -> start recording!
                break

        try:
            pcm_data = self._record_streaming_audio(fn_mode=recorded_via_fn)
            if len(pcm_data) < 4000:
                console.print("[dim yellow]Audio was too short. Please try speaking again.[/dim yellow]")
                return ""

            console.print("[bold yellow]⏳ Transcribing speech...[/bold yellow]")

            # Convert raw PCM into WAV format in-memory
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(pcm_data)

            audio_bytes = wav_buffer.getvalue()
            recognizer = self._get_recognizer()
            audio_source = sr.AudioData(audio_bytes, 16000, 2)

            # Fast Indian English recognition with fallback to en-US
            raw_transcription = ""
            try:
                raw_transcription = recognizer.recognize_google(audio_source, language="en-IN")
            except Exception:
                raw_transcription = recognizer.recognize_google(audio_source, language="en-US")

            transcription = normalize_speech_text(raw_transcription)
            if transcription != raw_transcription:
                console.print(f"[bold green]🗣️  Heard:[/bold green] [italic]\"{raw_transcription}\"[/italic] [dim]→ normalized to:[/dim] [bold cyan]\"{transcription}\"[/bold cyan]")
            else:
                console.print(f"[bold green]🗣️  Heard:[/bold green] [italic]\"{transcription}\"[/italic]")
            return transcription.strip()

        except sr.UnknownValueError:
            console.print("[bold yellow]🎙️  Sorry, I didn't catch that. Please try speaking again.[/bold yellow]")
            return ""
        except sr.RequestError as e:
            console.print(f"[dim yellow]Speech service unreachable ({e}). Please type command:[/dim yellow]")
            return input("You: ").strip()
        except Exception as e:
            console.print(f"[dim yellow]Microphone recording notice ({e}). Falling back to typing:[/dim yellow]")
            return input("You: ").strip()


voice_listener = VoiceListener()
