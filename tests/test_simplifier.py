"""
Unit tests for CommandSimplifier and Media Fast-Path in BlackyAgent.
"""

import unittest
from unittest.mock import patch, MagicMock

from blacky.core.simplifier import CommandSimplifier
from blacky.core.agent import BlackyAgent
from blacky.core.ollama_client import OllamaProvider


class TestCommandSimplifier(unittest.TestCase):
    def test_voice_rambling_youtube_play_with_browser(self):
        rambling = (
            "I have a task that you have to open the brave and search for the YouTube "
            "and inside the YouTube you have to search for the bulleya song and I have "
            "to that you have to play it song and play that song bulleya"
        )
        distilled = CommandSimplifier.simplify(rambling)
        self.assertEqual(distilled, "play bulleya song on youtube in Brave Browser")

    def test_conversational_youtube_play_in_chrome(self):
        rambling = "open chrome and go to youtube and search for kesariya song and play it"
        distilled = CommandSimplifier.simplify(rambling)
        self.assertEqual(distilled, "play kesariya song on youtube in Google Chrome")

    def test_youtube_search_without_play(self):
        rambling = "open brave and search for python tutorials on youtube"
        distilled = CommandSimplifier.simplify(rambling)
        self.assertEqual(distilled, "search for python tutorials on youtube in Brave Browser")

    def test_web_search_rambling(self):
        rambling = "open chrome and search for latest ai news on google"
        distilled = CommandSimplifier.simplify(rambling)
        self.assertEqual(distilled, "search for latest ai news on google in Google Chrome")

    def test_whatsapp_preamble_stripping(self):
        rambling = "I have a task that you have to open whatsapp and search velocity and send him thanks message"
        distilled = CommandSimplifier.simplify(rambling)
        self.assertEqual(distilled, "open whatsapp and search velocity and send him thanks message")

    def test_search_here_youtube_and_open_it(self):
        distilled = CommandSimplifier.simplify("search here youtube and open it")
        self.assertEqual(distilled, "open youtube")

        distilled2 = CommandSimplifier.simplify("search on this youtube and open it")
        self.assertEqual(distilled2, "open youtube")

    def test_whatsapp_typo_normalization(self):
        distilled = CommandSimplifier.simplify("open whatsapp and serch velocity and send him thanks message")
        self.assertEqual(distilled, "open whatsapp and search velocity and send him thanks message")

    def test_leetcode_rambling(self):
        rambling = (
            "I have a task that you have to open leetcode and search for "
            "4. Median of Two Sorted Arrays and solve this on leetcode and submit in java language"
        )
        distilled = CommandSimplifier.simplify(rambling)
        self.assertEqual(distilled, "solve and submit Median of Two Sorted Arrays on leetcode in java")

    def test_general_preamble_stripping(self):
        clean = CommandSimplifier.simplify("Can you please do one thing for me open spotify")
        self.assertEqual(clean, "open spotify")

        clean_hi = CommandSimplifier.simplify("Ek kaam karo chrome kholo")
        self.assertEqual(clean_hi, "chrome kholo")


class FakeProvider(OllamaProvider):
    model = "qwen3.5:4b"

    def __init__(self):
        pass

    def check_connection(self):
        return True, "ok"

    def has_model(self, name):
        return True

    def vision_status(self):
        return False, "no vision"

    def is_available(self):
        return True


class TestMediaFastPath(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider()
        self.agent = BlackyAgent(speak_replies=False, provider=self.provider)
        self.agent._capture_screen_context = lambda: {}
        self.agent._capture_screen_image = lambda ctx: None
        self.agent._capture_screen_after_action = lambda: None

    @patch("blacky.tools.web.youtube_play")
    def test_media_fast_path_play_with_browser(self, mock_yt):
        mock_yt.return_value = "Playing 'bulleya song' on YouTube in Brave Browser"
        res = self.agent._check_fast_path("play bulleya song on youtube in Brave Browser")
        self.assertIsNotNone(res)
        mock_yt.assert_called_once_with(query="bulleya song", browser="Brave Browser")

    @patch("blacky.tools.web.youtube_play")
    def test_media_fast_path_hindi_chalao(self, mock_yt):
        mock_yt.return_value = "Playing 'kesariya' on YouTube"
        res = self.agent._check_fast_path("youtube pe kesariya chalao")
        self.assertIsNotNone(res)
        mock_yt.assert_called_once_with(query="kesariya", browser="")

    @patch("blacky.tools.web.browser_search")
    def test_media_fast_path_search_with_browser(self, mock_search):
        mock_search.return_value = "Searched YouTube for 'python tutorials'"
        res = self.agent._check_fast_path("search for python tutorials on youtube in Google Chrome")
        self.assertIsNotNone(res)
        mock_search.assert_called_once_with(query="python tutorials", site="youtube", browser="Google Chrome")

    @patch("blacky.tools.web.youtube_play")
    def test_agent_run_end_to_end_distillation(self, mock_yt):
        mock_yt.return_value = "Playing 'bulleya song' on YouTube in Brave Browser"
        rambling = (
            "I have a task that you have to open the brave and search for the YouTube "
            "and inside the YouTube you have to search for the bulleya song and I have "
            "to that you have to play it song and play that song bulleya"
        )
        res = self.agent.run(rambling)
        mock_yt.assert_called_once_with(query="bulleya song", browser="Brave Browser")
        self.assertIn("Playing 'bulleya song'", res)

    @patch("blacky.tools.whatsapp.whatsapp_send_message")
    def test_whatsapp_fast_path_serch_typo(self, mock_wa):
        mock_wa.return_value = "Message sent to velocity."
        res = self.agent.run("open whatsapp and serch velocity and send him thanks message")
        self.assertIn("Message sent to velocity", res)
        mock_wa.assert_called_once_with(contact="velocity", message="thanks")

    @patch("blacky.tools.macos.open_application")
    def test_search_here_youtube_opens_youtube(self, mock_app):
        mock_app.return_value = "Opened YouTube."
        res = self.agent.run("search here youtube and open it")
        self.assertIn("Opened YouTube", res)
        mock_app.assert_called_once_with("YouTube", new_tab=False)

    @patch("blacky.tools.whatsapp.whatsapp_send_message")
    def test_screen_chat_api_whatsapp_fast_path(self, mock_wa):
        from fastapi.testclient import TestClient
        from blacky.web.server import app

        mock_wa.return_value = "Message sent to velocity."
        client = TestClient(app)
        resp = client.post(
            "/api/screen/chat",
            json={"prompt": "open whatsapp and serch velocity and send him thanks message", "target_app": "Auto"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["response"], "Message sent to velocity.")
        mock_wa.assert_called_once_with(contact="velocity", message="thanks")

    @patch("blacky.tools.macos.open_application")
    def test_screen_chat_api_search_here_youtube(self, mock_app):
        from fastapi.testclient import TestClient
        from blacky.web.server import app

        mock_app.return_value = "Opened YouTube."
        client = TestClient(app)
        resp = client.post(
            "/api/screen/chat",
            json={"prompt": "search here youtube and open it", "target_app": "Auto"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["response"], "Opened YouTube.")
        mock_app.assert_called_once_with("YouTube", new_tab=False)


if __name__ == "__main__":
    unittest.main()
