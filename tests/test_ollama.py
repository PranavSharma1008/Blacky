"""
Tests for the local Ollama provider, tool-schema conversion, the agent tool loop
and the mobile API.

Every model call is mocked: these tests never need a running Ollama server or a
downloaded model.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

from blacky.config import config
from blacky.core.agent import BlackyAgent
from blacky.core.ollama_client import (
    ModelReply,
    OllamaModelMissingError,
    OllamaProvider,
    OllamaUnavailableError,
    ToolCall,
    _extract_json_tool_call,
    _strip_inline_reasoning,
)
from blacky.tools import registry
from blacky.tools.base import build_function_schema


# ----------------------------------------------------------------------
# Fakes
# ----------------------------------------------------------------------
class FakeClient:
    """Stands in for ollama.Client."""

    def __init__(self, models=None, reply=None, list_error=None, chat_error=None, stream=None):
        self._models = models if models is not None else ["qwen3:4b"]
        self._reply = reply
        self._list_error = list_error
        self._chat_error = chat_error
        self._stream = stream or []
        self.chat_kwargs = None

    def list(self):
        if self._list_error:
            raise self._list_error
        return SimpleNamespace(
            models=[
                SimpleNamespace(
                    model=m,
                    capabilities=(
                        ["completion", "tools", "vision"]
                        if "llava" in m
                        else (["completion"] if "tinyllama" in m else ["completion", "tools", "thinking"])
                    ),
                )
                for m in self._models
            ]
        )

    def chat(self, **kwargs):
        self.chat_kwargs = kwargs
        if self._chat_error:
            raise self._chat_error
        if kwargs.get("stream"):
            return iter(self._stream)
        return self._reply


def reply_with(text=None, name=None, arguments=None):
    message = SimpleNamespace(content=text, thinking=None, tool_calls=None)
    if name:
        message.tool_calls = [SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments or {}))]
    return SimpleNamespace(message=message)


class ScriptedProvider:
    """Provider double for agent tests."""

    def __init__(self, replies):
        self.model = "qwen3:4b"
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools=None, model=None, allowed_tools=None):
        self.calls.append([dict(m) for m in messages])
        if self.replies:
            return self.replies.pop(0)
        return ModelReply(text="Done.")

    def check_connection(self):
        return True, "ok"

    def has_model(self, name):
        return True

    def vision_status(self):
        return False, "no vision model"

    def is_available(self):
        return True

    def health(self):
        return {
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "connected": True,
            "detail": "ok",
            "model": self.model,
            "model_available": True,
            "vision_model": None,
            "vision_available": False,
            "vision_detail": "no vision model",
        }


def make_agent(replies):
    agent = BlackyAgent(speak_replies=False, provider=ScriptedProvider(replies))
    agent._capture_screen_context = lambda: {"front_app": "Finder"}
    agent._capture_screen_image = lambda ctx: None
    agent._capture_screen_after_action = lambda: None
    return agent


# ----------------------------------------------------------------------
# 1-2. Connection and model availability
# ----------------------------------------------------------------------
class TestOllamaConnection(unittest.TestCase):

    def test_connection_ok(self):
        provider = OllamaProvider(client=FakeClient(models=["qwen3:4b"]))
        ok, detail = provider.check_connection()
        self.assertTrue(ok)
        self.assertIn("running", detail)
        self.assertTrue(provider.is_available())

    def test_connection_failure_is_reported(self):
        provider = OllamaProvider(client=FakeClient(list_error=ConnectionError("refused")))
        ok, detail = provider.check_connection()
        self.assertFalse(ok)
        self.assertIn("Cannot reach Ollama", detail)
        self.assertFalse(provider.is_available())

    def test_model_availability_and_errors(self):
        provider = OllamaProvider(model="qwen3:4b", client=FakeClient(models=["qwen3:4b"]))
        self.assertTrue(provider.has_model("qwen3:4b"))
        self.assertTrue(provider.has_model("qwen3:4b:latest"))
        provider.ensure_model()  # no raise

        missing = OllamaProvider(model="llama3:8b", client=FakeClient(models=["qwen3:4b"]))
        self.assertFalse(missing.has_model("llama3:8b"))
        with self.assertRaises(OllamaModelMissingError) as ctx:
            missing.ensure_model()
        self.assertIn("ollama pull llama3:8b", str(ctx.exception))

    def test_health_payload(self):
        provider = OllamaProvider(client=FakeClient(models=["qwen3:4b"]))
        health = provider.health()
        self.assertEqual(health["provider"], "ollama")
        self.assertTrue(health["connected"])
        self.assertTrue(health["model_available"])
        self.assertFalse(health["vision_available"])

    def test_capabilities_come_from_server(self):
        provider = OllamaProvider(client=FakeClient(models=["qwen3:4b"]))
        self.assertIn("tools", provider.model_capabilities())


# ----------------------------------------------------------------------
# 3-5. Chat, timeouts and language handling
# ----------------------------------------------------------------------
class TestOllamaChat(unittest.TestCase):

    def test_text_chat(self):
        provider = OllamaProvider(
            client=FakeClient(reply=reply_with(text="Ready")),
        )
        reply = provider.chat([{"role": "user", "content": "hi"}])
        self.assertEqual(reply.text, "Ready")
        self.assertEqual(reply.tool_calls, [])

    def test_streaming(self):
        chunks = [SimpleNamespace(message=SimpleNamespace(content="Hel")),
                  SimpleNamespace(message=SimpleNamespace(content="lo"))]
        provider = OllamaProvider(client=FakeClient(stream=chunks))
        self.assertEqual("".join(provider.stream_chat([{"role": "user", "content": "hi"}])), "Hello")

    def test_connection_failure_during_chat(self):
        provider = OllamaProvider(client=FakeClient(chat_error=TimeoutError("timed out")))
        with self.assertRaises(OllamaUnavailableError):
            provider.chat([{"role": "user", "content": "hi"}])

    def test_inline_reasoning_is_stripped(self):
        self.assertEqual(_strip_inline_reasoning("hmm...\n</think>\n\nDONE"), "DONE")
        self.assertEqual(_strip_inline_reasoning("clean answer"), "clean answer")
        self.assertEqual(
            _strip_inline_reasoning("Okay, let's see. The user wants to...\n\nFinal Answer:\nDone!"),
            "Done!",
        )
        self.assertEqual(
            _strip_inline_reasoning("Okay, let's break down the user's command step by step..."),
            "",
        )

    def test_think_only_sent_when_supported(self):
        thinking = OllamaProvider(client=FakeClient(models=["qwen3:4b"]))
        self.assertIsNotNone(thinking._think_param("qwen3:4b"))
        plain = OllamaProvider(client=FakeClient(models=["tinyllama"]))
        self.assertIsNone(plain._think_param("tinyllama"))


# ----------------------------------------------------------------------
# 6-7. Tool schema conversion and tool-call parsing
# ----------------------------------------------------------------------
class TestToolSchemas(unittest.TestCase):

    def test_schema_conversion(self):
        def sample(path: str, count: int = 3, verbose: bool = False) -> str:
            """Do a sample action.

            Args:
                path: Where to operate.
            """
            return path

        schema = build_function_schema(sample)
        fn = schema["function"]
        self.assertEqual(schema["type"], "function")
        self.assertEqual(fn["name"], "sample")
        self.assertIn("sample action", fn["description"])
        props = fn["parameters"]["properties"]
        self.assertEqual(props["path"]["type"], "string")
        self.assertEqual(props["path"]["description"], "Where to operate.")
        self.assertEqual(props["count"], {"type": "integer", "default": 3})
        self.assertEqual(props["verbose"]["type"], "boolean")
        self.assertEqual(fn["parameters"]["required"], ["path"])

    def test_registry_schemas_cover_every_tool(self):
        schemas = registry.get_tool_schemas()
        self.assertEqual(len(schemas), len(registry.tool_names()))
        names = {s["function"]["name"] for s in schemas}
        self.assertIn("whatsapp_send_message", names)
        self.assertIn("run_terminal_command", names)

    def test_native_tool_call_parsing(self):
        client = FakeClient(reply=reply_with(text=None, name="read_file", arguments={"file_path": "a.txt"}))
        provider = OllamaProvider(client=client)
        reply = provider.chat([{"role": "user", "content": "read a.txt"}])
        self.assertEqual(reply.tool_calls, [ToolCall(name="read_file", arguments={"file_path": "a.txt"})])

    def test_json_in_text_recovery(self):
        client = FakeClient(reply=reply_with(text='```json\n{"name": "read_file", "arguments": {"file_path": "a.txt"}}\n```'))
        provider = OllamaProvider(client=client)
        reply = provider.chat([{"role": "user", "content": "read a.txt"}], allowed_tools=["read_file"])
        self.assertEqual(reply.tool_calls[0].name, "read_file")
        self.assertEqual(reply.text, "")

    def test_unknown_json_tool_is_ignored(self):
        self.assertIsNone(_extract_json_tool_call('{"name": "rm_rf", "arguments": {}}', {"read_file"}))
        client = FakeClient(reply=reply_with(text='{"name": "rm_rf", "arguments": {}}'))
        provider = OllamaProvider(client=client)
        reply = provider.chat([{"role": "user", "content": "x"}], allowed_tools=["read_file"])
        self.assertEqual(reply.tool_calls, [])

    def test_python_syntax_tool_call_recovery(self):
        client = FakeClient(
            reply=reply_with(
                text='whatsapp_send_message(contact="Yash Baniya", message="aaj game 9:30 bajje khelenege")'
            )
        )
        provider = OllamaProvider(client=client)
        reply = provider.chat(
            [{"role": "user", "content": "send msg"}], allowed_tools=["whatsapp_send_message"]
        )
        self.assertEqual(len(reply.tool_calls), 1)
        self.assertEqual(reply.tool_calls[0].name, "whatsapp_send_message")
        self.assertEqual(
            reply.tool_calls[0].arguments,
            {"contact": "Yash Baniya", "message": "aaj game 9:30 bajje khelenege"},
        )
        self.assertEqual(reply.text, "")


# ----------------------------------------------------------------------
# 8-11. Agent loop: sequential tools, invalid calls, gating, disambiguation
# ----------------------------------------------------------------------
class TestAgentToolLoop(unittest.TestCase):

    def test_sequential_tool_execution(self):
        agent = make_agent([
            ModelReply(tool_calls=[ToolCall(name="get_system_info", arguments={})]),
            ModelReply(text="RAM is 50%."),
        ])
        with mock.patch.dict(registry._tools, {"get_system_info": lambda: "RAM: 50%"}), \
             mock.patch.object(registry, "log_call"):
            result = agent.run("Check my RAM")

        self.assertEqual(result, "RAM is 50%.")
        self.assertEqual(len(agent.provider.calls), 2)
        # The follow-up turn must carry the tool result, not a synthetic nudge.
        self.assertEqual(agent.provider.calls[1][-1]["role"], "tool")
        self.assertEqual(agent.provider.calls[1][-1]["content"], "RAM: 50%")

    def test_invalid_tool_call_is_rejected(self):
        agent = make_agent([
            ModelReply(tool_calls=[ToolCall(name="rm_rf", arguments={"path": "/"})]),
            ModelReply(text="I could not do that."),
        ])
        result = agent.run("Delete everything")
        self.assertEqual(result, "I could not do that.")
        tool_msgs = [m for m in agent.messages if m["role"] == "tool"]
        self.assertIn("not a registered tool", tool_msgs[0]["content"])

    def test_malformed_arguments_are_handled(self):
        def strict(x: int) -> str:
            return str(x)

        agent = make_agent([
            ModelReply(tool_calls=[ToolCall(name="strict_tool", arguments={"bogus": 1})]),
            ModelReply(text="Bad arguments."),
        ])
        with mock.patch.dict(registry._tools, {"strict_tool": strict}):
            result = agent.run("run strict tool")
        self.assertEqual(result, "Bad arguments.")
        tool_msgs = [m for m in agent.messages if m["role"] == "tool"]
        self.assertIn("invalid arguments", tool_msgs[0]["content"])

    def test_repeated_call_is_not_reexecuted(self):
        calls = {"n": 0}

        def counter() -> str:
            calls["n"] += 1
            return "done"

        agent = make_agent([
            ModelReply(tool_calls=[ToolCall(name="counter", arguments={})]),
            ModelReply(tool_calls=[ToolCall(name="counter", arguments={})]),
            ModelReply(tool_calls=[ToolCall(name="counter", arguments={})]),
            ModelReply(text="Finished."),
        ])
        with mock.patch.dict(registry._tools, {"counter": counter}):
            result = agent.run("count once")
        self.assertEqual(calls["n"], 1)
        # The loop stops instead of burning every hop on the same call.
        self.assertIn("counter finished", result)

    def test_confirmation_gate_blocks_send(self):
        agent = make_agent([
            ModelReply(tool_calls=[ToolCall(name="whatsapp_send_message",
                                            arguments={"contact": "Avnish", "message": "hi"})]),
        ])
        with mock.patch.object(agent, "_execute_tool_call_by_name") as exec_mock:
            result = agent.run("Open WhatsApp")

        exec_mock.assert_not_called()
        self.assertIn("send a message", result)
        self.assertEqual(agent.task_state["phase"], "awaiting_clarification")
        self.assertTrue(agent.task_state["awaiting_confirmation"])

    def test_contact_disambiguation_pauses_task(self):
        ambiguous = "AMBIGUOUS_CONTACTS: 1) Rishab Sharma 2) Rishab Verma. ASK THE USER."
        agent = make_agent([
            ModelReply(tool_calls=[ToolCall(name="whatsapp_open_chat", arguments={"contact": "Rishab"})]),
        ])
        with mock.patch.dict(registry._tools, {"whatsapp_open_chat": lambda contact: ambiguous}):
            result = agent.run("WhatsApp par Rishab ka chat kholo")

        self.assertIn("AMBIGUOUS_CONTACTS", result)
        self.assertEqual(agent.task_state["phase"], "awaiting_clarification")

    def test_completion_verification_flags_missing_send(self):
        agent = make_agent([ModelReply(text="All done!")])
        result = agent.run("send a whatsapp message to Avnish saying hi")
        self.assertIn("Nothing has been sent yet", result)
        self.assertEqual(agent.task_state["phase"], "awaiting_clarification")

    def test_hinglish_command_executes_tool(self):
        captured = {}

        def fake_open(contact: str) -> str:
            captured["contact"] = contact
            return f"Opened chat with {contact}."

        agent = make_agent([
            ModelReply(tool_calls=[ToolCall(name="whatsapp_open_chat", arguments={"contact": "Palwan"})]),
            ModelReply(text="Palwan ka chat khol diya."),
        ])
        with mock.patch.dict(registry._tools, {"whatsapp_open_chat": fake_open}):
            result = agent.run("WhatsApp par Palwan ka chat kholo")

        self.assertEqual(captured["contact"], "Palwan")
        self.assertIn("khol diya", result)

    def test_model_unavailable_message(self):
        agent = make_agent([])

        def boom(*args, **kwargs):
            raise OllamaUnavailableError("Ollama did not respond")

        agent.provider.chat = boom
        result = agent.run("open chrome")
        self.assertIn("could not reach the local AI model", result)

    def test_missing_model_message(self):
        agent = make_agent([])

        def boom(*args, **kwargs):
            raise OllamaModelMissingError("Model 'qwen3:4b' is not installed locally.")

        agent.provider.chat = boom
        result = agent.run("open chrome")
        self.assertIn("not installed", result)


# ----------------------------------------------------------------------
# 12. Vision
# ----------------------------------------------------------------------
class TestVision(unittest.TestCase):

    def test_vision_disabled_without_model(self):
        provider = OllamaProvider(vision_model="", client=FakeClient(models=["qwen3:4b"]))
        ok, detail = provider.vision_status()
        self.assertFalse(ok)
        self.assertIn("disabled", detail)

    def test_vision_model_not_installed(self):
        provider = OllamaProvider(vision_model="llava:7b", client=FakeClient(models=["qwen3:4b"]))
        ok, detail = provider.vision_status()
        self.assertFalse(ok)
        self.assertIn("ollama pull llava:7b", detail)

    def test_vision_model_ready(self):
        provider = OllamaProvider(vision_model="llava:7b", client=FakeClient(models=["qwen3:4b", "llava:7b"]))
        ok, _detail = provider.vision_status()
        self.assertTrue(ok)

    def test_agent_prompt_states_screen_availability(self):
        agent = make_agent([])
        agent.vision_enabled = False
        prompt = agent._build_user_prompt("open chrome", {})
        self.assertIn("Screen Image: unavailable", prompt)
        self.assertIsNone(agent._capture_screen_image({}))


# ----------------------------------------------------------------------
# 13-14. Voice and text input both use the same agent
# ----------------------------------------------------------------------
class TestInputModes(unittest.TestCase):

    def test_typed_command_reaches_agent(self):
        from blacky import main as main_module

        agent = mock.MagicMock()
        with mock.patch.object(main_module, "show_banner"), \
             mock.patch.object(main_module, "print_user_prompt"), \
             mock.patch.object(main_module, "clear_screen_analysis"), \
             mock.patch.object(main_module.console, "input", side_effect=["open chrome", "exit"]):
            main_module.run_repl(agent)

        agent.run.assert_called_once_with("open chrome")

    def test_voice_transcript_reaches_agent(self):
        from blacky import main as main_module

        agent = mock.MagicMock()
        agent.run.return_value = "Opened Chrome."
        with mock.patch.object(main_module, "show_banner"), \
             mock.patch.object(main_module, "print_user_prompt"), \
             mock.patch.object(main_module, "post_system_notification"), \
             mock.patch.object(main_module.voice_listener, "listen_push_to_talk",
                               side_effect=["Open Chrome", "exit"]):
            main_module.run_voice_loop(agent)

        agent.run.assert_called_once_with("Open Chrome")

    def test_unreliable_transcription_is_rejected(self):
        from blacky.voice.stt import is_reliable_transcription

        self.assertFalse(is_reliable_transcription(""))
        self.assertFalse(is_reliable_transcription("a b c d"))
        self.assertTrue(is_reliable_transcription("open chrome please"))


# ----------------------------------------------------------------------
# 15-16. FastAPI mobile endpoint
# ----------------------------------------------------------------------
class TestMobileApi(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from blacky.web import server

        self.server = server
        self.client = TestClient(server.app)

    def test_status_reports_ollama_state(self):
        fake = SimpleNamespace(health=lambda: {
            "provider": "ollama", "base_url": "http://localhost:11434", "connected": True,
            "detail": "ok", "model": "qwen3:4b", "model_available": True,
            "vision_model": None, "vision_available": False, "vision_detail": "disabled",
        })
        with mock.patch.object(self.server, "OllamaProvider", return_value=fake):
            self.server._agent = None
            data = self.client.get("/api/status").json()

        self.assertEqual(data["status"], "online")
        self.assertEqual(data["ollama"]["model"], "qwen3:4b")
        self.assertTrue(data["agent_ready"])

    def test_chat_endpoint_uses_agent(self):
        fake_agent = mock.MagicMock()
        fake_agent.run.return_value = "Opened Chrome."
        with mock.patch.object(self.server, "BlackyAgent", return_value=fake_agent), \
             mock.patch.object(self.server.registry, "get_recent_logs", return_value=[]), \
             mock.patch.object(config, "MOBILE_API_TOKEN", "test-token"):
            self.server._agent = None
            res = self.client.post(
                "/api/chat",
                json={"prompt": "open chrome"},
                headers={"X-Blacky-Token": "test-token"},
            )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["response"], "Opened Chrome.")
        fake_agent.run.assert_called_once_with("open chrome")

    def test_remote_call_requires_token(self):
        with mock.patch.object(config, "MOBILE_API_TOKEN", ""):
            with self.assertRaises(Exception):
                self.server._authorize(None, "192.168.1.50")
            self.server._authorize(None, "127.0.0.1")  # localhost always allowed

    def test_remote_call_accepts_valid_token(self):
        with mock.patch.object(config, "MOBILE_API_TOKEN", "secret"):
            self.server._authorize("secret", "192.168.1.50")
            with self.assertRaises(Exception):
                self.server._authorize("wrong", "192.168.1.50")


if __name__ == "__main__":
    unittest.main()
