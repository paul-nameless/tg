import unittest
from typing import Any, Dict, List

from tg.models import MsgModel


def msg(msg_id: int) -> Dict[str, Any]:
    return {"id": msg_id}


class SelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.model = MsgModel(None)  # type: ignore[arg-type]
        for msg_id in (1, 2, 3, 4):
            self.model.add_message(10, msg(msg_id))

    def selected(self) -> int:
        ids: List[int] = self.model.msg_ids[10]
        return ids[self.model.current_msgs[10]]

    def test_new_message_keeps_selection(self) -> None:
        self.model.current_msgs[10] = 2
        self.assertEqual(self.selected(), 2)
        self.model.add_message(10, msg(5))
        self.assertEqual(self.selected(), 2)

    def test_bottom_follows_new_messages(self) -> None:
        self.model.add_message(10, msg(5))
        self.assertEqual(self.selected(), 5)

    def test_older_message_keeps_selection(self) -> None:
        self.model.current_msgs[10] = 1
        self.model.add_message(10, msg(0))
        self.assertEqual(self.selected(), 3)

    def test_removing_newer_message_keeps_selection(self) -> None:
        self.model.current_msgs[10] = 2
        self.model.remove_messages(10, [4])
        self.assertEqual(self.selected(), 2)

    def test_removing_selected_message_stays_in_range(self) -> None:
        self.model.current_msgs[10] = 3
        self.model.remove_messages(10, [1])
        self.assertEqual(self.model.current_msgs[10], 2)


if __name__ == "__main__":
    unittest.main()
