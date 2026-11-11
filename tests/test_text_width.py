import unittest

from tg.utils import string_len_dwc, truncate_to_len


class TextWidthTest(unittest.TestCase):
    def test_plain_and_wide(self) -> None:
        self.assertEqual(string_len_dwc("abc"), 3)
        self.assertEqual(string_len_dwc("日本"), 4)
        self.assertEqual(string_len_dwc("👍"), 2)

    def test_zero_width_parts(self) -> None:
        self.assertEqual(string_len_dwc("é"), 1)
        self.assertEqual(string_len_dwc("👍🏽"), 2)
        self.assertEqual(string_len_dwc("a‍b"), 2)
        self.assertEqual(string_len_dwc("❤️"), 1)

    def test_truncate_never_exceeds_width(self) -> None:
        self.assertEqual(truncate_to_len("ab日本", 3), "ab")
        self.assertEqual(truncate_to_len("ab日本", 4), "ab日")
        self.assertEqual(truncate_to_len("abc", 5), "abc")
        self.assertEqual(truncate_to_len("éx", 1), "é")


if __name__ == "__main__":
    unittest.main()
