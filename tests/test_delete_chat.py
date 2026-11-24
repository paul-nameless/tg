import unittest
from unittest import mock

from tg.controllers import Controller
from tg.tdlib import ChatType


def delete_private_chat(*answers: str | None) -> bool:
    ctrl = Controller.__new__(Controller)
    ctrl.model = mock.Mock()
    ctrl.model.current_chat = 0
    ctrl.model.chats.chats = [
        {
            "id": 1,
            "type": {"@type": ChatType.chatTypePrivate.name},
            "can_be_deleted_for_all_users": True,
        }
    ]
    ctrl.view = mock.Mock()
    ctrl.view.status.get_input.side_effect = list(answers)
    ctrl.tg = mock.Mock()
    ctrl.queue = mock.Mock()
    ctrl.delete_chat()
    return bool(ctrl.tg.delete_chat_history.call_args.kwargs["revoke"])


class DeleteChatRevokeTest(unittest.TestCase):
    def test_default_and_no_keep_messages_for_others(self) -> None:
        self.assertFalse(delete_private_chat("y", ""))
        self.assertFalse(delete_private_chat("y", "n"))
        self.assertFalse(delete_private_chat("y", " "))

    def test_yes_deletes_for_all(self) -> None:
        self.assertTrue(delete_private_chat("y", "y"))
        self.assertTrue(delete_private_chat("y", "Y"))


if __name__ == "__main__":
    unittest.main()
