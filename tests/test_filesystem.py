"""
Unit tests for BlackyAgent filesystem tools.
"""

import unittest
import tempfile
import shutil
from pathlib import Path

from blacky.config import config
from blacky.tools.filesystem import (
    create_folder,
    write_file,
    read_file,
    edit_file,
    list_directory,
    delete_item,
)


class TestFilesystemTools(unittest.TestCase):

    def setUp(self):
        # Create a dedicated temporary directory for isolated testing
        self.test_dir = tempfile.mkdtemp(prefix="blacky_test_")
        self.orig_base = config.BASE_DIR
        config.BASE_DIR = Path(self.test_dir)

    def tearDown(self):
        config.BASE_DIR = self.orig_base
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_folder(self):
        res = create_folder("algorithms/searching")
        self.assertIn("successfully created", res)
        folder = Path(self.test_dir) / "algorithms" / "searching"
        self.assertTrue(folder.is_dir())

    def test_write_and_read_file(self):
        code_content = "def binary_search(arr, target):\n    return -1\n"
        file_path = "algorithms/binary_search.py"
        
        write_res = write_file(file_path, code_content)
        self.assertIn("Successfully wrote", write_res)

        target_file = Path(self.test_dir) / file_path
        self.assertTrue(target_file.is_file())

        read_res = read_file(file_path)
        self.assertIn("def binary_search", read_res)

    def test_edit_file(self):
        file_path = "test_script.py"
        write_file(file_path, "value = 10\nprint(value)")

        edit_res = edit_file(file_path, "value = 10", "value = 42")
        self.assertIn("Successfully updated", edit_res)

        updated_content = read_file(file_path)
        self.assertIn("value = 42", updated_content)

    def test_list_directory(self):
        create_folder("folder_a")
        write_file("file_b.txt", "hello")

        listing = list_directory(".")
        self.assertIn("folder_a", listing)
        self.assertIn("file_b.txt", listing)

    def test_delete_item(self):
        write_file("to_delete.txt", "bye")
        self.assertTrue((Path(self.test_dir) / "to_delete.txt").exists())

        del_res = delete_item("to_delete.txt")
        self.assertIn("Deleted file", del_res)
        self.assertFalse((Path(self.test_dir) / "to_delete.txt").exists())


if __name__ == "__main__":
    unittest.main()
