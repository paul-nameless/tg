import curses
import re
import unittest
from typing import Any
from unittest import mock

from tg import config
from tg.controllers import Controller, chat_handler, msg_handler
from tg.keymaps import RU, UK
from tg.utils import is_no, is_yes
from tg.views import SPECIAL_KEYS, View


class SpecialKeyTest(unittest.TestCase):
    def test_arrows_and_pages_map_to_key_names(self) -> None:
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_DOWN), "<Down>")
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_UP), "<Up>")
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_LEFT), "<Left>")
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_RIGHT), "<Right>")
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_NPAGE), "J")
        self.assertEqual(SPECIAL_KEYS.get(curses.KEY_PPAGE), "K")

    def test_other_special_keys_are_ignored(self) -> None:
        for key in (curses.KEY_HOME, curses.KEY_END, curses.KEY_DC, curses.KEY_IC):
            self.assertNotIn(key, SPECIAL_KEYS)

    def test_arrows_keep_their_pane_actions(self) -> None:
        self.assertEqual(msg_handler["<Down>"].__name__, "next_msg")
        self.assertEqual(msg_handler["<Up>"].__name__, "prev_msg")
        self.assertEqual(msg_handler["<Left>"].__name__, "back")
        self.assertNotIn("<Right>", msg_handler)
        self.assertEqual(chat_handler["<Down>"].__name__, "next_chat")
        self.assertEqual(chat_handler["<Up>"].__name__, "prev_chat")
        self.assertEqual(chat_handler["<Right>"].__name__, "handle_msgs")
        self.assertNotIn("<Left>", chat_handler)


def read_keys(*chars: Any) -> tuple[int, str]:
    view = View.__new__(View)
    stdscr = mock.Mock()
    stdscr.get_wch.side_effect = list(chars)
    view.stdscr = stdscr
    return view.get_keys()


class GetKeysTest(unittest.TestCase):
    def test_plain_and_control_keys(self) -> None:
        self.assertEqual(read_keys("j"), (1, "j"))
        self.assertEqual(read_keys("\x0e"), (1, "^N"))
        self.assertEqual(read_keys("\n"), (1, "^J"))
        self.assertEqual(read_keys("\x1b"), (1, "^["))
        self.assertEqual(read_keys(" "), (1, " "))
        self.assertEqual(read_keys("\x00"), (1, "^@"))
        self.assertEqual(read_keys("\x7f"), (1, "^?"))

    def test_repeat_factor_and_multichar(self) -> None:
        self.assertEqual(read_keys("1", "2", "j"), (12, "j"))
        self.assertEqual(read_keys("d", "d"), (1, "dd"))

    def test_special_keys(self) -> None:
        self.assertEqual(read_keys(curses.KEY_DOWN), (1, "<Down>"))
        self.assertEqual(read_keys(curses.KEY_HOME), (1, "UNKNOWN"))

    def test_no_input(self) -> None:
        self.assertEqual(read_keys(curses.error()), (1, "UNKNOWN"))

    def test_non_latin_without_aliases(self) -> None:
        with mock.patch.object(config, "KEY_ALIASES", {}):
            self.assertEqual(read_keys("о"), (1, "о"))

    def test_default_aliases_are_ru(self) -> None:
        self.assertEqual(config.KEY_ALIASES, RU)

    def test_aliases(self) -> None:
        with mock.patch.object(config, "KEY_ALIASES", RU):
            self.assertEqual(read_keys("о"), (1, "j"))
            self.assertEqual(read_keys("3", "л"), (3, "k"))
            self.assertEqual(read_keys("в", "в"), (1, "dd"))
            self.assertEqual(read_keys("Ш"), (1, "I"))
            self.assertEqual(read_keys("j"), (1, "j"))


class AnswerTest(unittest.TestCase):
    def test_answers_in_layout(self) -> None:
        with mock.patch.object(config, "KEY_ALIASES", RU):
            self.assertTrue(is_no("т"))
            self.assertFalse(is_yes("т"))
            self.assertTrue(is_yes("Н"))
            self.assertFalse(is_no("н"))
        with mock.patch.object(config, "KEY_ALIASES", {}):
            self.assertFalse(is_no("т"))
            self.assertTrue(is_yes("y"))
            self.assertTrue(is_no(""))
        with mock.patch.object(config, "KEY_ALIASES", {"n": "j", "y": "o"}):
            self.assertTrue(is_no("n"))
            self.assertTrue(is_yes("Y"))


class KeymapTest(unittest.TestCase):
    def test_layouts(self) -> None:
        self.assertEqual(RU["ш"], "i")
        self.assertEqual(RU["Ф"], "A")
        self.assertEqual(RU["х"], "[")
        self.assertEqual(UK["і"], "s")
        self.assertEqual(UK["ї"], "]")
        self.assertEqual(UK["є"], "'")
        self.assertEqual(len(RU), 64)
        self.assertEqual(len(UK), 64)


class HelpTest(unittest.TestCase):
    def test_one_line_per_action(self) -> None:
        lines = Controller.format_help(msg_handler).splitlines()
        names = [re.split(r"\s{2,}", line)[1] for line in lines]
        self.assertEqual(len(names), len(set(names)))
        rows = {re.split(r"\s{2,}", line)[1]: line for line in lines}
        self.assertTrue(rows["next_msg"].startswith("j, <Down>, ^N "))
        self.assertTrue(rows["toggle_select_msg_down"].startswith("<Space> "))
        self.assertTrue(rows["discard_selected_msgs"].startswith("^G, <Esc> "))

    def test_sorted_by_key(self) -> None:
        lines = Controller.format_help(chat_handler).splitlines()
        self.assertEqual(lines, sorted(lines))


if __name__ == "__main__":
    unittest.main()
