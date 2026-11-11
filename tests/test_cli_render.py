import json
import unittest

from tg.cli import render


class RenderTest(unittest.TestCase):
    def test_chat_line_labels_every_field(self) -> None:
        line = render.chat_line(
            {
                "chat_id": -100,
                "type": "group",
                "title": 'Team "A"',
                "username": "team",
                "unread": 3,
                "mentions": 1,
                "muted": True,
                "marked_unread": False,
                "shown": 2,
            }
        )
        self.assertEqual(
            line,
            'chat_id=-100 type=group title="Team \\"A\\"" username=@team'
            " unread=3 mentions=1 muted=yes shown=2",
        )

    def test_msg_line_escapes_newlines_and_puts_text_last(self) -> None:
        line = render.msg_line(
            {
                "msg_id": 5,
                "ts": 0,
                "from": "Bob",
                "reply_to": 4,
                "forwarded": False,
                "media": {"type": "photo", "size": "1.2MB"},
                "text": "a\nb",
            }
        )
        self.assertTrue(line.startswith("  msg_id=5 date="))
        self.assertIn('from="Bob" reply_to=4 media=photo size=1.2MB: a\\nb', line)

    def test_clip(self) -> None:
        self.assertEqual(render.clip("abcdef", 3), "abc…")
        self.assertEqual(render.clip("abcdef", 0), "abcdef")

    def test_to_text_caps_output(self) -> None:
        lines = ["x" * 1000] * 100
        out = render.to_text(lines).splitlines()
        self.assertEqual(out[-1], render.TRUNCATED)
        self.assertLess(len(out), 100)

    def test_to_json_converts_timestamps(self) -> None:
        data = json.loads(render.to_json({"messages": [{"msg_id": 1, "ts": 0}]}))
        self.assertEqual(
            data, {"messages": [{"msg_id": 1, "date": "1970-01-01T00:00:00Z"}]}
        )


if __name__ == "__main__":
    unittest.main()
