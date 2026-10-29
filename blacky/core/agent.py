"""
Agent core orchestrator for BlackyAgent.
Uses Google Gemini API with Automatic Function Calling (AFC) and tool dispatch.
"""

from typing import Any
from google import genai
from google.genai import types

from blacky.config import config
from blacky.core.prompts import SYSTEM_INSTRUCTION
from blacky.tools import registry
from blacky.voice import voice_engine
from blacky.ui.console import (
    console,
    print_agent_thought,
    print_agent_response,
    print_warning,
    print_error,
)


class BlackyAgent:
    """Core autonomous AI agent orchestrator."""

    def __init__(self, speak_replies: bool = False):
        self.api_key = config.GEMINI_API_KEY
        self.primary_model = config.GEMINI_MODEL
        self.fallback_models = config.GEMINI_FALLBACK_MODELS
        self.speak_replies = speak_replies
        self.client: genai.Client | None = None
        self.chat = None
        self.active_model = self.primary_model
        self._init_client()

    def _init_client(self) -> None:
        """Initialize Google GenAI client with fast retry options."""
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured! Please add it to your .env file."
            )

        # Set attempts=1 and 12s timeout so it fails over fast instead of hanging
        http_opts = types.HttpOptions(
            timeout=12000,
            retry_options=types.HttpRetryOptions(attempts=1),
        )

        self.client = genai.Client(api_key=self.api_key, http_options=http_opts)
        self._setup_chat_session(self.primary_model)

    def _setup_chat_session(self, model_name: str) -> bool:
        """Create a chat session with registered tools."""
        try:
            tools = registry.get_all_tools()
            self.chat = self.client.chats.create(
                model=model_name,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=tools,
                    temperature=0.2,
                ),
            )
            self.active_model = model_name
            return True
        except Exception as e:
            return False

    def run(self, user_prompt: str) -> str:
        """
        Execute user request through the ReAct agent loop.
        Handles tool execution, model fallback, voice synthesis, and formatted output.
        """
        if not user_prompt or not user_prompt.strip():
            return ""

        print_agent_thought("Analyzing request and planning actions...")

        models_to_try = [self.active_model] + [
            m for m in self.fallback_models if m != self.active_model
        ]

        last_error = None
        for model in models_to_try:
            try:
                if self.active_model != model or self.chat is None:
                    success = self._setup_chat_session(model)
                    if not success:
                        continue

                response = self.chat.send_message(user_prompt)
                response_text = response.text or "Done!"

                # Output to console
                print_agent_response(response_text)

                # Voice output (Siri-like)
                if self.speak_replies and config.BLACKY_VOICE_ENABLED:
                    voice_engine.speak(response_text, wait=False)

                return response_text

            except Exception as e:
                err_str = str(e)
                last_error = err_str
                err_lower = err_str.lower()
                # Check for rate limit, quota, demand spike, timeout, or model not found
                if any(x in err_lower for x in ("503", "504", "deadline", "timeout", "404", "unavailable", "resource_exhausted", "429", "quota")):
                    print_warning(f"Model '{model}' busy or timed out. Seamlessly switching to backup model...")
                    continue
                else:
                    print_error(f"Execution error: {err_str}")
                    return f"Error: {err_str}"

        fail_msg = f"All models currently rate-limited. Please wait 30 seconds and try again. (Details: {last_error})"
        print_error(fail_msg)
        return fail_msg


def create_agent(speak_replies: bool = False) -> BlackyAgent:
    """Factory function to build a BlackyAgent instance."""
    return BlackyAgent(speak_replies=speak_replies)
