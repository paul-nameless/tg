import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Union, Tuple

from telegram.client import Telegram

from tg.msg import MsgProxy

log = logging.getLogger(__name__)


class Model:
    def __init__(self, tg: Telegram) -> None:
        self.chats = ChatModel(tg)
        self.msgs = MsgModel(tg)
        self.users = UserModel(tg)
        self.current_chat = 0
        self.downloads: Dict[int, Tuple[int, int]] = {}

    def get_me(self):
        return self.users.get_me()

    def get_user(self, user_id):
        return self.users.get_user(user_id)

    def get_current_chat_msg_idx(self) -> Optional[int]:
        chat_id = self.chats.id_by_index(self.current_chat)
        if chat_id is None:
            return None
        return self.msgs.current_msgs[chat_id]

    def fetch_msgs(
        self,
        current_position: int = 0,
        page_size: int = 10,
        msgs_left_scroll_threshold: int = 10,
    ) -> List[Tuple[int, Dict[str, Any]]]:
        chat_id = self.chats.id_by_index(self.current_chat)
        if chat_id is None:
            return []
        msgs_left = page_size - 1 - current_position
        offset = max(msgs_left_scroll_threshold - msgs_left, 0)

        limit = offset + page_size
        return self.msgs.fetch_msgs(chat_id, offset=offset, limit=limit)

    def current_msg(self):
        chat_id = self.chats.id_by_index(self.current_chat)
        if chat_id is None:
            return {}
        current_msg = self.msgs.current_msgs[chat_id]
        log.info("current-msg: %s", current_msg)
        return self.msgs.msgs[chat_id][current_msg]

    def jump_bottom(self):
        chat_id = self.chats.id_by_index(self.current_chat)
        return self.msgs.jump_bottom(chat_id)

    def next_chat(self, step: int = 1) -> bool:
        new_idx = self.current_chat + step
        if new_idx < len(self.chats.chats):
            self.current_chat = new_idx
            return True
        return False

    def prev_chat(self, step: int = 1) -> bool:
        if self.current_chat == 0:
            return False
        self.current_chat = max(0, self.current_chat - step)
        return True

    def first_chat(self):
        if self.current_chat != 0:
            self.current_chat = 0
            return True
        return False

    def next_msg(self, step: int = 1) -> bool:
        chat_id = self.chats.id_by_index(self.current_chat)
        if not chat_id:
            return False
        return self.msgs.next_msg(chat_id, step)

    def prev_msg(self, step: int = 1) -> bool:
        chat_id = self.chats.id_by_index(self.current_chat)
        if not chat_id:
            return False
        return self.msgs.prev_msg(chat_id, step)

    def get_chats(
        self, offset: int = 0, limit: int = 10
    ) -> List[Dict[str, Any]]:
        return self.chats.fetch_chats(offset=offset, limit=limit)

    def send_message(self, text: str) -> bool:
        chat_id = self.chats.id_by_index(self.current_chat)
        if chat_id is None:
            return False
        self.msgs.send_message(chat_id, text)
        return True

    def delete_msg(self) -> bool:
        chat_id = self.chats.id_by_index(self.current_chat)
        if chat_id:
            return self.msgs.delete_msg(chat_id)
        return False


class ChatModel:
    def __init__(self, tg: Telegram) -> None:
        self.tg = tg
        self.chats: List[Dict[str, Any]] = []
        self.chat_ids: List[int] = []

    def id_by_index(self, index: int) -> Optional[int]:
        if index >= len(self.chats):
            return None
        return self.chats[index]["id"]

    def fetch_chats(
        self, offset: int = 0, limit: int = 10
    ) -> List[Dict[str, Any]]:
        if offset + limit < len(self.chats):
            # return data from cache
            return self.chats[offset:limit]

        previous_chats_num = len(self.chat_ids)

        self.fetch_chat_ids(
            offset=len(self.chats), limit=len(self.chats) + limit
        )
        if len(self.chat_ids) == previous_chats_num:
            return self.chats[offset:limit]

        for chat_id in self.chat_ids:
            chat = self.fetch_chat(chat_id)
            self.chats.append(chat)

        return self.chats[offset:limit]

    def fetch_chat_ids(self, offset: int = 0, limit: int = 10) -> List[int]:
        if len(self.chats):
            result = self.tg.get_chats(
                offset_chat_id=self.chats[-1]["id"], limit=limit
            )
        else:
            result = self.tg.get_chats(
                offset_order=2 ** 63 - 1, offset_chat_id=offset, limit=limit
            )

        result.wait()
        if result.error:
            log.error(f"get chat ids error: {result.error_info}")
            return []

        for chat_id in result.update["chat_ids"]:
            self.chat_ids.append(chat_id)

        # TODO:
        # if len(self.chat_ids) >= offset + limit:
        #     break

        return self.chat_ids[offset:limit]

    def fetch_chat(self, chat_id: int) -> Dict[str, Any]:
        result = self.tg.get_chat(chat_id)
        result.wait()

        if result.error:
            log.error(f"get chat error: {result.error_info}")
            return {}
        return result.update

    def update_last_message(self, chat_id, message):
        for i, c in enumerate(self.chats):
            if c["id"] != chat_id:
                continue
            self.chats[i]["last_message"] = message
            self.chats = sorted(
                self.chats,
                key=lambda it: it["last_message"]["date"],
                reverse=True,
            )

            log.info("Updated last message")
            return True
        else:
            log.error(f"Can't find chat {chat_id} in existing chats")
            return False


class MsgModel:
    def __init__(self, tg: Telegram) -> None:
        self.tg = tg
        self.msgs: Dict[int, List[Dict]] = defaultdict(list)
        self.current_msgs: Dict[int, int] = defaultdict(int)
        self.msg_ids: Dict[int, Set[int]] = defaultdict(set)

    def next_msg(self, chat_id: int, step: int = 1) -> bool:
        current_msg = self.current_msgs[chat_id]
        if current_msg == 0:
            return False
        self.current_msgs[chat_id] = max(0, current_msg - step)
        return True

    def jump_bottom(self, chat_id):
        if self.current_msgs[chat_id] == 0:
            return False
        self.current_msgs[chat_id] = 0
        return True

    def prev_msg(self, chat_id: int, step: int = 1) -> bool:
        new_idx = self.current_msgs[chat_id] + step
        if new_idx < len(self.msgs[chat_id]):
            self.current_msgs[chat_id] = new_idx
            return True

        return False

    def remove_message(self, chat_id, msg_id):
        msg_set = self.msg_ids[chat_id]
        if msg_id not in msg_set:
            return False
        log.info(f"removing msg {msg_id=}")
        # FIXME: potential bottleneck, replace with constan time operation
        self.msgs[chat_id] = [
            m for m in self.msgs[chat_id] if m["id"] != msg_id
        ]
        msg_set.remove(msg_id)
        return True

    def add_message(self, chat_id: int, message: Dict[str, Any]) -> bool:
        msg_id = message["id"]
        msg_set = self.msg_ids[chat_id]
        if msg_id in msg_set:
            log.warning(
                f"message {msg_id} was added earlier. probably, inaccurate "
                "usage of the tdlib lead to unnecessary requests"
            )
            return False
        log.info(f"adding {msg_id=} {message}")
        self.msgs[chat_id].append(message)
        msg_set.add(msg_id)
        self.msgs[chat_id] = sorted(
            self.msgs[chat_id], key=lambda d: d["id"], reverse=True
        )
        return True

    def add_messages(self, chat_id: int, messages: Any) -> bool:
        return any([self.add_message(chat_id, msg) for msg in messages])

    def _fetch_msgs_until_limit(
        self, chat_id: int, offset: int = 0, limit: int = 10
    ) -> List[Dict[str, Any]]:
        if len(self.msgs[chat_id]):
            result = self.tg.get_chat_history(
                chat_id,
                from_message_id=self.msgs[chat_id][-1]["id"],
                limit=len(self.msgs[chat_id]) + limit,
            )
        else:
            result = self.tg.get_chat_history(
                chat_id,
                offset=len(self.msgs[chat_id]),
                limit=len(self.msgs[chat_id]) + limit,
            )
        result.wait()
        messages = result.update["messages"]
        if not messages:
            return messages

        # tdlib could doesn't guarantee number of messages, so we need to
        # send another request on demand
        # see https://github.com/tdlib/td/issues/168
        for i in range(3):
            if len(messages) >= limit + offset:
                break
            result = self.tg.get_chat_history(
                chat_id,
                from_message_id=messages[-1]["id"],
                limit=len(self.msgs[chat_id]) + limit,
            )
            result.wait()
            messages += result.update["messages"]

        return messages

    def fetch_msgs(
        self, chat_id: int, offset: int = 0, limit: int = 10
    ) -> List[Tuple[int, Dict[str, Any]]]:
        if offset + limit > len(self.msgs[chat_id]):
            messages = self._fetch_msgs_until_limit(
                chat_id, offset, offset + limit
            )
            self.add_messages(chat_id, messages)

        return [
            (i, self.msgs[chat_id][i])
            for i in range(offset, offset + limit)
            if i < len(self.msgs[chat_id])
        ]

    def send_message(self, chat_id: int, text: str) -> None:
        log.info("Sending msg")
        result = self.tg.send_message(chat_id=chat_id, text=text)

        result.wait()
        if result.error:
            log.info(f"send message error: {result.error_info}")
        else:
            log.info(f"message has been sent: {result.update}")

    def delete_msg(self, chat_id: int) -> bool:
        if chat_id is None:
            return False
        selected_msg = self.current_msgs[chat_id]
        msg_item = self.msgs[chat_id].pop(selected_msg)
        self.current_msgs[chat_id] = min(
            selected_msg, len(self.msgs[chat_id]) - 1
        )
        log.info(f"Deleting msg from the chat {chat_id}: {msg_item}")
        message_ids = [msg_item["id"]]
        r = self.tg.delete_messages(chat_id, message_ids, revoke=True)
        r.wait()
        return True


class UserModel:
    def __init__(self, tg: Telegram) -> None:
        self.tg = tg
        self.me = None
        self.users: Dict[int, Dict] = {}

    def get_me(self):
        if self.me:
            return self.me
        result = self.tg.get_me()
        result.wait()
        if result.error:
            log.error(f"get chat ids error: {result.error_info}")
            return {}
        self.me = result.update
        return self.me

    def get_user(self, user_id: int) -> Dict[str, Any]:
        if user_id in self.users:
            return self.users[user_id]
        result = self.tg.call_method("getUser", {"user_id": user_id})
        result.wait()
        if result.error:
            log.error(f"get chat ids error: {result.error_info}")
            return {}
        self.users[user_id] = result.update
        return result.update
