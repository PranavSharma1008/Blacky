"""
Unit tests for WhatsApp automation tools in BlackyAgent.
"""

import unittest
from blacky.tools.whatsapp import (
    whatsapp_open_chat,
    whatsapp_send_message,
    whatsapp_start_video_call,
    whatsapp_start_voice_call,
    whatsapp_click_send_button,
    _clean_phone,
    _is_self_target,
    _contact_match_score,
    _extract_whatsapp_candidates,
    _resolve_whatsapp_candidates,
)


class TestWhatsAppTools(unittest.TestCase):

    def test_is_self_target(self):
        self.assertTrue(_is_self_target("You"))
        self.assertTrue(_is_self_target("you"))
        self.assertTrue(_is_self_target("me"))
        self.assertTrue(_is_self_target("myself"))
        self.assertTrue(_is_self_target("my own chat"))
        self.assertFalse(_is_self_target("Satyam"))
        self.assertFalse(_is_self_target("John Doe"))

    def test_clean_phone(self):
        self.assertEqual(_clean_phone("+1 234-567-8901"), "+12345678901")
        self.assertEqual(_clean_phone("9876543210"), "9876543210")
        self.assertIsNone(_clean_phone("Satyam"))
        self.assertIsNone(_clean_phone("John Doe"))

    def test_tools_callable(self):
        self.assertTrue(callable(whatsapp_open_chat))
        self.assertTrue(callable(whatsapp_send_message))
        self.assertTrue(callable(whatsapp_start_video_call))
        self.assertTrue(callable(whatsapp_start_voice_call))
        self.assertTrue(callable(whatsapp_click_send_button))

    def test_contact_match_score(self):
        # Case insensitive exact match
        self.assertEqual(_contact_match_score("yash baniya", "Yash Baniya"), 1.0)
        self.assertEqual(_contact_match_score("YASH BANIYA", "yash baniya"), 1.0)
        # Prefix match
        self.assertGreater(_contact_match_score("yash", "yash baniya"), 0.90)
        self.assertGreater(_contact_match_score("yash baniy", "yash baniya"), 0.95)
        # Substring / word match
        self.assertGreater(_contact_match_score("baniya", "yash baniya"), 0.80)
        # Typo / character sequence match
        self.assertGreater(_contact_match_score("yash banya", "yash baniya"), 0.90)
        # Unrelated text
        self.assertLess(_contact_match_score("yash baniya", "Satyam"), 0.35)

    def test_extract_and_resolve_from_user_screenshot(self):
        ocr_screenshot = """
[101, 105, 70, 20] -> Chats
[341, 200, 158, 30] -> Q yash baniy
[301, 341, 91, 26] -> Chats
[445, 428, 159, 26] -> Yash Baniya
[445, 470, 229, 24] -> Chal bata diyo 9 15
[863, 430, 118, 24] -> Yesterday
[301, 583, 296, 32] -> Groups in common
[445, 666, 210, 30] -> G2 LANDERs£
[445, 712, 470, 24] -> Yash Baniya is also in this group
"""
        scale = 2.0
        for query in ("yash baniya", "Yash Baniya", "YASH BANIYA", "yash", "yash bani", "yash baniy", "yash banya"):
            cands = _extract_whatsapp_candidates(ocr_screenshot, query, scale)
            status, res = _resolve_whatsapp_candidates(cands, query)
            self.assertEqual(status, "EXACT", f"Failed for query: {query}")
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["name"], "Yash Baniya")
            # Verify coordinates point to Yash Baniya row
            self.assertEqual(res[0]["x"], 262)
            self.assertEqual(res[0]["y"], 220)

    def test_disambiguation_when_multiple_matches(self):
        ocr_multiple = """
[301, 341, 91, 26] -> Chats
[445, 428, 159, 26] -> Yash Baniya
[445, 520, 159, 26] -> Yash Sharma
[301, 620, 296, 32] -> Groups in common
"""
        cands = _extract_whatsapp_candidates(ocr_multiple, "yash", 2.0)
        status, res = _resolve_whatsapp_candidates(cands, "yash")
        self.assertEqual(status, "AMBIGUOUS")
        self.assertEqual(len(res), 2)
        names = [c["name"] for c in res]
        self.assertIn("Yash Baniya", names)
        self.assertIn("Yash Sharma", names)

        # Clear winner matches exactly
        cands_exact = _extract_whatsapp_candidates(ocr_multiple, "yash baniya", 2.0)
        status_exact, res_exact = _resolve_whatsapp_candidates(cands_exact, "yash baniya")
        self.assertEqual(status_exact, "EXACT")
        self.assertEqual(len(res_exact), 1)
        self.assertEqual(res_exact[0]["name"], "Yash Baniya")


if __name__ == "__main__":
    unittest.main()
