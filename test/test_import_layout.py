from __future__ import annotations

import unittest
from pathlib import Path

import utils


ROOT_DIR = Path(__file__).resolve().parents[1]


class ImportLayoutTests(unittest.TestCase):
    def test_project_utils_package_is_not_shadowed_by_test_helpers(self) -> None:
        self.assertEqual(
            Path(utils.__file__).resolve(),
            ROOT_DIR / "utils" / "__init__.py",
        )


if __name__ == "__main__":
    unittest.main()
