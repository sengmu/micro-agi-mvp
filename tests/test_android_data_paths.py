"""Portable data paths for a future embedded Android Python runtime."""

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class AndroidDataPathTests(unittest.TestCase):
    def test_embedded_database_uses_private_writable_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "private" / "data"
            with patch.dict(os.environ, {"MICRO_AGI_DATA_DIR": str(data_dir)}):
                spec = importlib.util.spec_from_file_location(
                    "micro_agi_db_path_test", ROOT / "db.py")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            self.assertEqual(Path(module.DB_PATH), data_dir / "micro_agi.db")
            self.assertTrue((data_dir / "micro_agi.db").is_file())
            with self.assertRaises(ValueError):
                module.resolve_db_path("relative/path")


if __name__ == "__main__":
    unittest.main()
