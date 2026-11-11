import curses
import unittest

from tg.views import SPECIAL_KEYS


class SpecialKeyTest(unittest.TestCase):
    def test_arrows_and_pages_map_to_vi_keys(self) -> None:
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_DOWN), "^B")
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_UP), "^C")
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_LEFT), "^D")
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_RIGHT), "^E")
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_NPAGE), "J")
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_PPAGE), "K")

    def test_other_special_keys_are_ignored(self) -> None:
        for key in (curses.KEY_HOME, curses.KEY_END, curses.KEY_DC, curses.KEY_IC):
            self.assertNotIn(key, SPECIAL_KEYS)


if __name__ == "__main__":
    unittest.main()
