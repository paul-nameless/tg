import logging
import os
import threading
from datetime import datetime
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional

from telegram.client import Telegram

from tg import config
from tg.models import Model
from tg.msg import MsgProxy
from tg.utils import (
    get_duration,
    get_video_resolution,
    get_waveform,
    handle_exception,
    is_yes,
    notify,
    suspend,
)
from tg.views import View

log = logging.getLogger(__name__)

MSGS_LEFT_SCROLL_THRESHOLD = 10


# start scrolling to next page when number of the msgs left is less than value.
# note, that setting high values could lead to situations when long msgs will
# be removed from the display in order to achive scroll threshold. this could
# cause blan areas on the msg display screen
MSGS_LEFT_SCROLL_THRESHOLD = 2


class Controller:
    """
    # MVC
    # Model is data from telegram
    # Controller handles keyboad events
    # View is terminal vindow
    """

    def __init__(self, model: Model, view: View, tg: Telegram) -> None:
        self.model = model
        self.view = view
        self.lock = threading.Lock()
        self.tg = tg
        self.handlers = {
            "updateChatDraftMessage": self.update_chat_draft_msg,
            "updateChatIsMarkedAsUnread": self.update_chat_marked_as_unread,
            "updateChatIsPinned": self.update_chat_is_pinned,
            "updateChatLastMessage": self.update_chat_last_msg,
            "updateChatNotificationSettings": self.update_chat_notification_settings,
            "updateChatOrder": self.update_chat_order,
            "updateChatReadInbox": self.update_chat_read_inbox,
            "updateChatTitle": self.update_chat_title,
            "updateFile": self.update_file,
            "updateMessageContent": self.update_msg_content,
            "updateMessageSendSucceeded": self.update_msg_send_succeeded,
            "updateNewMessage": self.update_new_msg,
        }

    def send_file(self, send_file_fun, *args, **kwargs):
        file_path = self.view.status.get_input()
        if file_path and os.path.isfile(file_path):
            chat_id = self.model.chats.id_by_index(self.model.current_chat)
            send_file_fun(file_path, chat_id, *args, **kwargs)

    def send_voice(self):
        file_path = f"/tmp/voice-{datetime.now()}.oga"
        with suspend(self.view) as s:
            s.call(config.record_cmd.format(file_path=file_path))
        resp = self.view.status.get_input(
            f"Do you want to send recording: {file_path}? [Y/n]"
        )
        if is_yes(resp) and os.path.isfile(file_path):
            chat_id = self.model.chats.id_by_index(self.model.current_chat)
            duration = get_duration(file_path)
            waveform = get_waveform(file_path)
            self.tg.send_voice(file_path, chat_id, duration, waveform)
            self.view.status.draw(f"Sent voice msg: {file_path}")

    def run(self) -> None:
        try:
            self.handle_chats()
        except Exception:
            log.exception("Error happened in main loop")

    def download_current_file(self):
        msg = MsgProxy(self.model.current_msg())
        log.debug("Downloading msg: %s", msg.msg)
        file_id = msg.file_id
        if file_id:
            self.download(file_id, msg["chat_id"], msg["id"])

    def download(self, file_id: int, chat_id: int, msg_id: int):
        log.info("Downloading file: file_id=%s", file_id)
        self.model.downloads[file_id] = (chat_id, msg_id)
        self.tg.download_file(file_id=file_id)
        log.info("Downloaded: file_id=%s", file_id)

    def open_current_msg(self):
        msg = MsgProxy(self.model.current_msg())
        log.info("Open msg: %s", msg.msg)
        if msg.is_text:
            text = msg["content"]["text"]["text"]
            with NamedTemporaryFile("w", suffix=".txt") as f:
                f.write(text)
                f.flush()
                with suspend(self.view) as s:
                    s.open_file(f.name)
            return

        path = msg.local_path
        if path:
            with suspend(self.view) as s:
                log.info("Opening file: %s", path)
                s.open_file(path)

    def write_long_msg(self):
        file_path = "/tmp/tg-msg.txt"
        with suspend(self.view) as s:
            s.call(f"$EDITOR {file_path} || vim {file_path}")
        if not os.path.isfile(file_path):
            return
        with open(file_path) as f:
            msg = f.read().strip()
        os.remove(file_path)
        if msg:
            self.model.send_message(text=msg)
            with self.lock:
                self.view.status.draw("Message sent")

    def handle_msgs(self) -> str:
        self.view.chats.resize(0.2)
        self.view.msgs.resize(0.8)
        self.refresh_chats()

        while True:

            repeat_factor, keys = self.view.get_keys(
                self.view.chats.h, self.view.chats.w
            )
            log.info("Pressed keys: %s", keys)
            if keys == "q":
                return "QUIT"
            elif keys == "]":
                if self.model.next_chat():
                    self.refresh_chats()
            elif keys == "[":
                if self.model.prev_chat():
                    self.refresh_chats()
            elif keys == "J":
                if self.model.next_msg(10):
                    self.refresh_msgs()
            elif keys == "K":
                if self.model.prev_msg(10):
                    self.refresh_msgs()
            elif keys in ("j", "^P"):
                if self.model.next_msg(repeat_factor):
                    self.refresh_msgs()
            elif keys in ("k", "^N"):
                if self.model.prev_msg(repeat_factor):
                    self.refresh_msgs()
            elif keys == "G":
                if self.model.jump_bottom():
                    self.refresh_msgs()
            elif keys == "dd":
                if self.model.delete_msg():
                    self.refresh_msgs()
            elif keys == "D":
                self.download_current_file()

            elif keys == "l":
                self.open_current_msg()

            elif keys == "sd":
                self.send_file(self.tg.send_doc)

            elif keys == "sp":
                self.send_file(self.tg.send_photo)

            elif keys == "sa":
                self.send_file(self.tg.send_audio)

            elif keys == "sv":
                file_path = self.view.status.get_input()
                if file_path and os.path.isfile(file_path):
                    chat_id = self.model.chats.id_by_index(
                        self.model.current_chat
                    )
                    width, height = get_video_resolution(file_path)
                    duration = get_duration(file_path)
                    self.tg.send_video(
                        file_path, chat_id, width, height, duration
                    )

            elif keys == "v":
                self.send_voice()

            elif keys == "/":
                # search
                pass
            elif keys == "gg":
                # move to the top
                pass
            elif keys == "e":
                # edit msg
                pass
            elif keys == "r":
                # reply to this msg
                # print to status line
                pass
            elif keys in ("i", "a"):
                # write new message
                msg = self.view.status.get_input()
                if msg:
                    self.model.send_message(text=msg)
                    with self.lock:
                        self.view.status.draw(f"Sent: {msg}")

            elif keys in ("I", "A"):
                self.write_long_msg()

            elif keys in ("h", "^D"):
                return "BACK"

            elif keys == "bp":
                with suspend(self.view):
                    breakpoint()

    def handle_chats(self) -> None:
        self.view.chats.resize(0.5)
        self.view.msgs.resize(0.5)
        self.refresh_chats()
        while True:

            repeat_factor, keys = self.view.get_keys(
                self.view.chats.h, self.view.chats.w
            )
            log.info("Pressed keys: %s", keys)
            if keys == "q":
                return
            elif keys in ("l", "^J"):
                rc = self.handle_msgs()
                if rc == "QUIT":
                    return
                self.view.chats.resize(0.5)
                self.view.msgs.resize(0.5)
                self.refresh_chats()

            elif keys in ("j", "^N"):
                if self.model.next_chat(repeat_factor):
                    self.refresh_chats()

            elif keys in ("k", "^P"):
                if self.model.prev_chat(repeat_factor):
                    self.refresh_chats()

            elif keys in ("J",):
                if self.model.next_chat(10):
                    self.refresh_chats()

            elif keys in ("K",):
                if self.model.prev_chat(10):
                    self.refresh_chats()

            elif keys == "gg":
                if self.model.first_chat():
                    self.refresh_chats()

            elif keys == "bp":
                with suspend(self.view):
                    breakpoint()

            elif keys == "u":
                chat = self.model.chats.chats[self.model.current_chat]
                chat_id = chat["id"]
                toggle = not chat["is_marked_as_unread"]
                self.tg.toggle_chat_is_marked_as_unread(chat_id, toggle)

            elif keys == "p":
                chat = self.model.chats.chats[self.model.current_chat]
                chat_id = chat["id"]
                toggle = not chat["is_pinned"]
                self.tg.toggle_chat_is_pinned(chat_id, toggle)

            elif keys == "r":
                chat = self.model.chats.chats[self.model.current_chat]
                chat_id = chat["id"]
                msg_id = chat["last_message"]["id"]
                self.tg.view_messages(chat_id, [msg_id])

            elif keys == "m":
                # TODO: if it's msg to yourself, do not change its
                # notification setting, because we can't by documentation,
                # instead write about it in status
                chat = self.model.chats.chats[self.model.current_chat]
                chat_id = chat["id"]
                notification_settings = chat["notification_settings"]
                if notification_settings["mute_for"]:
                    notification_settings["mute_for"] = 0
                else:
                    notification_settings["mute_for"] = 2147483647
                self.tg.set_chat_nottification_settings(
                    chat_id, notification_settings
                )

    def refresh_chats(self) -> None:
        with self.lock:
            # using lock here, because refresh_chats is used from another
            # thread by tdlib python wrapper
            page_size = self.view.msgs.h
            chats = self.model.get_chats(
                self.model.current_chat, page_size, MSGS_LEFT_SCROLL_THRESHOLD
            )
            selected_chat = min(
                self.model.current_chat, page_size - MSGS_LEFT_SCROLL_THRESHOLD
            )

            self.view.chats.draw(selected_chat, chats)
            self.refresh_msgs()
            self.view.status.draw()

    def refresh_msgs(self) -> None:
        self.view.msgs.users = self.model.users
        current_msg_idx = self.model.get_current_chat_msg_idx()
        if current_msg_idx is None:
            return
        msgs = self.model.fetch_msgs(
            current_position=current_msg_idx,
            page_size=self.view.msgs.h,
            msgs_left_scroll_threshold=MSGS_LEFT_SCROLL_THRESHOLD,
        )
        self.view.msgs.draw(current_msg_idx, msgs, MSGS_LEFT_SCROLL_THRESHOLD)

    @handle_exception
    def update_msg_content(self, update):
        content = MsgProxy(update["new_content"])
        chat_id = update["chat_id"]
        message_id = update["message_id"]
        self.model.msgs.update_msg_content(chat_id, message_id, content)
        current_chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if current_chat_id == chat_id:
            self.refresh_msgs()

    @handle_exception
    def update_new_msg(self, update):
        msg = MsgProxy(update["message"])
        chat_id = msg["chat_id"]
        self.model.msgs.add_message(chat_id, msg)
        current_chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if current_chat_id == chat_id:
            self.refresh_msgs()
        if msg.file_id and msg.size <= config.max_download_size:
            self.download(msg.file_id, chat_id, msg["id"])

        self._notify_for_message(chat_id, msg)

    def _notify_for_message(self, chat_id: int, msg: Dict[str, Any]):
        # do not notify, if muted
        # TODO: optimize
        chat = None
        for chat in self.model.chats.chats:
            if chat_id == chat["id"]:
                break

        # TODO: handle cases when all chats muted on global level
        if chat and chat["notification_settings"]["mute_for"]:
            return

        # notify
        user_id = msg["sender_user_id"]
        if msg["sender_user_id"] == self.model.get_me()["id"]:
            return
        user = self.model.users.get_user(user_id)
        name = "{} {}".format(user["first_name"], user["last_name"])
        _type = msg["content"]["@type"]

        if _type == "messageText":
            text = msg["content"]["text"]["text"]
        else:
            text = MsgProxy.types.get(_type, "")
        notify(text, title=name)

    @handle_exception
    def update_chat_order(self, update: Dict[str, Any]):
        log.info("Proccessing updateChatOrder")
        current_chat_id = self.model.chats.id_by_index(self.model.current_chat)
        chat_id = update["chat_id"]
        order = update["order"]

        self.model.chats.update_chat(chat_id, order=order)
        self._refresh_current_chat(current_chat_id)

    @handle_exception
    def update_chat_title(self, update: Dict[str, Any]):
        log.info("Proccessing updateChatTitle")
        chat_id = update["chat_id"]
        title = update["title"]
        current_chat_id = self.model.chats.id_by_index(self.model.current_chat)
        self.model.chats.update_chat(chat_id, title=title)
        self._refresh_current_chat(current_chat_id)

    @handle_exception
    def update_chat_marked_as_unread(self, update: Dict[str, Any]):
        log.info("Proccessing updateChatIsMarkedAsUnread")
        chat_id = update["chat_id"]
        is_marked_as_unread = update["is_marked_as_unread"]
        current_chat_id = self.model.chats.id_by_index(self.model.current_chat)
        self.model.chats.update_chat(
            chat_id, is_marked_as_unread=is_marked_as_unread
        )
        self._refresh_current_chat(current_chat_id)

    @handle_exception
    def update_chat_is_pinned(self, update: Dict[str, Any]):
        log.info("Proccessing updateChatIsPinned")
        chat_id = update["chat_id"]
        is_pinned = update["is_pinned"]
        order = update["order"]
        current_chat_id = self.model.chats.id_by_index(self.model.current_chat)
        self.model.chats.update_chat(chat_id, is_pinned=is_pinned, order=order)
        self._refresh_current_chat(current_chat_id)

    @handle_exception
    def update_chat_read_inbox(self, update: Dict[str, Any]):
        log.info("Proccessing updateChatReadInbox")
        chat_id = update["chat_id"]
        last_read_inbox_message_id = update["last_read_inbox_message_id"]
        unread_count = update["unread_count"]
        current_chat_id = self.model.chats.id_by_index(self.model.current_chat)
        self.model.chats.update_chat(
            chat_id,
            last_read_inbox_message_id=last_read_inbox_message_id,
            unread_count=unread_count,
        )
        self._refresh_current_chat(current_chat_id)

    @handle_exception
    def update_chat_draft_msg(self, update: Dict[str, Any]):
        log.info("Proccessing updateChatDraftMessage")
        chat_id = update["chat_id"]
        # FIXME: ignoring draft message itself for now because UI can't show it
        # draft_message = update["draft_message"]
        order = update["order"]
        current_chat_id = self.model.chats.id_by_index(self.model.current_chat)
        self.model.chats.update_chat(chat_id, order=order)
        self._refresh_current_chat(current_chat_id)

    @handle_exception
    def update_chat_last_msg(self, update: Dict[str, Any]):
        log.info("Proccessing updateChatLastMessage")
        chat_id = update["chat_id"]
        message = update["last_message"]
        order = update["order"]
        current_chat_id = self.model.chats.id_by_index(self.model.current_chat)
        self.model.chats.update_chat(
            chat_id, last_message=message, order=order
        )
        self._refresh_current_chat(current_chat_id)

    def _refresh_current_chat(self, current_chat_id: Optional[int]):
        if current_chat_id is None:
            return
        # TODO: we can create <index> for chats, it's faster than sqlite anyway
        # though need to make sure that creatinng index is atomic operation
        # requires locks for read, until index and chats will be the same
        for i, chat in enumerate(self.model.chats.chats):
            if chat["id"] == current_chat_id:
                self.model.current_chat = i
                break
        self.refresh_chats()

    @handle_exception
    def update_chat_notification_settings(self, update):
        log.info("Proccessing update_chat_notification_settings")
        chat_id = update["chat_id"]
        notification_settings = update["notification_settings"]
        self.model.chats.update_chat(
            chat_id, notification_settings=notification_settings
        )
        self.refresh_chats()

    @handle_exception
    def update_msg_send_succeeded(self, update):
        chat_id = update["message"]["chat_id"]
        msg_id = update["old_message_id"]
        self.model.msgs.add_message(chat_id, update["message"])
        self.model.msgs.remove_message(chat_id, msg_id)
        current_chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if current_chat_id == chat_id:
            self.refresh_msgs()

    @handle_exception
    def update_file(self, update):
        log.info("update_file: %s", update)
        file_id = update["file"]["id"]
        local = update["file"]["local"]
        chat_id, msg_id = self.model.downloads.get(file_id, (None, None))
        if chat_id is None:
            log.warning(
                "Can't find information about file with file_id=%s", file_id
            )
            return
        msgs = self.model.msgs.msgs[chat_id]
        for msg in msgs:
            if msg["id"] == msg_id:
                proxy = MsgProxy(msg)
                proxy.local = local
                self.refresh_msgs()
                if proxy.is_downloaded:
                    self.model.downloads.pop(file_id)
                break
