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

    # Gemini API settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
    GEMINI_FALLBACK_MODELS: list[str] = [
        m.strip()
        for m in os.getenv(
            "GEMINI_FALLBACK_MODELS",
            "gemini-flash-latest,gemini-3-flash-preview,gemini-flash-lite-latest",
        ).split(",")
        if m.strip()
    ]

    # Voice & Audio
    BLACKY_VOICE: str = os.getenv("BLACKY_VOICE", "Samantha").strip()
    BLACKY_SPEECH_RATE: int = int(os.getenv("BLACKY_SPEECH_RATE", "195"))
    BLACKY_VOICE_ENABLED: bool = os.getenv(
        "BLACKY_VOICE_ENABLED", "false"
    ).lower() in ("1", "true", "yes")

    # Mobile Remote Web Server
    MOBILE_SERVER_PORT: int = int(os.getenv("MOBILE_SERVER_PORT", "8000"))
    MOBILE_SERVER_HOST: str = os.getenv("MOBILE_SERVER_HOST", "0.0.0.0")

    # Working Directory for File System Tools
    BASE_DIR: Path = Path.cwd()

    @classmethod
    def validate(cls) -> bool:
        """Validate critical configuration."""
        if not cls.GEMINI_API_KEY:
            return False
        return True


config = Config()
