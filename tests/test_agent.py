"""
Unit tests for BlackyAgent core agent initialization and execution.
"""

import unittest
from blacky.config import config
from blacky.core.agent import BlackyAgent


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


if __name__ == "__main__":
    unittest.main()
