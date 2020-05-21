import curses
import logging
import os
import threading
from datetime import datetime
from signal import SIGWINCH, signal
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional

from tg import config
from tg.models import Model
from tg.msg import MsgProxy
from tg.tdlib import Tdlib
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

    def __init__(self, model: Model, view: View, tg: Tdlib) -> None:
        self.model = model
        self.view = view
        self.lock = threading.Lock()
        self.tg = tg
        self.chat_size = 0.5
        signal(SIGWINCH, self.resize_handler)

    def send_file(self, send_file_fun, *args, **kwargs):
        file_path = self.view.status.get_input()
        if file_path and os.path.isfile(file_path):
            chat_id = self.model.chats.id_by_index(self.model.current_chat)
            send_file_fun(file_path, chat_id, *args, **kwargs)
            self.present_info("File sent")

    def send_voice(self):
        file_path = f"/tmp/voice-{datetime.now()}.oga"
        with suspend(self.view) as s:
            s.call(config.record_cmd.format(file_path=file_path))
        resp = self.view.status.get_input(
            f"Do you want to send recording: {file_path}? [Y/n]"
        )
        if not is_yes(resp):
            self.present_info("Voice message discarded")
        elif not os.path.isfile(file_path):
            self.present_info(f"Can't load recording file {file_path}")
        else:
            chat_id = self.model.chats.id_by_index(self.model.current_chat)
            duration = get_duration(file_path)
            waveform = get_waveform(file_path)
            self.tg.send_voice(file_path, chat_id, duration, waveform)
            self.present_info(f"Sent voice msg: {file_path}")

    def run(self) -> None:
        try:
            self.handle_chats()
        except Exception:
            log.exception("Error happened in main loop")

    def download_current_file(self):
        msg = MsgProxy(self.model.current_msg)
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
        msg = MsgProxy(self.model.current_msg)
        if msg.is_text:
            with NamedTemporaryFile("w", suffix=".txt") as f:
                f.write(msg.text_content)
                f.flush()
                with suspend(self.view) as s:
                    s.open_file(f.name)
            return

        path = msg.local_path
        if path:
            chat_id = self.model.chats.id_by_index(self.model.current_chat)
            self.tg.open_message_content(chat_id, msg.msg_id)
            with suspend(self.view) as s:
                s.open_file(path)

    def present_error(self, msg: str):
        return self.update_status("Error", msg)

    def present_info(self, msg: str):
        return self.update_status("Info", msg)

    def update_status(self, level: str, msg: str):
        with self.lock:
            self.view.status.draw(f"{level}: {msg}")

    def edit_msg(self):
        msg = MsgProxy(self.model.current_msg)
        log.info("Editing msg: %s", msg.msg)
        if not self.model.is_me(msg.sender_id):
            return self.present_error("You can edit only your messages!")
        if not msg.is_text:
            return self.present_error("You can edit text messages only!")
        if not msg.can_be_edited:
            return self.present_error("Meessage can't be edited!")

        with NamedTemporaryFile("r+", suffix=".txt") as f, suspend(
            self.view
        ) as s:
            f.write(msg.text_content)
            f.flush()
            s.call(f"{config.editor} {f.name}")
            with open(f.name) as f:
                if msg := f.read().strip():
                    self.model.edit_message(text=msg)
                    self.present_info("Message edited")

    def write_long_msg(self):
        with NamedTemporaryFile("r+", suffix=".txt") as f, suspend(
            self.view
        ) as s:
            s.call(config.long_msg_cmd.format(file_path=f.name))
            with open(f.name) as f:
                if msg := f.read().strip():
                    self.model.send_message(text=msg)
                    self.present_info("Message sent")

    def resize_handler(self, signum, frame):
        curses.endwin()
        self.view.stdscr.refresh()
        self.resize()

    def resize(self):
        rows, cols = self.view.stdscr.getmaxyx()
        # If we didn't clear the screen before doing this,
        # the original window contents would remain on the screen
        # and we would see the window text twice.
        self.view.stdscr.erase()
        self.view.stdscr.noutrefresh()

        self.view.chats.resize(rows, cols, self.chat_size)
        self.view.msgs.resize(rows, cols, 1 - self.chat_size)
        self.view.status.resize(rows, cols)
        self.render()

    def handle_msgs(self) -> str:
        self.chat_size = 0.2
        self.resize()

        while True:

            repeat_factor, keys = self.view.get_keys()
            if keys == "q":
                return "QUIT"
            elif keys == "]":
                if self.model.next_chat():
                    self.render()
            elif keys == "[":
                if self.model.prev_chat():
                    self.render()
            elif keys == "J":
                if self.model.next_msg(10):
                    self.refresh_msgs()
            elif keys == "K":
                if self.model.prev_msg(10):
                    self.refresh_msgs()
            elif keys in ("j", "^N"):
                if self.model.next_msg(repeat_factor):
                    self.refresh_msgs()
            elif keys in ("k", "^P"):
                if self.model.prev_msg(repeat_factor):
                    self.refresh_msgs()
            elif keys == "G":
                if self.model.jump_bottom():
                    self.refresh_msgs()
            elif keys == "dd":
                if self.model.delete_msg():
                    self.refresh_msgs()
                    self.present_info("Message deleted")
            elif keys == "D":
                self.download_current_file()
                self.present_info("File downloaded")

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
                    if not chat_id:
                        continue
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
                self.edit_msg()

            elif keys == "r":
                # reply to this msg
                # print to status line
                pass

            elif keys in ("i", "a"):
                # write new message
                if msg := self.view.status.get_input():
                    self.model.send_message(text=msg)
                    self.present_info("Message sent")
                else:
                    self.present_info("Message wasn't sent")

            elif keys in ("I", "A"):
                self.write_long_msg()

            elif keys in ("h", "^D"):
                return "BACK"

            elif keys == "bp":
                with suspend(self.view):
                    breakpoint()

    def handle_chats(self) -> None:
        self.chat_size = 0.5
        self.resize()

        while True:

            repeat_factor, keys = self.view.get_keys()
            log.info("Pressed keys: %s", keys)
            if keys == "q":
                return
            elif keys in ("l", "^J"):
                rc = self.handle_msgs()
                if rc == "QUIT":
                    return
                self.chat_size = 0.5
                self.resize()

            elif keys in ("j", "^N"):
                if self.model.next_chat(repeat_factor):
                    self.render()

            elif keys in ("k", "^P"):
                if self.model.prev_chat(repeat_factor):
                    self.render()

            elif keys in ("J",):
                if self.model.next_chat(10):
                    self.render()

            elif keys in ("K",):
                if self.model.prev_chat(10):
                    self.render()

            elif keys == "gg":
                if self.model.first_chat():
                    self.render()

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

    def render(self) -> None:
        with self.lock:
            # using lock here, because render is used from another
            # thread by tdlib python wrapper
            page_size = self.view.chats.h
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
        current_msg_idx = self.model.get_current_chat_msg_idx()
        if current_msg_idx is None:
            return
        msgs = self.model.fetch_msgs(
            current_position=current_msg_idx,
            page_size=self.view.msgs.h,
            msgs_left_scroll_threshold=MSGS_LEFT_SCROLL_THRESHOLD,
        )
        self.view.msgs.draw(current_msg_idx, msgs, MSGS_LEFT_SCROLL_THRESHOLD)

    def _notify_for_message(self, chat_id: int, msg: MsgProxy):
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
        if self.model.is_me(msg["sender_user_id"]):
            return
        user = self.model.users.get_user(msg.sender_id)
        name = f"{user['first_name']} {user['last_name']}"

        text = msg.text_content if msg.is_text else msg.content_type
        notify(text, title=name)

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
        self.render()
