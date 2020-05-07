import logging
import os
import threading
from tempfile import NamedTemporaryFile

from telegram.client import Telegram

from tg.utils import notify, handle_exception, suspend
from tg.models import Model
from tg.views import View
from tg.msg import MsgProxy

log = logging.getLogger(__name__)


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
            "updateChatLastMessage": self.update_chat_last_msg,
            "updateMessageSendSucceeded": self.update_msg_send_succeeded,
            "updateFile": self.update_file,
        }

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
            log.info("Downloading file: file_id=%s", file_id)
            self.model.downloads[file_id] = (msg["chat_id"], msg["id"])
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
                    s.run(f.name)
            return

        path = msg.local_path
        if path:
            with suspend(self.view) as s:
                log.info("Opening file: %s", path)
                s.run(path)

    def handle_msgs(self) -> str:
        # set width to 0.25, move window to left
        # refresh everything
        self.view.chats.resize(0.2)
        self.view.msgs.resize(0.2)
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
                msg = self.view.get_input()
                if msg:
                    self.model.send_message(text=msg)
                    self.view.draw_status(f"Sent: {msg}")

            elif keys in ("h", "^D"):
                return "BACK"

    def handle_chats(self) -> None:
        # set width to 0.5, move window to center?
        # refresh everything
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

    def refresh_chats(self) -> None:
        with self.lock:
            # using lock here, because refresh_chats is used from another
            # thread by tdlib python wrapper
            self.view.draw_chats(
                self.model.current_chat,
                self.model.get_chats(limit=self.view.chats.h),
            )
            self.refresh_msgs()
            self.view.draw_status()

    def refresh_msgs(self) -> None:
        self.view.msgs.users = self.model.users
        msgs = self.model.fetch_msgs(limit=self.view.msgs.h)
        self.view.draw_msgs(self.model.get_current_chat_msg(), msgs)

    @handle_exception
    def update_new_msg(self, update):
        msg = update["message"]
        chat_id = msg["chat_id"]
        self.model.msgs.add_message(chat_id, msg)
        self.refresh_msgs()

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
    def update_chat_last_msg(self, update):
        log.info("Proccessing updateChatLastMessage")
        chat_id = update["chat_id"]
        message = update["last_message"]
        current_chat_id = self.model.chats.id_by_index(self.model.current_chat)
        self.model.chats.update_last_message(chat_id, message)
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
