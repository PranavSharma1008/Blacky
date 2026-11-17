"""
Unit tests for BlackyAgent Screen Analyzing Mode.
Tests fast-path activation, MCQ request detection, server endpoints, and app window opening.
"""

import unittest
from unittest import mock
from fastapi.testclient import TestClient

from blacky.core.agent import BlackyAgent
from blacky.core.screen_mode import (
    is_mcq_request,
    extract_question_count,
    NEXT_LABELS,
)
from blacky.web.server import app
from tests.test_agent import FakeProvider


class TestScreenMode(unittest.TestCase):

    def setUp(self):
        self.agent = BlackyAgent(speak_replies=False, provider=FakeProvider())
        self.agent._capture_screen_context = lambda: {}
        self.agent._capture_screen_image = lambda ctx: None
        self.agent._capture_screen_after_action = lambda: None
        self.client = TestClient(app)

    def test_mcq_triggers(self):
        self.assertTrue(is_mcq_request("solve this mcq paper"))
        self.assertTrue(is_mcq_request("solve all mcqs one by one"))
        self.assertTrue(is_mcq_request("one mcq solve next then next"))
        self.assertTrue(is_mcq_request("solve sample paper"))
        self.assertTrue(is_mcq_request("solve 15 mcqs"))
        self.assertTrue(is_mcq_request("solve exam questions"))
        self.assertFalse(is_mcq_request("hello blacky"))
        self.assertFalse(is_mcq_request("open chrome"))

    def test_extract_question_count(self):
        self.assertEqual(extract_question_count("solve 5 mcqs"), 5)
        self.assertEqual(extract_question_count("solve 20 questions"), 20)
        self.assertEqual(extract_question_count("solve mcq paper", default=10), 10)

    def test_next_labels_coverage(self):
        self.assertIn("Save & Next", NEXT_LABELS)
        self.assertIn("Save and Next", NEXT_LABELS)
        self.assertIn("Submit & Next", NEXT_LABELS)
        self.assertIn("Next >", NEXT_LABELS)
        self.assertIn("Proceed", NEXT_LABELS)

    @mock.patch("blacky.web.server.ensure_screen_mode_active")
    def test_fast_path_activation(self, mock_ensure):
        mock_ensure.return_value = True

        commands = [
            "activate screen analyzing mode",
            "activate screen mode",
            "open screen analyzing mode",
            "open screen mode",
            "start screen analyzing mode",
            "screen analyzing mode",
            "screen mode",
            "can you activate screen analyzing mode",
            "please open screen mode",
        ]

        for cmd in commands:
            res = self.agent._check_fast_path(cmd)
            self.assertIsNotNone(res, f"Failed on command: {cmd}")
            self.assertIn("Screen Analyzing Mode Activated", res)

        self.assertEqual(mock_ensure.call_count, len(commands))

    def test_api_screen_status(self):
        res = self.client.get("/api/screen/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("ready", data)
        self.assertIn("vision_model", data)

    def test_api_screen_apps(self):
        res = self.client.get("/api/screen/apps")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("apps", data)
        self.assertIsInstance(data["apps"], list)

    def test_api_screen_index(self):
        res = self.client.get("/screen")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Blacky Companion", res.text)

    def test_api_screen_window_controls(self):
        res_hide = self.client.post("/api/screen/window/hide")
        self.assertEqual(res_hide.status_code, 200)
        res_show = self.client.post("/api/screen/window/show")
        self.assertEqual(res_show.status_code, 200)
        res_toggle = self.client.post("/api/screen/window/toggle")
        self.assertEqual(res_toggle.status_code, 200)


if __name__ == "__main__":
    unittest.main()
