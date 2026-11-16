"""
Configuration manager for BlackyAgent.
Loads settings from .env and environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Search for .env in current directory or project root
_env_path = Path.cwd() / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(dotenv_path=_env_path, override=True)


class Config:
    """Central application configuration."""

    # --- Ollama (local LLM provider) ---
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:4b").strip()
    # Optional local vision model (e.g. llava:7b, moondream, qwen2.5vl:3b).
    # Empty means screen-image understanding is disabled; nothing is auto-downloaded.
    OLLAMA_VISION_MODEL: str = os.getenv("OLLAMA_VISION_MODEL", "").strip()
    OLLAMA_TIMEOUT: float = float(os.getenv("OLLAMA_TIMEOUT", "300"))
    OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "10m").strip()
    OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
    OLLAMA_NUM_PREDICT: int = int(os.getenv("OLLAMA_NUM_PREDICT", "512"))
    # Let thinking-capable models reason before answering (slower on small Macs).
    OLLAMA_THINK: bool = os.getenv("OLLAMA_THINK", "false").lower() in ("1", "true", "yes")
    # Conversation turns kept when talking to the local model.
    OLLAMA_HISTORY_MESSAGES: int = int(os.getenv("OLLAMA_HISTORY_MESSAGES", "24"))
    # Hard cap on tool-execution hops per turn.
    BLACKY_MAX_TOOL_HOPS: int = int(os.getenv("BLACKY_MAX_TOOL_HOPS", "8"))

    # Voice & Audio
    BLACKY_VOICE: str = os.getenv("BLACKY_VOICE", "Samantha").strip()
    BLACKY_SPEECH_RATE: int = int(os.getenv("BLACKY_SPEECH_RATE", "195"))
    BLACKY_VOICE_ENABLED: bool = os.getenv(
        "BLACKY_VOICE_ENABLED", "false"
    ).lower() in ("1", "true", "yes")
    BLACKY_VOICE_TRIGGER: str = os.getenv("BLACKY_VOICE_TRIGGER", "both").strip().lower()
    # Show the transcript and let the user fix it before execution.
    BLACKY_STT_CONFIRM: bool = os.getenv("BLACKY_STT_CONFIRM", "false").lower() in (
        "1",
        "true",
        "yes",
    )

    # Mobile Remote Web Server
    MOBILE_SERVER_PORT: int = int(os.getenv("MOBILE_SERVER_PORT", "8000"))
    MOBILE_SERVER_HOST: str = os.getenv("MOBILE_SERVER_HOST", "0.0.0.0")
    # Shared secret for remote control. When empty, remote commands are rejected
    # unless the request comes from localhost.
    MOBILE_API_TOKEN: str = os.getenv("MOBILE_API_TOKEN", "").strip()

    # Working Directory for File System Tools
    BASE_DIR: Path = Path.cwd()

    @classmethod
    def validate(cls) -> bool:
        """Validate critical configuration (a local model name must be set)."""
        return bool(cls.OLLAMA_MODEL)


config = Config()
