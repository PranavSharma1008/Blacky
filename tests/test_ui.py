"""
Unit tests for BlackyAgent UI screen-analysis animation states.
"""

import unittest
from blacky.ui.console import (
    SCREEN_STATES,
    get_screen_state,
    start_screen_analysis,
    stop_screen_analysis,
)


class TestScreenAnalysisAnimation(unittest.TestCase):

    def test_required_screen_states_exist(self):
        for state in (
            "observing",
            "analyzing",
            "identifying",
            "processing",
            "waiting_for_user",
            "executing",
            "verifying",
            "task_completed",
        ):
            self.assertIn(state, SCREEN_STATES)

    def test_start_and_stop_screen_analysis(self):
        start_screen_analysis("observing", detail="Foreground app: Blinkit")
        self.assertEqual(get_screen_state(), "observing")
        stop_screen_analysis("task_completed")
        self.assertEqual(get_screen_state(), "task_completed")

    def test_stop_restores_idle(self):
        start_screen_analysis("executing")
        stop_screen_analysis()
        self.assertEqual(get_screen_state(), "task_completed")


if __name__ == "__main__":
    unittest.main()
