"""
Unit tests for WhatsApp automation tools in BlackyAgent.
"""

import unittest
from blacky.tools.whatsapp import (
    whatsapp_open_chat,
    whatsapp_send_message,
    whatsapp_start_video_call,
    whatsapp_start_voice_call,
    _clean_phone,
)


class TestWhatsAppTools(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
