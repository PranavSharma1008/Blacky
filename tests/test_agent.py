"""
Unit tests for BlackyAgent core agent initialization and execution.
The local model is mocked: no Ollama call is made by this module.
"""

import unittest
from unittest import mock

from blacky.config import config
from blacky.core.agent import BlackyAgent
from blacky.core.ollama_client import ModelReply, OllamaProvider
from blacky.tools import registry


class FakeProvider(OllamaProvider):
    """Minimal stand-in for OllamaProvider used across the unit tests."""

    model = "qwen3.5:4b"

    def __init__(self, replies: list[ModelReply] | None = None):
        self.replies = list(replies or [])
        self.calls: list[list[dict]] = []

    def chat(self, messages, tools=None, model=None, allowed_tools=None, think=None, **kwargs):
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


def make_agent(replies=None) -> BlackyAgent:
    agent = BlackyAgent(speak_replies=False, provider=FakeProvider(replies))
    # Keep tests off the macOS screen.
    agent._capture_screen_context = lambda: {}
    agent._capture_screen_image = lambda ctx: None
    agent._capture_screen_after_action = lambda: None
    return agent


class TestAgent(unittest.TestCase):

    def test_config_loaded(self):
        self.assertTrue(config.validate())
        self.assertTrue(len(config.OLLAMA_MODEL) > 0)

    def test_agent_initialization(self):
        agent = make_agent()
        self.assertIsNotNone(agent.provider)
        self.assertEqual(agent.active_model, config.OLLAMA_MODEL)
        self.assertEqual(agent.messages, [])
        self.assertTrue(agent.tool_schemas)

    def test_agent_single_turn_greeting(self):
        agent = make_agent([ModelReply(text="Ready")])
        response = agent.run("Hello Blacky, reply with 'Ready' in one word.")
        self.assertEqual(response, "Ready")
        self.assertEqual(agent.provider.calls[0][0]["role"], "system")

    def test_task_stage_classification(self):
        agent = make_agent()
        self.assertEqual(agent._classify_stage("Open Blinkit and search for Diet Coke"), "search")
        self.assertEqual(agent._classify_stage("Open VS Code and create a folder named Java"), "file_task")
        self.assertEqual(agent._classify_stage("in desktop make me a text file name b.txt inside that binary search code in java language"), "file_task")
        self.assertEqual(agent._classify_stage("Open WhatsApp and message Avnish hello"), "messaging")
        self.assertEqual(agent._classify_stage("add diet coke to cart"), "add")
        self.assertEqual(agent._classify_stage("open whatsapp"), "other")
        self.assertEqual(agent._classify_stage("launch whatsapp"), "other")

    def test_send_was_requested_heuristics(self):
        agent = make_agent()
        agent.task_state["stage"] = "other"
        agent.task_state["instruction"] = "open whatsapp"
        self.assertFalse(agent._send_was_requested())

        agent.task_state["stage"] = "messaging"
        agent.task_state["instruction"] = "open whatsapp"
        self.assertFalse(agent._send_was_requested())

        agent.task_state["instruction"] = "launch whatsapp"
        self.assertFalse(agent._send_was_requested())

        agent.task_state["instruction"] = "whatsapp"
        self.assertFalse(agent._send_was_requested())

        agent.task_state["instruction"] = "open whatsapp and send hello to Avnish"
        self.assertTrue(agent._send_was_requested())

        agent.task_state["instruction"] = "message Avnish on whatsapp"
        self.assertTrue(agent._send_was_requested())

    def test_verify_task_completion_open_whatsapp(self):
        agent = make_agent()
        agent.task_state["stage"] = "other"
        agent.task_state["instruction"] = "open whatsapp"
        final_text, incomplete = agent._verify_task_completion("WhatsApp opened successfully")
        self.assertFalse(incomplete)
        self.assertNotIn("Nothing has been sent yet", final_text)

    def test_verify_task_completion_strips_reasoning_monologue(self):
        agent = make_agent()
        agent.task_state["stage"] = "messaging"
        agent.task_state["instruction"] = "send hello to yash"
        monologue = "Okay, let's break down the user's command step by step. The user says..."
        final_text, incomplete = agent._verify_task_completion(monologue)
        self.assertTrue(incomplete)
        self.assertNotIn("Okay, let's break down", final_text)
        self.assertIn("Nothing has been sent yet", final_text)

    def test_clarification_cancellation(self):
        agent = make_agent()
        agent.task_state["phase"] = "awaiting_clarification"
        agent.task_state["instruction"] = "some task"
        agent.task_state["pending_question"] = "Which contact?"
        reply = agent._handle_clarification_answer("cancel")
        self.assertIn("cancelled", reply.lower())
        self.assertEqual(agent.task_state["phase"], "completed")

    def test_pending_answer_ordinal_resolution(self):
        agent = make_agent()
        agent.task_state["pending_candidates"] = [
            {"name": "Diet Coke 300 ml"},
            {"name": "Diet Coke 750 ml"},
            {"name": "Diet Coke 1.25L"},
        ]
        self.assertEqual(agent._resolve_pending_answer("second"), {"name": "Diet Coke 750 ml"})
        self.assertEqual(agent._resolve_pending_answer("the 1st one"), {"name": "Diet Coke 300 ml"})
        self.assertEqual(agent._resolve_pending_answer("3"), {"name": "Diet Coke 1.25L"})
        self.assertIsNone(agent._resolve_pending_answer("coca cola"))

    def test_disambiguation_contact_resolution(self):
        agent = make_agent()
        agent.task_state["pending_candidates"] = [
            {"name": "Satyam", "x": 100, "y": 200},
            {"name": "Satyam Brother", "x": 100, "y": 300},
        ]
        # Exact match should pick Satyam, not Satyam Brother
        self.assertEqual(agent._resolve_pending_answer("Satyam"), {"name": "Satyam", "x": 100, "y": 200})
        # Natural phrasing with action verbs and prepositions
        self.assertEqual(agent._resolve_pending_answer("text to Satyam"), {"name": "Satyam", "x": 100, "y": 200})
        self.assertEqual(agent._resolve_pending_answer("send to Satyam Brother"), {"name": "Satyam Brother", "x": 100, "y": 300})
        self.assertEqual(agent._resolve_pending_answer("1st one"), {"name": "Satyam", "x": 100, "y": 200})
        self.assertEqual(agent._resolve_pending_answer("second"), {"name": "Satyam Brother", "x": 100, "y": 300})

    def test_affirmative_and_negative_answers(self):
        agent = make_agent()
        self.assertTrue(agent._is_affirmative_answer("yes"))
        self.assertTrue(agent._is_affirmative_answer("yes please"))
        self.assertTrue(agent._is_affirmative_answer("2"))
        self.assertFalse(agent._is_affirmative_answer("no"))
        self.assertFalse(agent._is_affirmative_answer("nope"))

    def test_confirmation_gating(self):
        agent = make_agent()
        agent.task_state["instruction"] = "Open Blinkit and add Diet Coke to my cart"
        self.assertFalse(agent._requires_confirmation("blinkit_add_to_cart", {"query": "diet coke"}))
        agent.task_state["instruction"] = "Open Blinkit and go to checkout now"
        self.assertTrue(agent._requires_confirmation("blinkit_checkout_flow", {"query": "diet coke"}))
        agent.task_state["instruction"] = "Open Blinkit"
        self.assertTrue(agent._requires_confirmation("whatsapp_send_message", {"contact": "Avnish", "message": "hi"}))
        self.assertTrue(agent._requires_confirmation("delete_item", {"path": "/tmp/x.txt"}))

    def test_looks_like_new_instruction_detection(self):
        agent = make_agent()
        self.assertTrue(agent._looks_like_new_instruction("remove that item so the cart will be empty"))
        self.assertTrue(agent._looks_like_new_instruction("open blinkit and add diet coke"))
        self.assertFalse(agent._looks_like_new_instruction("the first one"))
        self.assertFalse(agent._looks_like_new_instruction("second"))

    def test_new_instruction_during_clarification_replaces_question(self):
        """A user's new/correction instruction while awaiting clarification must
        start a new task instead of being swallowed as a failed clarification answer."""
        agent = make_agent()
        agent.task_state["phase"] = "awaiting_clarification"
        agent.task_state["pending_question"] = "Which product do you want?"
        agent.task_state["pending_candidates"] = []

        new_instruction = "we have to item first of all remove that so card will be empty"
        with mock.patch.object(agent, "_run_agent_turn", return_value="ok") as mock_turn:
            result = agent._handle_clarification_answer(new_instruction)

        mock_turn.assert_called_once_with(new_instruction)
        self.assertEqual(agent.task_state["phase"], "executing")
        self.assertEqual(agent.task_state["instruction"], new_instruction)

    def test_whatsapp_fast_path_parsing(self):
        agent = make_agent()
        cases = [
            ("open whatsapp and search for You and send a hello message", ("send", "You", "hello")),
            ("open whatsapp and search for Yash and send hello", ("send", "Yash", "hello")),
            ("open whatsapp and send a hello to Yash", ("send", "Yash", "hello")),
            ("open the whatsapp and send a hello to Yash", ("send", "Yash", "hello")),
            ("open the whatsapp text yash baniya to aaj game 9:30 bajje khelenege and send him", ("send", "yash baniya", "aaj game 9:30 bajje khelenege")),
            ("open the whatsapp and text yash baniya to aaj game 9:30 bajje khelenege and send him", ("send", "yash baniya", "aaj game 9:30 bajje khelenege")),
            ("open whatsapp text yash baniya to aaj game 9:30 bajje khelenege and send him", ("send", "yash baniya", "aaj game 9:30 bajje khelenege")),
            ("send hello to You on whatsapp", ("send", "You", "hello")),
            ("send a message to Mom on whatsapp saying I am on my way", ("send", "Mom", "I am on my way")),
            ("text Alex on whatsapp: are you free?", ("send", "Alex", "are you free?")),
            ("whatsapp Rahul where are you", ("send", "Rahul", "where are you")),
            ("open whatsapp and search for Satyam", ("open", "Satyam", "")),
            ("open chat with Priya on whatsapp", ("open", "Priya", "")),
            ("open the whatsapp chat with Priya", ("open", "Priya", "")),
            ("open the WhatsApp and search for Billu", ("open", "Billu", "")),
            ("search for Billu on whatsapp", ("open", "Billu", "")),
            ("search for Billu in whatsapp", ("open", "Billu", "")),
            ("search Billu in whatsapp", ("open", "Billu", "")),
            ("now search for Billu on whatsapp", ("open", "Billu", "")),
            ("open whatsapp search avnish kal aaega cllg text huim and send", ("send", "avnish", "kal aaega cllg")),
            ("open whatsapp search avnish kal aaega cllg text him and send", ("send", "avnish", "kal aaega cllg")),
            ("open whatsapp search avnish and text him kal aaega cllg and send", ("send", "avnish", "kal aaega cllg")),
            ("open whatsapp search avnish text him kal aaega cllg and send", ("send", "avnish", "kal aaega cllg")),
            ("open whatsapp search avnish send kal aaega cllg", ("send", "avnish", "kal aaega cllg")),
            ("open whatsapp search avnish and send kal aaega cllg", ("send", "avnish", "kal aaega cllg")),
            ("open whatsapp search avnish", ("open", "avnish", "")),
            ("open whatsapp search for avnish", ("open", "avnish", "")),
            ("open the whatsapp search for avnish and send hello", ("send", "avnish", "hello")),
            ("open whatsapp search yash baniya aaj game khelenege text him and send", ("send", "yash baniya", "aaj game khelenege")),
            ("ya i need open the whatsapp and text to yash that \" kal bakend ha ni mar baunga bunk 1st lecture\"  and send him", ("send", "yash", "kal bakend ha ni mar baunga bunk 1st lecture")),
            ("yeah i need to open whatsapp and send hello to yash", ("send", "yash", "hello")),
            ("can you open whatsapp and text yash \"kal ha exam\" and send him", ("send", "yash", "kal ha exam")),
            ("open whatsapp text yash aaj game khelenge and send him", ("send", "yash", "aaj game khelenge")),
            ("ok whatsapp kkhol yash baniya ko message kr kosish krung aaj aa paya toh game kyuki nalr ha", ("send", "yash baniya", "kosish krung aaj aa paya toh game kyuki nalr ha")),
            ("open whatsapp text yash baniya osish krung aaj aa paya toh game kyuki nalr ha", ("send", "yash baniya", "osish krung aaj aa paya toh game kyuki nalr ha")),
            ("whatsapp pe yash baniya ko message kar kal cllg chalte hain", ("send", "yash baniya", "kal cllg chalte hain")),
            ("yash baniya ko whatsapp pe message bhej aaj shaam ko milte hain", ("send", "yash baniya", "aaj shaam ko milte hain")),
            ("whatsapp khol yash baniya ki chat khol", ("open", "yash baniya", "")),
            ("whatsapp kkhol yash baniya", ("open", "yash baniya", "")),
        ]
        for prompt, expected in cases:
            res = agent._parse_whatsapp_fast_path(prompt)
            self.assertEqual(res, expected, f"Failed parsing: {prompt}")

    def test_whatsapp_contextual_fast_path_parsing(self):
        agent = make_agent()
        agent.task_state["stage"] = "messaging"
        self.assertEqual(agent._parse_whatsapp_fast_path("now search for the blue"), ("open", "blue", ""))
        self.assertEqual(agent._parse_whatsapp_fast_path("search for Billu"), ("open", "Billu", ""))
        self.assertEqual(agent._parse_whatsapp_fast_path("find Billu"), ("open", "Billu", ""))
        self.assertEqual(
            agent._parse_whatsapp_fast_path("search avnish kal aaega cllg text huim and send"),
            ("send", "avnish", "kal aaega cllg"),
        )
        self.assertEqual(
            agent._parse_whatsapp_fast_path("how in the search bar search for the Yash baniya"),
            ("open", "Yash baniya", ""),
        )
        self.assertEqual(
            agent._parse_whatsapp_fast_path("in the search bar search for Yash baniya"),
            ("open", "Yash baniya", ""),
        )

    def test_whatsapp_fast_path_execution(self):
        agent = make_agent()
        with mock.patch("blacky.tools.whatsapp.whatsapp_send_message", return_value="Message sent to You") as mock_send:
            reply = agent._check_fast_path("open whatsapp and search for You and send a hello message")
            mock_send.assert_called_once_with(contact="You", message="hello")
            self.assertEqual(reply, "Message sent to You")
            self.assertEqual(agent.task_state["phase"], "completed")

    def test_whatsapp_disambiguation_completion_and_continuation(self):
        agent = make_agent()
        # Simulate agent entering awaiting_clarification with pending action and candidates
        agent.task_state["phase"] = "awaiting_clarification"
        agent.task_state["instruction"] = "open whatsapp text yash baniya osish krung aaj aa paya toh game kyuki nalr ha"
        agent.task_state["stage"] = "messaging"
        agent.task_state["pending_action"] = {
            "tool": "whatsapp_send_message",
            "args": {"contact": "yash", "message": "osish krung aaj aa paya toh game kyuki nalr ha"},
        }
        agent.task_state["pending_candidates"] = [
            {"name": "Yashika G2"},
            {"name": "Yash Baniya"},
        ]

        # 1. User answers with contact name "yash baniya"
        mock_send = mock.MagicMock(return_value="Message sent to Yash Baniya via WhatsApp: 'osish krung aaj aa paya toh game kyuki nalr ha'")
        with mock.patch.dict(registry._tools, {"whatsapp_send_message": mock_send}):
            reply = agent.run("yash baniya")
            mock_send.assert_called_once_with(contact="Yash Baniya", message="osish krung aaj aa paya toh game kyuki nalr ha")
            self.assertIn("Message sent to Yash Baniya", reply)
            self.assertEqual(agent.task_state["phase"], "completed")

    def test_whatsapp_disambiguation_with_next_operation(self):
        agent = make_agent()
        agent.task_state["phase"] = "awaiting_clarification"
        agent.task_state["instruction"] = "open whatsapp text yash baniya osish krung"
        agent.task_state["stage"] = "messaging"
        agent.task_state["pending_action"] = {
            "tool": "whatsapp_send_message",
            "args": {"contact": "yash", "message": "osish krung"},
        }
        agent.task_state["pending_candidates"] = [
            {"name": "Yashika G2"},
            {"name": "Yash Baniya"},
        ]

        # 2. User answers with contact name AND a subsequent operation: "yash baniya and open chrome"
        mock_send = mock.MagicMock(return_value="Message sent to Yash Baniya via WhatsApp: 'osish krung'")
        with mock.patch.dict(registry._tools, {"whatsapp_send_message": mock_send}):
            with mock.patch("blacky.tools.macos.open_application", return_value="Application 'Google Chrome' launched successfully in full screen.") as mock_app:
                reply = agent.run("yash baniya and open chrome")
                mock_send.assert_called_once_with(contact="Yash Baniya", message="osish krung")
                mock_app.assert_called_once_with("Google Chrome", new_tab=False)
                self.assertIn("Message sent to Yash Baniya", reply)
                self.assertIn("Opened Google Chrome", reply)
                self.assertEqual(agent.task_state["phase"], "completed")

    def test_whatsapp_disambiguation_ordinal_choice(self):
        agent = make_agent()
        agent.task_state["phase"] = "awaiting_clarification"
        agent.task_state["instruction"] = "open whatsapp text yash baniya osish krung"
        agent.task_state["stage"] = "messaging"
        agent.task_state["pending_action"] = {
            "tool": "whatsapp_send_message",
            "args": {"contact": "yash", "message": "osish krung"},
        }
        agent.task_state["pending_candidates"] = [
            {"name": "Yashika G2"},
            {"name": "Yash Baniya"},
        ]

        # 3. User answers with ordinal "second one"
        mock_send = mock.MagicMock(return_value="Message sent to Yash Baniya via WhatsApp: 'osish krung'")
        with mock.patch.dict(registry._tools, {"whatsapp_send_message": mock_send}):
            reply = agent.run("second one")
            mock_send.assert_called_once_with(contact="Yash Baniya", message="osish krung")
            self.assertIn("Message sent to Yash Baniya", reply)
            self.assertEqual(agent.task_state["phase"], "completed")

    def test_hinglish_app_opening(self):
        agent = make_agent()
        with mock.patch("blacky.tools.macos.open_application", return_value="Application 'Google Chrome' launched successfully in full screen.") as mock_app:
            reply = agent._check_fast_path("chrome kholo")
            self.assertIn("Opened Google Chrome", reply)
            mock_app.assert_called_with("Google Chrome", new_tab=False)

            reply = agent._check_fast_path("khol chrome")
            self.assertIn("Opened Google Chrome", reply)

            reply = agent._check_fast_path("spotify chalao")
            self.assertIn("Opened Spotify", reply)

    def test_conversational_and_system_fast_paths(self):
        agent = make_agent()
        reply = agent._check_fast_path("i need good agent work every work fine and in good manner")
        self.assertIn("accurately, quickly, and with great care", reply)

        reply = agent._check_fast_path("hi")
        self.assertIn("Hello! I'm Blacky", reply)

        reply = agent._check_fast_path("thank you")
        self.assertIn("welcome", reply.lower())

        reply = agent._check_fast_path("what time is it")
        self.assertIn("The time is", reply)

        reply = agent._check_fast_path("what is today's date")
        self.assertIn("Today is", reply)

        with mock.patch("blacky.tools.macos.open_application", return_value="Application 'Google Chrome' launched successfully in full screen.") as mock_app:
            reply = agent._check_fast_path("can you open chrome")
            self.assertIn("Opened Google Chrome", reply)
            mock_app.assert_called_with("Google Chrome", new_tab=False)

            reply = agent._check_fast_path("ya i need open spotify")
            self.assertIn("Opened Spotify", reply)
            mock_app.assert_called_with("Spotify", new_tab=False)

            reply = agent._check_fast_path("open blinkit in a new tab")
            self.assertIn("Opened Blinkit", reply)
            mock_app.assert_called_with("Blinkit", new_tab=True)

            with mock.patch("blacky.tools.macos.open_application", return_value="https://blinkit.com is already open in Brave Browser (brought to front in full screen).") as mock_app:
                reply = agent._check_fast_path("open blinkit")
                self.assertIn("already open", reply)
                mock_app.assert_called_with("Blinkit", new_tab=False)

    def test_history_is_recorded(self):
        agent = make_agent([ModelReply(text="Ready")])
        agent.run("say ready")
        roles = [m["role"] for m in agent.messages]
        self.assertEqual(roles, ["user", "assistant"])

    def test_reset_history(self):
        agent = make_agent([ModelReply(text="Ready")])
        agent.run("say ready")
        agent.reset_history()
        self.assertEqual(agent.messages, [])

    def test_filesystem_fast_paths(self):
        agent = make_agent()
        with mock.patch("blacky.tools.filesystem.write_file", return_value="Successfully wrote 30 lines") as mock_write:
            reply = agent._check_fast_path("in the desktop make a file name a.txt inside this add a code of binary search java code")
            self.assertIn("Created file 'a.txt' on your Desktop", reply)
            mock_write.assert_called_once()
            call_args = mock_write.call_args[1]
            self.assertEqual(call_args["file_path"], "~/Desktop/a.txt")
            self.assertIn("class BinarySearch", call_args["content"])
            self.assertIn("binarySearch", call_args["content"])

        with mock.patch("blacky.tools.filesystem.write_file", return_value="Successfully wrote 45 lines") as mock_write2:
            reply2 = agent._check_fast_path("in desktop make me a text file name b.txt inside that binary search code in java language")
            self.assertIn("Created file 'b.txt' on your Desktop", reply2)
            mock_write2.assert_called_once()
            call_args2 = mock_write2.call_args[1]
            self.assertEqual(call_args2["file_path"], "~/Desktop/b.txt")
            self.assertIn("class BinarySearch", call_args2["content"])

        with mock.patch("blacky.tools.filesystem.create_folder", return_value="Directory created") as mock_mkdir:
            reply = agent._check_fast_path("make a folder named my_project on desktop")
            self.assertIn("Created folder 'my_project' on your Desktop", reply)
            mock_mkdir.assert_called_with(folder_path="~/Desktop/my_project")

    def test_dynamic_tool_routing(self):
        agent = make_agent()
        code_tools = {t["function"]["name"] for t in agent._filter_tools_for_request("write a python script for sorting")}
        self.assertIn("write_file", code_tools)
        self.assertIn("run_python_code", code_tools)
        # Verify irrelevant tool schemas are pruned
        self.assertNotIn("whatsapp_start_video_call", code_tools)
        self.assertNotIn("blinkit_checkout_flow", code_tools)
        self.assertLess(len(code_tools), 15)

    def test_resolve_path_special_directories(self):
        from blacky.tools.filesystem import _resolve_path
        from pathlib import Path

        desktop_p = _resolve_path("desktop/a.txt")
        self.assertEqual(desktop_p, (Path.home() / "Desktop" / "a.txt").resolve())

        downloads_p = _resolve_path("downloads/file.pdf")
        self.assertEqual(downloads_p, (Path.home() / "Downloads" / "file.pdf").resolve())

        documents_p = _resolve_path("documents/report.docx")
        self.assertEqual(documents_p, (Path.home() / "Documents" / "report.docx").resolve())

    def test_leetcode_fast_path_parsing(self):
        agent = make_agent()
        with mock.patch("blacky.tools.web.leetcode_problem", return_value="Solved LeetCode Median of Two Sorted Arrays") as mock_lc:
            prompt = "4. Median of Two Sorted Arrays solve this on  leetocde and submit in java language"
            res = agent.run(prompt)
            self.assertIn("Solved LeetCode", res)
            mock_lc.assert_called_once_with(
                problem="Median of Two Sorted Arrays",
                language="java",
                solve=True,
                submit=True,
            )


if __name__ == "__main__":
    unittest.main()
