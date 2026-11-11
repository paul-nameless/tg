import curses
import unittest

from tg.colors import parse_style


class SelectedStyleTest(unittest.TestCase):
    def test_names_and_combinations(self) -> None:
        self.assertEqual(parse_style("reverse"), curses.A_REVERSE)
        self.assertEqual(parse_style("Bold"), curses.A_BOLD)
        self.assertEqual(
            parse_style("bold + underline"), curses.A_BOLD | curses.A_UNDERLINE
        )

    def test_unknown_falls_back_to_reverse(self) -> None:
        self.assertEqual(parse_style("blue"), curses.A_REVERSE)
        self.assertEqual(parse_style(""), curses.A_REVERSE)


if __name__ == "__main__":
    unittest.main()
