import logging
from typing import Dict, Any, Optional
import os
import threading
from datetime import datetime
from tempfile import NamedTemporaryFile

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
            "updateNewMessage": self.update_new_msg,
            "updateChatIsPinned": self.update_chat_is_pinned,
            "updateChatReadInbox": self.update_chat_read_inbox,
            "updateChatTitle": self.update_chat_title,
            "updateChatLastMessage": self.update_chat_last_msg,
            "updateChatDraftMessage": self.update_chat_draft_msg,
            "updateChatOrder": self.update_chat_order,
            "updateMessageSendSucceeded": self.update_msg_send_succeeded,
            "updateFile": self.update_file,
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

    def download(self, file_id: int, chat_id, msg_id):
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
            elif keys == "I":
                # open vim or emacs to write long messages
                pass
            elif keys in ("i", "a"):
                # write new message
                msg = self.view.status.get_input()
                if msg:
                    self.model.send_message(text=msg)
                    self.view.status.draw(f"Sent: {msg}")

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
        msgs = self.model.fetch_msgs(limit=self.view.msgs.h)
        self.view.msgs.draw(self.model.get_current_chat_msg(), msgs)

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

        # do not notify, if muted
        # TODO: optimize
        chat = None
        for chat in self.model.chats.chats:
            if chat_id == chat["id"]:
                chat = chat
                break

        if (
            chat
            and chat["notification_settings"]["mute_for"]
            or chat["notification_settings"]["use_default_mute_for"]
        ):
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
