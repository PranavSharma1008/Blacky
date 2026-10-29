"""
Text-to-Speech (TTS) engine for BlackyAgent using native macOS speech synthesis.
"""

import os
import re
import shutil
import subprocess
import threading
from blacky.config import config


def clean_text_for_speech(text: str) -> str:
    """
    Format and trim speech for natural, concise operational voice feedback.
    Strips out long quoted messages, code, URLs, and keeps speech strictly operational
    (e.g. 'Calling Satyam', 'Message sent to Satyam') without reading back long message bodies.
    """
    # Remove code blocks entirely or summarize them
    text = re.sub(r"```[\s\S]*?```", " Code generated. ", text)
    # Remove long quoted message bodies (so it never speaks entire dictated messages)
    text = re.sub(r'["“\'][^"”\']{15,}["”\']', '', text)
    # Remove inline code marks
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove markdown headers and emphasis
    text = re.sub(r"[#*_~>]+", "", text)
    # Remove markdown links: [label](url) -> label
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Remove raw URLs
    text = re.sub(r"https?://\S+", "", text)
    # Collapse multiple whitespaces
    text = re.sub(r"\s+", " ", text).strip()

    # Keep only the operational status (at most first 2 concise sentences)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) > 2:
        text = " ".join(sentences[:2]).strip()

    # Cap character length to prevent rambling
    if len(text) > 160:
        text = text[:157].rsplit(" ", 1)[0] + "."

    return text


class VoiceEngine:
    """Manages speech synthesis on macOS."""

    def __init__(
        self,
        voice: str | None = None,
        rate: int | None = None,
        enabled: bool | None = None,
    ):
        self.voice = voice or config.BLACKY_VOICE
        self.rate = rate or config.BLACKY_SPEECH_RATE
        self._enabled = enabled
        self._say_bin = shutil.which("say") or "/usr/bin/say"
        self._current_process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        if self._enabled is not None:
            return self._enabled
        return config.BLACKY_VOICE_ENABLED

    @enabled.setter
    def enabled(self, val: bool | None) -> None:
        self._enabled = val

    def speak(self, text: str, wait: bool = False) -> None:
        """
        Speak text aloud.
        If wait is False, speaks asynchronously without blocking the terminal.
        """
        if not self.enabled or not os.path.exists(self._say_bin):
            return

        speech_text = clean_text_for_speech(text)
        if not speech_text:
            return

        def _run():
            with self._lock:
                self.stop()
                try:
                    cmd = [
                        self._say_bin,
                        "-v",
                        self.voice,
                        "-r",
                        str(self.rate),
                        speech_text,
                    ]
                    self._current_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self._current_process.wait()
                except Exception:
                    pass
                finally:
                    self._current_process = None

        if wait:
            _run()
        else:
            thread = threading.Thread(target=_run, daemon=True)
            thread.start()

    def stop(self) -> None:
        """Interrupt and terminate ongoing speech."""
        if self._current_process and self._current_process.poll() is None:
            try:
                self._current_process.terminate()
            except Exception:
                pass


voice_engine = VoiceEngine()
