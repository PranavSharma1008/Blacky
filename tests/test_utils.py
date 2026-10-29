"""
Unit tests for string helper functions in BlackyAgent utils.
"""

import unittest
from utils.string_helpers import (
    reverse_string,
    is_palindrome,
    to_camel_case,
    to_snake_case,
    truncate,
)


class TestStringHelpers(unittest.TestCase):

    def test_reverse_string(self):
        self.assertEqual(reverse_string("hello"), "olleh")
        self.assertEqual(reverse_string(""), "")
        self.assertEqual(reverse_string("12345"), "54321")

    def test_is_palindrome(self):
        self.assertTrue(is_palindrome("Racecar"))
        self.assertTrue(is_palindrome("A man, a plan, a canal: Panama"))
        self.assertFalse(is_palindrome("Hello"))
        self.assertTrue(is_palindrome(""))

    def test_to_camel_case(self):
        self.assertEqual(to_camel_case("hello_world"), "helloWorld")
        self.assertEqual(to_camel_case("hello world"), "helloWorld")
        self.assertEqual(to_camel_case("single"), "single")
        self.assertEqual(to_camel_case(""), "")

    def test_to_snake_case(self):
        self.assertEqual(to_snake_case("helloWorld"), "hello_world")
        self.assertEqual(to_snake_case("HelloWorld"), "hello_world")
        self.assertEqual(to_snake_case("hello world"), "hello_world")

    def test_truncate(self):
        self.assertEqual(truncate("Short", 10), "Short")
        self.assertEqual(truncate("The quick brown fox", 10), "The quick...")


if __name__ == "__main__":
    unittest.main()
