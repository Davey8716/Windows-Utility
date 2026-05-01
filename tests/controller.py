import sys
import unittest
from pathlib import Path


def main():
    tests_dir = Path(__file__).resolve().parent
    project_root = tests_dir.parent
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(tests_dir))
    suite = unittest.defaultTestLoader.discover(str(tests_dir), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2, buffer=True)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
