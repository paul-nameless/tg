import unittest
from typing import Any
from unittest.mock import MagicMock

from tg.models import Model
from tg.update_handlers import handlers

BOB = 5
CHAT = -100


def result(update: dict[str, Any]) -> MagicMock:
    res = MagicMock()
    res.error = False
    res.update = update
    return res


def user(first_name: str = "", usernames: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": BOB,
        "first_name": first_name,
        "last_name": "",
        "usernames": {"active_usernames": usernames or []},
        "phone_number": "",
        "type": {"@type": "userTypeRegular"},
        "status": {"@type": "userStatusEmpty"},
    }


def model(user_obj: dict[str, Any]) -> Model:
    tg = MagicMock()
    tg.get_user.return_value = result(user_obj)
    tg.get_user_full_info.return_value = result(
        {"bio": {"@type": "formattedText", "text": "Hello there", "entities": []}}
    )
    tg.get_supergroup_full_info.return_value = result(
        {
            "member_count": 42,
            "description": "About",
            "invite_link": {
                "@type": "chatInviteLink",
                "invite_link": "https://t.me/+abc",
            },
        }
    )
    return Model(tg)


class ChatActionTest(unittest.TestCase):
    def test_typing_from_update_chat_action(self) -> None:
        controller = MagicMock()
        controller.model = model(user("Bob"))
        update = {
            "@type": "updateChatAction",
            "chat_id": CHAT,
            "sender_id": {"@type": "messageSenderUser", "user_id": BOB},
            "action": {"@type": "chatActionTyping"},
        }
        handlers["updateChatAction"](controller, update)
        self.assertEqual(controller.model.users.get_user_action(CHAT), (BOB, "typing"))

        cancel = {**update, "action": {"@type": "chatActionCancel"}}
        handlers["updateChatAction"](controller, cancel)
        self.assertEqual(controller.model.users.get_user_action(CHAT), (None, None))


class InfoTest(unittest.TestCase):
    def test_username_label_when_no_name(self) -> None:
        m = model(user(usernames=["bob"]))
        self.assertEqual(m.users.get_user_label(BOB), "@bob")

    def test_private_chat_info(self) -> None:
        m = model(user("Bob", ["bob"]))
        info = m.get_private_chat_info({"id": BOB, "title": "Bob"})
        self.assertEqual(info["Username"], "bob")
        self.assertEqual(info["Bio"], "Hello there")

    def test_supergroup_info(self) -> None:
        m = model(user("Bob"))
        chat = {"id": CHAT, "title": "Group", "type": {"supergroup_id": 1}}
        info = m.get_supergroup_info(chat)
        self.assertEqual(info["Group"], "42 members")
        self.assertEqual(info["Share link"], "https://t.me/+abc")
        self.assertEqual(m.get_channel_info(chat)["Group"], "42 subscribers")


if __name__ == "__main__":
    unittest.main()
