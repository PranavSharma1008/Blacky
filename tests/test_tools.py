"""
Unit tests for BlackyAgent tool registry and execution tools.
"""

import unittest
from blacky.tools.base import registry
from blacky.tools.terminal import run_terminal_command, run_python_code
from blacky.tools.macos import get_system_info
from blacky.tools.mobile import mobile_get_connected_devices


class TestTools(unittest.TestCase):

    def test_registry_has_all_tools(self):
        tools = registry.get_all_tools()
        names = [t.__name__ for t in tools]
        self.assertIn("create_folder", names)
        self.assertIn("write_file", names)
        self.assertIn("run_terminal_command", names)
        self.assertIn("run_python_code", names)
        self.assertIn("search_web", names)
        self.assertIn("open_application", names)
        self.assertIn("get_system_info", names)
        self.assertIn("mobile_get_connected_devices", names)

    def test_terminal_command_execution(self):
        res = run_terminal_command("echo 'Hello BlackyAgent'")
        self.assertIn("Exit Code: 0", res)
        self.assertIn("Hello BlackyAgent", res)

    def test_python_code_execution(self):
        code = "print(2 + 2)"
        res = run_python_code(code)
        self.assertIn("Exit Code: 0", res)
        self.assertIn("4", res)

    def test_system_info(self):
        info = get_system_info()
        self.assertIn("CPU Usage:", info)
        self.assertIn("RAM Usage:", info)

    def test_mobile_check(self):
        mob_res = mobile_get_connected_devices()
        self.assertTrue(len(mob_res) > 0)


if __name__ == "__main__":
    unittest.main()
