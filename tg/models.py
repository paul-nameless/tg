import logging
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from tg.msg import MsgProxy
from tg.tdlib import Tdlib
from tg.utils import copy_to_clipboard

log = logging.getLogger(__name__)


class Model:
    def __init__(self, tg: Tdlib):
        self.tg = tg
        self.chats = ChatModel(tg)
        self.msgs = MsgModel(tg)
        self.users = UserModel(tg)
        self.current_chat = 0
        self.downloads: Dict[int, Tuple[int, int]] = {}
        self.selected: Dict[int, List[int]] = defaultdict(list)
        self.copied_msgs: Tuple[int, List[int]] = (0, [])

    def get_me(self):
        return self.users.get_me()

    def is_me(self, user_id: int) -> bool:
        return self.get_me()["id"] == user_id

    def get_user(self, user_id):
        return self.users.get_user(user_id)

    @property
    def current_chat_id(self) -> Optional[int]:
        return self.chats.id_by_index(self.current_chat)

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

    @property
    def current_msg(self) -> Dict[str, Any]:
        chat_id = self.chats.id_by_index(self.current_chat)
        if chat_id is None:
            return {}
        current_msg = self.msgs.current_msgs[chat_id]
        log.info("current-msg: %s", current_msg)
        return self.msgs.msgs[chat_id][current_msg]

    @property
    def current_msg_id(self) -> int:
        return self.current_msg["id"]

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

    def view_current_msg(self):
        chat_id = self.chats.id_by_index(self.current_chat)
        msg = MsgProxy(self.current_msg)
        msg_id = msg["id"]
        self.tg.view_messages(chat_id, [msg_id])

    def next_msg(self, step: int = 1) -> bool:
        chat_id = self.chats.id_by_index(self.current_chat)
        if not chat_id:
            return False
        is_next = self.msgs.next_msg(chat_id, step)
        if is_next:
            self.view_current_msg()
        return is_next

    def prev_msg(self, step: int = 1) -> bool:
        chat_id = self.chats.id_by_index(self.current_chat)
        if not chat_id:
            return False
        is_prev = self.msgs.prev_msg(chat_id, step)
        if is_prev:
            self.view_current_msg()
        return is_prev

    def get_chats(
        self,
        current_position: int = 0,
        page_size: int = 10,
        msgs_left_scroll_threshold: int = 10,
    ):
        chats_left = page_size - current_position
        offset = max(msgs_left_scroll_threshold - chats_left, 0)
        limit = offset + page_size
        return self.chats.fetch_chats(offset=offset, limit=limit)

    def send_message(self, text: str) -> bool:
        chat_id = self.chats.id_by_index(self.current_chat)
        if chat_id is None:
            return False
        self.msgs.send_message(chat_id, text)
        return True

    def edit_message(self, text: str) -> bool:
        if chat_id := self.chats.id_by_index(self.current_chat):
            return self.msgs.edit_message(chat_id, self.current_msg_id, text)
        return False

    def can_be_deleted(self, chat_id: int, msg: Dict[str, Any]) -> bool:
        if chat_id == msg["sender_user_id"]:
            return msg["can_be_deleted_only_for_self"]
        return msg["can_be_deleted_for_all_users"]

    def delete_msgs(self) -> bool:
        chat_id = self.chats.id_by_index(self.current_chat)
        if not chat_id:
            return False
        msg_ids = self.selected[chat_id]
        if msg_ids:
            message_ids = msg_ids
            for msg_id in message_ids:
                msg = self.msgs.get_message(chat_id, msg_id)
                if not msg or not self.can_be_deleted(chat_id, msg):
                    return False
        else:
            selected_msg = self.msgs.current_msgs[chat_id]
            msg = self.msgs.msgs[chat_id][selected_msg]
            if not self.can_be_deleted(chat_id, msg):
                return False
            message_ids = [msg["id"]]

        log.info(f"Deleting msg from the chat {chat_id}: {message_ids}")
        self.tg.delete_messages(chat_id, message_ids, revoke=True)
        return True

    def forward_msgs(self) -> bool:
        chat_id = self.chats.id_by_index(self.current_chat)
        if not chat_id:
            return False
        from_chat_id, msg_ids = self.copied_msgs
        if not msg_ids:
            return False
        for msg_id in msg_ids:
            msg = self.msgs.get_message(from_chat_id, msg_id)
            if not msg or not msg["can_be_forwarded"]:
                return False

        self.tg.forward_messages(chat_id, from_chat_id, msg_ids)
        self.copied_msgs = (0, [])
        return True

    def copy_msgs_text(self):
        """Copies current msg text or path to file if it's file"""
        buffer = []

        from_chat_id, msg_ids = self.copied_msgs
        if not msg_ids:
            return False
        for msg_id in msg_ids:
            _msg = self.msgs.get_message(from_chat_id, msg_id)
            if not _msg:
                return False
            msg = MsgProxy(_msg)
            if msg.file_id:
                buffer.append(msg.local_path)
            elif msg.is_text:
                buffer.append(msg.text_content)
        copy_to_clipboard("\n".join(buffer))


class ChatModel:
    def __init__(self, tg: Tdlib):
        self.tg = tg
        self.chats: List[Dict[str, Any]] = []
        self.chat_ids: List[int] = []
        self.have_full_chat_list = False

    def id_by_index(self, index: int) -> Optional[int]:
        if index >= len(self.chats):
            return None
        return self.chats[index]["id"]

    def fetch_chats(
        self, offset: int = 0, limit: int = 10
    ) -> List[Dict[str, Any]]:
        if offset + limit > len(self.chats):
            self._load_next_chats()

        return self.chats[offset:limit]

    def _load_next_chats(self):
        """
        based on
        https://github.com/tdlib/td/issues/56#issuecomment-364221408
        """
        if self.have_full_chat_list:
            return None
        offset_order = 2 ** 63 - 1
        offset_chat_id = 0
        if len(self.chats):
            offset_chat_id = self.chats[-1]["id"]
            offset_order = self.chats[-1]["order"]
        result = self.tg.get_chats(
            offset_chat_id=offset_chat_id, offset_order=offset_order
        )

        result.wait()
        if result.error:
            log.error(f"get chat ids error: {result.error_info}")
            return None

        chats = result.update["chat_ids"]
        if not chats:
            self.have_full_chat_list = True
            return chats

        for chat_id in chats:
            # TODO: fix this, we shouldn't have any duplicates
            if chat_id not in self.chat_ids:
                self.chat_ids.append(chat_id)
                chat = self.fetch_chat(chat_id)
                self.chats.append(chat)

    def fetch_chat(self, chat_id: int) -> Dict[str, Any]:
        result = self.tg.get_chat(chat_id)
        result.wait()

        if result.error:
            log.error(f"get chat error: {result.error_info}")
            return {}
        return result.update

    def update_chat(self, chat_id: int, **updates: Dict[str, Any]) -> bool:
        for i, c in enumerate(self.chats):
            if c["id"] != chat_id:
                continue
            self.chats[i].update(updates)
            self.chats = sorted(
                self.chats,
                # recommended chat order, for more info see
                # https://core.telegram.org/tdlib/getting-started#getting-the-lists-of-chats
                key=lambda it: (it["order"], it["id"]),
                reverse=True,
            )
            log.info(f"Updated chat with keys {list(updates)}")
            return True
        else:
            log.warning(f"Can't find chat {chat_id} in existing chats")
            return False


class MsgModel:
    def __init__(self, tg: Tdlib):
        self.tg = tg
        self.msgs: Dict[int, List[Dict]] = defaultdict(list)
        self.current_msgs: Dict[int, int] = defaultdict(int)
        self.not_found: Set[int] = set()
        self.msg_idx: Dict[int, Dict[int, int]] = defaultdict(dict)
        self.lock = threading.Lock()

    def next_msg(self, chat_id: int, step: int = 1) -> bool:
        current_msg = self.current_msgs[chat_id]
        if current_msg == 0:
            return False
        self.current_msgs[chat_id] = max(0, current_msg - step)
        return True

    def jump_bottom(self, chat_id: int):
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

    def get_message(self, chat_id: int, msg_id: int) -> Optional[Dict]:
        with self.lock:
            if index := self.msg_idx[chat_id].get(msg_id):
                return self.msgs[chat_id][index]
        # we are not storing any out of ordres old msgs
        # just fetching them on demand
        result = self.tg.get_message(chat_id, msg_id)
        result.wait()
        if result.error:
            self.not_found.add(msg_id)
            return None
        return result.update

    def remove_messages(self, chat_id: int, msg_idx: List[int]):
        with self.lock:
            log.info(f"removing msg {msg_idx=}")
            self.msgs[chat_id] = [
                m for m in self.msgs[chat_id] if m["id"] not in msg_idx
            ]
            self.msg_idx[chat_id] = {
                msg["id"]: i for i, msg in enumerate(self.msgs[chat_id])
            }

    def add_message(self, chat_id: int, msg: Dict[str, Any]):
        with self.lock:
            log.info(f"adding {msg=}")
            self.msgs[chat_id].append(msg)
            self.msgs[chat_id] = sorted(
                self.msgs[chat_id], key=lambda d: d["id"], reverse=True,
            )
            self.msg_idx[chat_id] = {
                msg["id"]: i for i, msg in enumerate(self.msgs[chat_id])
            }

    def update_msg_content_opened(self, chat_id: int, msg_id: int):
        with self.lock:
            index = self.msg_idx[chat_id][msg_id]
            msg = MsgProxy(self.msgs[chat_id][index])
            if msg.content_type == "voice":
                msg.is_listened = True
            elif msg.content_type == "recording":
                msg.is_viewed = True
            # TODO: start the TTL timer for self-destructing messages
            # that is the last case to implement
            # https://core.telegram.org/tdlib/docs/classtd_1_1td__api_1_1update_message_content_opened.html

    def update_msg(self, chat_id: int, msg_id: int, **fields: Dict[str, Any]):
        with self.lock:
            index = self.msg_idx[chat_id][msg_id]
            msg = self.msgs[chat_id][index]
            msg.update(fields)

    def _fetch_msgs_until_limit(
        self, chat_id: int, offset: int = 0, limit: int = 10
    ) -> List[Dict[str, Any]]:
        if self.msgs[chat_id]:
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
            msgs = self._fetch_msgs_until_limit(
                chat_id, offset, offset + limit
            )
            for msg in msgs:
                self.add_message(chat_id, msg)

        return [
            (i, self.msgs[chat_id][i])
            for i in range(offset, offset + limit)
            if i < len(self.msgs[chat_id])
        ]

    def edit_message(self, chat_id: int, message_id: int, text: str) -> bool:
        log.info("Editing msg")
        result = self.tg.edit_message_text(chat_id, message_id, text)

        result.wait()
        if result.error:
            log.info(f"send message error: {result.error_info}")
            return False
        else:
            log.info(f"message has been sent: {result.update}")
            return True

    def send_message(self, chat_id: int, text: str) -> None:
        log.info("Sending msg")
        result = self.tg.send_message(chat_id=chat_id, text=text)

        result.wait()
        if result.error:
            log.info(f"send message error: {result.error_info}")
        else:
            log.info(f"message has been sent: {result.update}")


class UserModel:

    statuses = {
        "userStatusEmpty": "",
        "userStatusOnline": "online",
        "userStatusOffline": "offline",
        "userStatusRecently": "recently",
        "userStatusLastWeek": "last week",
        "userStatusLastMonth": "last month",
    }

    types = {
        "userTypeUnknown": "unknown",
        "userTypeBot": "bot",
        "userTypeDeleted": "deleted",
        "userTypeRegular": "regular",
    }

    def __init__(self, tg: Tdlib) -> None:
        self.tg = tg
        self.me = None
        self.users: Dict[int, Dict] = {}
        self.not_found: Set[int] = set()

    def get_me(self):
        if self.me:
            return self.me
        result = self.tg.get_me()
        result.wait()
        if result.error:
            log.error(f"get myself error: {result.error_info}")
            return {}
        self.me = result.update
        return self.me

    def set_status(self, user_id: int, status: Dict[str, Any]):
        if user_id not in self.users:
            self.get_user(user_id)
        self.users[user_id]["status"] = status

    def is_online(self, user_id: int):
        user = self.get_user(user_id)
        if (
            user
            and user["type"]["@type"] != "userTypeBot"
            and user["status"]["@type"] == "userStatusOnline"
            and user["status"]["expires"] > time.time()
        ):
            return True
        return False

    def get_user(self, user_id: int) -> Dict[str, Any]:
        if user_id in self.not_found:
            return {}
        if user_id in self.users:
            return self.users[user_id]
        result = self.tg.call_method("getUser", {"user_id": user_id})
        result.wait()
        if result.error:
            log.warning(f"get user error: {result.error_info}")
            self.not_found.add(user_id)
            return {}
        self.users[user_id] = result.update
        return result.update
