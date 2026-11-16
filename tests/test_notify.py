import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from tg.controllers import Controller
from tg.msg import MsgProxy
from tg.tdlib import is_muted

GROUPS = "notificationSettingsScopeGroupChats"
CHANNELS = "notificationSettingsScopeChannelChats"


def chat(
    chat_id: int, kind: dict[str, Any], mute_for: int = 0, default: bool = True
) -> dict[str, Any]:
    return {
        "id": chat_id,
        "title": f"Chat {chat_id}",
        "type": kind,
        "notification_settings": {
            "use_default_mute_for": default,
            "mute_for": mute_for,
        },
    }


CHANNEL = chat(
    -1, {"@type": "chatTypeSupergroup", "supergroup_id": 1, "is_channel": True}
)
GROUP = chat(-2, {"@type": "chatTypeBasicGroup", "basic_group_id": 2})


def muted_scopes(*scopes: str) -> Any:
    return lambda scope: scope in scopes


class IsMutedTest(unittest.TestCase):
    def test_own_setting_wins(self) -> None:
        muted = chat(-3, GROUP["type"], mute_for=100, default=False)
        unmuted = chat(-4, GROUP["type"], mute_for=0, default=False)
        self.assertTrue(is_muted(muted, muted_scopes()))
        self.assertFalse(is_muted(unmuted, muted_scopes(GROUPS)))

    def test_default_follows_scope(self) -> None:
        self.assertTrue(is_muted(GROUP, muted_scopes(GROUPS)))
        self.assertFalse(is_muted(GROUP, muted_scopes(CHANNELS)))
        self.assertTrue(is_muted(CHANNEL, muted_scopes(CHANNELS)))


def message(chat_id: int, sender: dict[str, Any]) -> MsgProxy:
    return MsgProxy(
        {
            "@type": "message",
            "id": 1,
            "chat_id": chat_id,
            "sender_id": sender,
            "content": {"@type": "messageText", "text": {"text": "hello"}},
        }
    )


def controller(scopes_muted: dict[str, bool]) -> Controller:
    ctrl = Controller.__new__(Controller)
    ctrl.model = MagicMock()
    ctrl.model.chats.chats = [CHANNEL, GROUP]
    ctrl.model.chats.is_muted = lambda c: is_muted(
        c, lambda scope: scopes_muted.get(scope, False)
    )
    ctrl.model.is_me.return_value = False
    ctrl.model.users.get_user_label.return_value = "Bob"
    return ctrl


class NotifyTest(unittest.TestCase):
    @patch("tg.controllers.notify")
    def test_channel_post_uses_chat_title(self, notify: MagicMock) -> None:
        sender = {"@type": "messageSenderChat", "chat_id": -1}
        controller({}).notify_for_message(-1, message(-1, sender))
        notify.assert_called_once_with("hello", title="Chat -1")

    @patch("tg.controllers.notify")
    def test_user_message_uses_user_label(self, notify: MagicMock) -> None:
        sender = {"@type": "messageSenderUser", "user_id": 5}
        controller({}).notify_for_message(-2, message(-2, sender))
        notify.assert_called_once_with("hello", title="Bob")

    @patch("tg.controllers.notify")
    def test_scope_muted_chat_is_silent(self, notify: MagicMock) -> None:
        sender = {"@type": "messageSenderUser", "user_id": 5}
        controller({GROUPS: True}).notify_for_message(-2, message(-2, sender))
        notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
