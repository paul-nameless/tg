import curses
import unittest

from tg.views import StatusView

edit = StatusView._edit_key


class EditKeyTest(unittest.TestCase):
    def test_cursor_moves_within_bounds(self) -> None:
        self.assertEqual(edit(curses.KEY_LEFT, "abc", 0), ("abc", 0))
        self.assertEqual(edit(curses.KEY_LEFT, "abc", 2), ("abc", 1))
        self.assertEqual(edit(curses.KEY_RIGHT, "abc", 3), ("abc", 3))
        self.assertEqual(edit(curses.KEY_HOME, "abc", 2), ("abc", 0))
        self.assertEqual(edit(curses.KEY_END, "abc", 0), ("abc", 3))

    def test_deletes_around_cursor(self) -> None:
        self.assertEqual(edit(curses.KEY_BACKSPACE, "abc", 2), ("ac", 1))
        self.assertEqual(edit(curses.KEY_BACKSPACE, "abc", 0), ("abc", 0))
        self.assertEqual(edit(curses.KEY_DC, "abc", 1), ("ac", 1))
        self.assertEqual(edit(curses.KEY_DC, "abc", 3), ("abc", 3))

    def test_other_keys_keep_text(self) -> None:
        self.assertEqual(edit(curses.KEY_PPAGE, "abc", 1), ("abc", 1))
        self.assertEqual(edit(curses.KEY_F1, "abc", 1), ("abc", 1))


if __name__ == "__main__":
    unittest.main()
