import logging
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from tg.msg import MsgProxy
from tg.tdlib import ChatAction, Tdlib, UserStatus
from tg.utils import copy_to_clipboard, pretty_ts

log = logging.getLogger(__name__)


class Model:
    def __init__(self, tg: Tdlib) -> None:
        self.tg = tg
        self.chats = ChatModel(tg)
        self.msgs = MsgModel(tg)
        self.users = UserModel(tg)
        self.current_chat = 0
        self.downloads: Dict[int, Tuple[int, int]] = {}
        self.selected: Dict[int, List[int]] = defaultdict(list)
        self.copied_msgs: Tuple[int, List[int]] = (0, [])

    def get_me(self) -> Dict[str, Any]:
        return self.users.get_me()

    def is_me(self, user_id: int) -> bool:
        return self.get_me()["id"] == user_id

    def get_user(self, user_id: int) -> Dict:
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

    def jump_bottom(self) -> bool:
        if chat_id := self.chats.id_by_index(self.current_chat):
            return self.msgs.jump_bottom(chat_id)
        return False

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

    def first_chat(self) -> bool:
        if self.current_chat != 0:
            self.current_chat = 0
            return True
        return False

    def view_current_msg(self) -> None:
        msg = MsgProxy(self.current_msg)
        msg_id = msg["id"]
        if chat_id := self.chats.id_by_index(self.current_chat):
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
    ) -> List[Dict[str, Any]]:
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

    def copy_msgs_text(self) -> bool:
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
            if msg.file_id and msg.local_path:
                buffer.append(msg.local_path)
            elif msg.is_text:
                buffer.append(msg.text_content)
        copy_to_clipboard("\n".join(buffer))
        return True


class ChatModel:
    def __init__(self, tg: Tdlib) -> None:
        self.tg = tg
        self.chats: List[Dict[str, Any]] = []
        self.chat_ids: List[int] = []
        self.have_full_chat_list = False
        self.title: str = "Chats"

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

    def _load_next_chats(self) -> None:
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
    def __init__(self, tg: Tdlib) -> None:
        self.tg = tg
        self.msgs: Dict[int, List[Dict]] = defaultdict(list)
        self.current_msgs: Dict[int, int] = defaultdict(int)
        self.not_found: Set[int] = set()
        self.msg_ids: Dict[int, Set[int]] = defaultdict(set)

    def next_msg(self, chat_id: int, step: int = 1) -> bool:
        current_msg = self.current_msgs[chat_id]
        if current_msg == 0:
            return False
        self.current_msgs[chat_id] = max(0, current_msg - step)
        return True

    def jump_bottom(self, chat_id: int) -> bool:
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
        if msg_id in self.not_found:
            return None
        msg_set = self.msg_ids[chat_id]
        if msg_id not in msg_set:
            # we are not storing any out of ordres old msgs
            # just fetching then on demand
            result = self.tg.get_message(chat_id, msg_id)
            result.wait()
            if result.error:
                self.not_found.add(msg_id)
                return None
            return result.update
        return next(iter(m for m in self.msgs[chat_id] if m["id"] == msg_id))

    def remove_messages(self, chat_id: int, msg_ids: List[int]) -> None:
        log.info(f"removing msgs {msg_ids=}")
        # FIXME: potential bottleneck, replace with constan time operation
        self.msgs[chat_id] = [
            m for m in self.msgs[chat_id] if m["id"] not in msg_ids
        ]
        msg_set = self.msg_ids[chat_id]
        for msg_id in msg_ids:
            msg_set.discard(msg_id)

    def update_msg_content_opened(self, chat_id: int, msg_id: int) -> None:
        for message in self.msgs[chat_id]:
            if message["id"] != msg_id:
                continue
            msg = MsgProxy(message)
            if msg.content_type == "voice":
                msg.is_listened = True
            elif msg.content_type == "recording":
                msg.is_viewed = True
            # TODO: start the TTL timer for self-destructing messages
            # that is the last case to implement
            # https://core.telegram.org/tdlib/docs/classtd_1_1td__api_1_1update_message_content_opened.html
            return

    def update_msg(
        self, chat_id: int, msg_id: int, **fields: Dict[str, Any]
    ) -> bool:
        msg = None
        for message in self.msgs[chat_id]:
            if message["id"] == msg_id:
                msg = message
                break
        if not msg:
            return False
        msg.update(fields)
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
            messages = self._fetch_msgs_until_limit(
                chat_id, offset, offset + limit
            )
            for msg in messages:
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

    types = {
        "userTypeUnknown": "unknown",
        "userTypeBot": "bot",
        "userTypeDeleted": "deleted",
        "userTypeRegular": "regular",
    }

    def __init__(self, tg: Tdlib) -> None:
        self.tg = tg
        self.me: Dict[str, Any] = {}
        self.users: Dict[int, Dict] = {}
        self.groups: Dict[int, Dict] = {}
        self.supergroups: Dict[int, Dict] = {}
        self.actions: Dict[int, Dict] = {}
        self.not_found: Set[int] = set()

    def get_me(self) -> Dict[str, Any]:
        if self.me:
            return self.me
        result = self.tg.get_me()
        result.wait()
        if result.error:
            log.error(f"get myself error: {result.error_info}")
            return {}
        self.me = result.update
        return self.me

    def get_action(self, chat_id: int) -> Optional[str]:
        action = self.actions.get(chat_id)
        if action is None:
            return None
        action_type = action["action"]["@type"]
        try:
            return ChatAction[action_type].value + "..."
        except KeyError:
            log.error(f"ChatAction type {action_type} not implemented")
        return None

    def set_status(self, user_id: int, status: Dict[str, Any]) -> None:
        if user_id not in self.users:
            self.get_user(user_id)
        self.users[user_id]["status"] = status

    def get_status(self, user_id: int) -> str:
        if user_id not in self.users:
            return ""
        user_status = self.users[user_id]["status"]

        try:
            status = UserStatus[user_status["@type"]]
        except KeyError:
            log.error(f"UserStatus type {user_status} not implemented")
            return ""

        if status == UserStatus.userStatusEmpty:
            return ""
        elif status == UserStatus.userStatusOnline:
            expires = user_status["expires"]
            if expires < time.time():
                return ""
            return status.value
        elif status == UserStatus.userStatusOffline:
            was_online = user_status["was_online"]
            ago = pretty_ts(was_online)
            return f"last seen {ago}"
        return f"last seen {status.value}"

    def is_online(self, user_id: int) -> bool:
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

    def get_group_info(self, group_id: int) -> Optional[Dict[str, Any]]:
        if group_id in self.groups:
            return self.groups[group_id]
        self.tg.get_basic_group(group_id)
        return None

    def get_supergroup_info(
        self, supergroup_id: int
    ) -> Optional[Dict[str, Any]]:
        if supergroup_id in self.supergroups:
            return self.supergroups[supergroup_id]
        self.tg.get_supergroup(supergroup_id)
        return None
