"""
Voice module for BlackyAgent (TTS & STT).
"""
from blacky.voice.tts import voice_engine, clean_text_for_speech
from blacky.voice.stt import (
    voice_listener,
    play_feedback_sound,
    post_system_notification,
    normalize_speech_text,
)

__all__ = [
    "voice_engine",
    "clean_text_for_speech",
    "voice_listener",
    "play_feedback_sound",
    "post_system_notification",
    "normalize_speech_text",
]
