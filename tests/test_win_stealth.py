import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.win_stealth import WinStealthController


class WinStealthTest(unittest.TestCase):
    def test_idle_seconds(self):
        idle = WinStealthController.get_idle_seconds()
        self.assertIsInstance(idle, float)
        self.assertGreaterEqual(idle, 0.0)
        self.assertLess(idle, 30 * 24 * 3600)

    def test_foreground_process_pid(self):
        pid = WinStealthController.get_foreground_process_pid()
        self.assertIsInstance(pid, int)
        self.assertGreaterEqual(pid, 0)

    def test_cursor_pos(self):
        pos = WinStealthController.get_cursor_pos()
        self.assertIsNotNone(pos)
        self.assertEqual(len(pos), 2)
        self.assertIsInstance(pos[0], int)
        self.assertIsInstance(pos[1], int)


if __name__ == "__main__":
    unittest.main()
