"""
Unit tests for BlackyAgent core agent initialization and execution.
"""

import unittest
from unittest import mock
from blacky.config import config
from blacky.core.agent import BlackyAgent, _ANSWER_ORDINALS, _AFFIRMATIVE_ANSWERS, _NEGATIVE_ANSWERS


class TestAgent(unittest.TestCase):

    def test_config_loaded(self):
        self.assertTrue(config.validate())
        self.assertTrue(len(config.GEMINI_MODEL) > 0)

    def test_agent_initialization(self):
        agent = BlackyAgent(speak_replies=False)
        self.assertIsNotNone(agent.client)
        self.assertIsNotNone(agent.chat)
        self.assertEqual(agent.active_model, config.GEMINI_MODEL)

    def test_agent_single_turn_greeting(self):
        agent = BlackyAgent(speak_replies=False)
        response = agent.run("Hello Blacky, reply with 'Ready' in one word.")
        self.assertTrue(len(response) > 0)

    def test_task_stage_classification(self):
        agent = BlackyAgent(speak_replies=False)
        self.assertEqual(agent._classify_stage("Open Blinkit and search for Diet Coke"), "search")
        self.assertEqual(agent._classify_stage("Open VS Code and create a folder named Java"), "file_task")
        self.assertEqual(agent._classify_stage("Open WhatsApp and message Avnish hello"), "messaging")
        self.assertEqual(agent._classify_stage("add diet coke to cart"), "add")

    def test_pending_answer_ordinal_resolution(self):
        agent = BlackyAgent(speak_replies=False)
        agent.task_state["pending_candidates"] = [
            {"name": "Diet Coke 300 ml"},
            {"name": "Diet Coke 750 ml"},
            {"name": "Diet Coke 1.25L"},
        ]
        self.assertEqual(agent._resolve_pending_answer("second"), {"name": "Diet Coke 750 ml"})
        self.assertEqual(agent._resolve_pending_answer("the 1st one"), {"name": "Diet Coke 300 ml"})
        self.assertEqual(agent._resolve_pending_answer("3"), {"name": "Diet Coke 1.25L"})
        self.assertIsNone(agent._resolve_pending_answer("coca cola"))

    def test_affirmative_and_negative_answers(self):
        agent = BlackyAgent(speak_replies=False)
        self.assertTrue(agent._is_affirmative_answer("yes"))
        self.assertTrue(agent._is_affirmative_answer("yes please"))
        self.assertTrue(agent._is_affirmative_answer("2"))
        self.assertFalse(agent._is_affirmative_answer("no"))
        self.assertFalse(agent._is_affirmative_answer("nope"))

    def test_confirmation_gating(self):
        agent = BlackyAgent(speak_replies=False)
        agent.task_state["instruction"] = "Open Blinkit and add Diet Coke to my cart"
        self.assertFalse(agent._requires_confirmation("blinkit_add_to_cart", {"query": "diet coke"}))
        agent.task_state["instruction"] = "Open Blinkit and go to checkout now"
        self.assertTrue(agent._requires_confirmation("blinkit_checkout_flow", {"query": "diet coke"}))
        agent.task_state["instruction"] = "Open Blinkit"
        self.assertTrue(agent._requires_confirmation("whatsapp_send_message", {"contact": "Avnish", "message": "hi"}))
        self.assertTrue(agent._requires_confirmation("delete_item", {"path": "/tmp/x.txt"}))

    def test_looks_like_new_instruction_detection(self):
        agent = BlackyAgent(speak_replies=False)
        self.assertTrue(agent._looks_like_new_instruction("remove that item so the cart will be empty"))
        self.assertTrue(agent._looks_like_new_instruction("open blinkit and add diet coke"))
        self.assertFalse(agent._looks_like_new_instruction("the first one"))
        self.assertFalse(agent._looks_like_new_instruction("second"))

    def test_new_instruction_during_clarification_replaces_question(self):
        """A user's new/correction instruction while awaiting clarification must
        start a new task instead of being swallowed as a failed clarification answer."""
        agent = BlackyAgent(speak_replies=False)
        agent.task_state["phase"] = "awaiting_clarification"
        agent.task_state["pending_question"] = "Which product do you want?"
        agent.task_state["pending_candidates"] = []

        new_instruction = "we have to item first of all remove that so card will be empty"
        with mock.patch.object(agent, "_run_agent_turn", return_value="ok") as mock_turn:
            result = agent._handle_clarification_answer(new_instruction)

        mock_turn.assert_called_once_with(new_instruction)
        self.assertEqual(agent.task_state["phase"], "executing")
        self.assertEqual(agent.task_state["instruction"], new_instruction)


if __name__ == "__main__":
    unittest.main()
