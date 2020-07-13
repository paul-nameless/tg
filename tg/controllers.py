import curses
import logging
import os
import shlex
from datetime import datetime
from functools import partial, wraps
from queue import Queue
from tempfile import NamedTemporaryFile
from typing import Any, Callable, Dict, List, Optional

from telegram.utils import AsyncResult
from tg import config
from tg.models import Model
from tg.msg import MsgProxy
from tg.tdlib import ChatAction, Tdlib
from tg.utils import (
    get_duration,
    get_video_resolution,
    get_waveform,
    is_yes,
    notify,
    suspend,
)
from tg.views import View, get_user_label

log = logging.getLogger(__name__)

# start scrolling to next page when number of the msgs left is less than value.
# note, that setting high values could lead to situations when long msgs will
# be removed from the display in order to achive scroll threshold. this could
# cause blan areas on the msg display screen
MSGS_LEFT_SCROLL_THRESHOLD = 2
REPLY_MSG_PREFIX = "# >"
HandlerType = Callable[[Any], Optional[str]]

chat_handler: Dict[str, HandlerType] = {}
msg_handler: Dict[str, HandlerType] = {}


def bind(
    binding: Dict[str, HandlerType],
    keys: List[str],
    repeat_factor: bool = False,
) -> Callable:
    """bind handlers to given keys"""

    def decorator(fun: Callable) -> HandlerType:
        @wraps(fun)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fun(*args, **kwargs)

        @wraps(fun)
        def _no_repeat_factor(self: "Controller", _: bool) -> Any:
            return fun(self)

        for key in keys:
            assert (
                key not in binding
            ), f"Key {key} already binded to {binding[key]}"
            binding[key] = fun if repeat_factor else _no_repeat_factor

        return wrapper

    return decorator


class Controller:
    def __init__(self, model: Model, view: View, tg: Tdlib) -> None:
        self.model = model
        self.view = view
        self.queue: Queue = Queue()
        self.is_running = True
        self.tg = tg
        self.chat_size = 0.5

    @bind(msg_handler, ["o"])
    def open_url(self) -> None:
        msg = MsgProxy(self.model.current_msg)
        if not msg.is_text:
            self.present_error("Does not contain urls")
            return
        text = msg["content"]["text"]["text"]
        urls = []
        for entity in msg["content"]["text"]["entities"]:
            if entity["type"]["@type"] != "textEntityTypeUrl":
                continue
            offset = entity["offset"]
            length = entity["length"]
            url = text[offset : offset + length]
            urls.append(url)
        if not urls:
            self.present_error("No url to open")
            return
        if len(urls) == 1:
            with suspend(self.view) as s:
                s.call(config.DEFAULT_OPEN.format(file_path=shlex.quote(url)))
            return
        with suspend(self.view) as s:
            s.run_with_input(config.URL_VIEW, "\n".join(urls))

    @staticmethod
    def format_help(bindings: Dict[str, HandlerType]) -> str:
        return "\n".join(
            f"{key}\t{fun.__name__}\t{fun.__doc__ or ''}"
            for key, fun in sorted(bindings.items())
        )

    @bind(chat_handler, ["?"])
    def show_chat_help(self) -> None:
        _help = self.format_help(chat_handler)
        with suspend(self.view) as s:
            s.run_with_input(config.VIEW_TEXT_CMD, _help)

    @bind(msg_handler, ["?"])
    def show_msg_help(self) -> None:
        _help = self.format_help(msg_handler)
        with suspend(self.view) as s:
            s.run_with_input(config.VIEW_TEXT_CMD, _help)

    @bind(chat_handler, ["bp"])
    @bind(msg_handler, ["bp"])
    def breakpoint(self) -> None:
        with suspend(self.view):
            breakpoint()

    @bind(chat_handler, ["q"])
    @bind(msg_handler, ["q"])
    def quit(self) -> str:
        return "QUIT"

    @bind(msg_handler, ["h", "^D"])
    def back(self) -> str:
        return "BACK"

    @bind(msg_handler, ["m"])
    def jump_to_reply_msg(self) -> None:
        chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if not chat_id:
            return
        msg = MsgProxy(self.model.current_msg)
        if not msg.reply_msg_id:
            return self.present_error("This msg does not reply")
        if not self.model.msgs.jump_to_msg_by_id(chat_id, msg.reply_msg_id):
            return self.present_error(
                "Can't jump to reply msg: it's not preloaded or deleted"
            )
        return self.render_msgs()

    @bind(msg_handler, ["p"])
    def forward_msgs(self) -> None:
        """Paste yanked msgs"""
        if not self.model.forward_msgs():
            self.present_error("Can't forward msg(s)")
            return
        self.present_info("Forwarded msg(s)")

    @bind(msg_handler, ["y"])
    def yank_msgs(self) -> None:
        """Copy msgs to clipboard and internal buffer to forward"""
        chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if not chat_id:
            return
        msg_ids = self.model.selected[chat_id]
        if not msg_ids:
            msg = self.model.current_msg
            msg_ids = [msg["id"]]
        self.model.copied_msgs = (chat_id, msg_ids)
        self.discard_selected_msgs()
        self.model.copy_msgs_text()
        self.present_info(f"Copied {len(msg_ids)} msg(s)")

    def _toggle_select_msg(self) -> None:
        chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if not chat_id:
            return
        msg = MsgProxy(self.model.current_msg)

        if msg.msg_id in self.model.selected[chat_id]:
            self.model.selected[chat_id].remove(msg.msg_id)
        else:
            self.model.selected[chat_id].append(msg.msg_id)

    @bind(msg_handler, [" "])
    def toggle_select_msg_down(self) -> None:
        """Select and jump to next msg with <space>"""
        self._toggle_select_msg()
        self.model.next_msg()
        self.render_msgs()

    @bind(msg_handler, ["^@"])
    def toggle_select_msg_up(self) -> None:
        """Select and jump to previous msg with ctrl+<space>"""
        self._toggle_select_msg()
        self.model.prev_msg()
        self.render_msgs()

    @bind(msg_handler, ["^G", "^["])
    def discard_selected_msgs(self) -> None:
        chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if not chat_id:
            return
        self.model.selected[chat_id] = []
        self.render_msgs()
        self.present_info("Discarded selected messages")

    @bind(msg_handler, ["G"])
    def bottom_msg(self) -> None:
        if self.model.jump_bottom():
            self.render_msgs()

    @bind(msg_handler, ["j", "^B", "^N"], repeat_factor=True)
    def next_msg(self, repeat_factor: int = 1) -> None:
        if self.model.next_msg(repeat_factor):
            self.render_msgs()

    @bind(msg_handler, ["J"])
    def jump_10_msgs_down(self) -> None:
        self.next_msg(10)

    @bind(msg_handler, ["k", "^C", "^P"], repeat_factor=True)
    def prev_msg(self, repeat_factor: int = 1) -> None:
        if self.model.prev_msg(repeat_factor):
            self.render_msgs()

    @bind(msg_handler, ["K"])
    def jump_10_msgs_up(self) -> None:
        self.prev_msg(10)

    @bind(msg_handler, ["r"])
    def reply_message(self) -> None:
        if not self.can_send_msg():
            self.present_info("Can't send msg in this chat")
            return
        chat_id = self.model.current_chat_id
        if chat_id is None:
            return
        reply_to_msg = self.model.current_msg_id
        if msg := self.view.status.get_input():
            self.tg.reply_message(chat_id, reply_to_msg, msg)
            self.present_info("Message reply sent")
        else:
            self.present_info("Message reply wasn't sent")

    @bind(msg_handler, ["R"])
    def reply_with_long_message(self) -> None:
        if not self.can_send_msg():
            self.present_info("Can't send msg in this chat")
            return
        chat_id = self.model.current_chat_id
        if chat_id is None:
            return
        reply_to_msg = self.model.current_msg_id
        msg = MsgProxy(self.model.current_msg)
        with NamedTemporaryFile("w+", suffix=".txt") as f, suspend(
            self.view
        ) as s:
            f.write(insert_replied_msg(msg))
            f.seek(0)
            s.call(config.LONG_MSG_CMD.format(file_path=shlex.quote(f.name)))
            with open(f.name) as f:
                if replied_msg := strip_replied_msg(f.read().strip()):
                    self.tg.reply_message(chat_id, reply_to_msg, replied_msg)
                    self.present_info("Message sent")
                else:
                    self.present_info("Message wasn't sent")

    @bind(msg_handler, ["a", "i"])
    def write_short_msg(self) -> None:
        chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if not self.can_send_msg() or chat_id is None:
            self.present_info("Can't send msg in this chat")
            return
        self.tg.send_chat_action(chat_id, ChatAction.chatActionTyping)
        if msg := self.view.status.get_input():
            self.model.send_message(text=msg)
            self.present_info("Message sent")
        else:
            self.tg.send_chat_action(chat_id, ChatAction.chatActionCancel)
            self.present_info("Message wasn't sent")

    @bind(msg_handler, ["A", "I"])
    def write_long_msg(self) -> None:
        chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if not self.can_send_msg() or chat_id is None:
            self.present_info("Can't send msg in this chat")
            return
        with NamedTemporaryFile("r+", suffix=".txt") as f, suspend(
            self.view
        ) as s:
            self.tg.send_chat_action(chat_id, ChatAction.chatActionTyping)
            s.call(config.LONG_MSG_CMD.format(file_path=shlex.quote(f.name)))
            with open(f.name) as f:
                if msg := f.read().strip():
                    self.model.send_message(text=msg)
                    self.present_info("Message sent")
                else:
                    self.tg.send_chat_action(
                        chat_id, ChatAction.chatActionCancel
                    )
                    self.present_info("Message wasn't sent")

    @bind(msg_handler, ["sv"])
    def send_video(self) -> None:
        file_path = self.view.status.get_input()
        if not file_path or not os.path.isfile(file_path):
            return
        chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if not chat_id:
            return
        width, height = get_video_resolution(file_path)
        duration = get_duration(file_path)
        self.tg.send_video(file_path, chat_id, width, height, duration)

    @bind(msg_handler, ["dd"])
    def delete_msgs(self) -> None:
        is_deleted = self.model.delete_msgs()
        self.discard_selected_msgs()
        if not is_deleted:
            self.present_error("Can't delete msg(s)")
            return
        self.present_info("Message deleted")

    @bind(msg_handler, ["sd"])
    def send_document(self) -> None:
        self.send_file(self.tg.send_doc)

    @bind(msg_handler, ["sp"])
    def send_picture(self) -> None:
        self.send_file(self.tg.send_photo)

    @bind(msg_handler, ["sa"])
    def send_audio(self) -> None:
        self.send_file(self.tg.send_audio)

    def send_file(
        self, send_file_fun: Callable[[str, int], AsyncResult],
    ) -> None:
        file_path = os.path.expanduser(self.view.status.get_input())
        if not file_path or not os.path.isfile(file_path):
            return self.present_info("Given path to file does not exist")

        if chat_id := self.model.chats.id_by_index(self.model.current_chat):
            send_file_fun(file_path, chat_id)
            self.present_info("File sent")

    @bind(msg_handler, ["v"])
    def record_voice(self) -> None:
        file_path = f"/tmp/voice-{datetime.now()}.oga"
        with suspend(self.view) as s:
            s.call(
                config.VOICE_RECORD_CMD.format(
                    file_path=shlex.quote(file_path)
                )
            )
        resp = self.view.status.get_input(
            f"Do you want to send recording: {file_path}? [Y/n]"
        )
        if not is_yes(resp):
            self.present_info("Voice message discarded")
            return

        if not os.path.isfile(file_path):
            self.present_info(f"Can't load recording file {file_path}")
            return

        chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if not chat_id:
            return
        duration = get_duration(file_path)
        waveform = get_waveform(file_path)
        self.tg.send_voice(file_path, chat_id, duration, waveform)
        self.present_info(f"Sent voice msg: {file_path}")

    @bind(msg_handler, ["D"])
    def download_current_file(self) -> None:
        msg = MsgProxy(self.model.current_msg)
        log.debug("Downloading msg: %s", msg.msg)
        file_id = msg.file_id
        if not file_id:
            self.present_info("File can't be downloaded")
            return
        self.download(file_id, msg["chat_id"], msg["id"])
        self.present_info("File started downloading")

    def download(self, file_id: int, chat_id: int, msg_id: int) -> None:
        log.info("Downloading file: file_id=%s", file_id)
        self.model.downloads[file_id] = (chat_id, msg_id)
        self.tg.download_file(file_id=file_id)
        log.info("Downloaded: file_id=%s", file_id)

    def can_send_msg(self) -> bool:
        chat = self.model.chats.chats[self.model.current_chat]
        return chat["permissions"]["can_send_messages"]

    def _open_msg(self, msg: MsgProxy, cmd: str = None) -> None:
        if msg.is_text:
            with NamedTemporaryFile("w", suffix=".txt") as f:
                f.write(msg.text_content)
                f.flush()
                with suspend(self.view) as s:
                    s.open_file(f.name, cmd)
            return

        path = msg.local_path
        if not path:
            self.present_info("File should be downloaded first")
            return
        chat_id = self.model.chats.id_by_index(self.model.current_chat)
        if not chat_id:
            return
        self.tg.open_message_content(chat_id, msg.msg_id)
        with suspend(self.view) as s:
            s.open_file(path, cmd)

    @bind(msg_handler, ["!"])
    def open_msg_with_cmd(self) -> None:
        """Open msg or file with cmd: less %s"""
        msg = MsgProxy(self.model.current_msg)
        cmd = self.view.status.get_input()
        if not cmd:
            return
        if "%s" not in cmd:
            return self.present_error(
                "command should contain <%s> which will be replaced by file path"
            )
        return self._open_msg(msg, cmd)

    @bind(msg_handler, ["l", "^J"])
    def open_current_msg(self) -> None:
        """Open msg or file with cmd in mailcap"""
        msg = MsgProxy(self.model.current_msg)
        self._open_msg(msg)

    @bind(msg_handler, ["e"])
    def edit_msg(self) -> None:
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
            s.call(f"{config.EDITOR} {f.name}")
            with open(f.name) as f:
                if text := f.read().strip():
                    self.model.edit_message(text=text)
                    self.present_info("Message edited")

    @bind(chat_handler, ["c"])
    def view_contacts(self) -> None:
        contacts = self.model.users.get_contacts()
        if contacts is None:
            return self.present_error("Can't get contacts")

        total = contacts["total_count"]
        users = []
        for user_id in contacts["user_ids"]:
            user_name = get_user_label(self.model.users, user_id)
            status = self.model.users.get_status(user_id)
            order = self.model.users.get_user_status_order(user_id)
            users.append((user_name, status, order))

        _, cols = self.view.stdscr.getmaxyx()
        limit = min(
            int(cols / 2), max(len(user_name) for user_name, *_ in users)
        )
        users_out = "\n".join(
            f"{user_name:<{limit}} | {status}"
            for user_name, status, _ in sorted(users, key=lambda it: it[2])
        )
        with suspend(self.view) as s:
            s.run_with_input(
                config.VIEW_TEXT_CMD, f"{total} users:\n" + users_out
            )

    @bind(chat_handler, ["l", "^J", "^E"])
    def handle_msgs(self) -> Optional[str]:
        rc = self.handle(msg_handler, 0.2)
        if rc == "QUIT":
            return rc
        self.chat_size = 0.5
        self.resize()

    @bind(chat_handler, ["g"])
    def top_chat(self) -> None:
        if self.model.first_chat():
            self.render()

    @bind(chat_handler, ["j", "^B", "^N"], repeat_factor=True)
    @bind(msg_handler, ["]"])
    def next_chat(self, repeat_factor: int = 1) -> None:
        if self.model.next_chat(repeat_factor):
            self.render()

    @bind(chat_handler, ["k", "^C", "^P"], repeat_factor=True)
    @bind(msg_handler, ["["])
    def prev_chat(self, repeat_factor: int = 1) -> None:
        if self.model.prev_chat(repeat_factor):
            self.render()

    @bind(chat_handler, ["J"])
    def jump_10_chats_down(self) -> None:
        self.next_chat(10)

    @bind(chat_handler, ["K"])
    def jump_10_chats_up(self) -> None:
        self.prev_chat(10)

    @bind(chat_handler, ["u"])
    def toggle_unread(self) -> None:
        chat = self.model.chats.chats[self.model.current_chat]
        chat_id = chat["id"]
        toggle = not chat["is_marked_as_unread"]
        self.tg.toggle_chat_is_marked_as_unread(chat_id, toggle)
        self.render()

    @bind(chat_handler, ["r"])
    def read_msgs(self) -> None:
        chat = self.model.chats.chats[self.model.current_chat]
        chat_id = chat["id"]
        msg_id = chat["last_message"]["id"]
        self.tg.view_messages(chat_id, [msg_id])
        self.render()

    @bind(chat_handler, ["m"])
    def toggle_mute(self) -> None:
        # TODO: if it's msg to yourself, do not change its
        # notification setting, because we can't by documentation,
        # instead write about it in status
        chat = self.model.chats.chats[self.model.current_chat]
        chat_id = chat["id"]
        if self.model.is_me(chat_id):
            self.present_error("You can't mute Saved Messages")
            return
        notification_settings = chat["notification_settings"]
        if notification_settings["mute_for"]:
            notification_settings["mute_for"] = 0
        else:
            notification_settings["mute_for"] = 2147483647
        self.tg.set_chat_nottification_settings(chat_id, notification_settings)
        self.render()

    @bind(chat_handler, ["p"])
    def toggle_pin(self) -> None:
        chat = self.model.chats.chats[self.model.current_chat]
        chat_id = chat["id"]
        toggle = not chat["is_pinned"]
        self.tg.toggle_chat_is_pinned(chat_id, toggle)
        self.render()

    def run(self) -> None:
        try:
            self.handle(chat_handler, 0.5)
            self.queue.put(self.close)
        except Exception:
            log.exception("Error happened in main loop")

    def close(self) -> None:
        self.is_running = False

    def handle(self, handlers: Dict[str, HandlerType], size: float) -> str:
        self.chat_size = size
        self.resize()

        while True:
            try:
                repeat_factor, keys = self.view.get_keys()
                fun = handlers.get(keys, lambda *_: None)
                res = fun(self, repeat_factor)  # type: ignore
                if res == "QUIT":
                    return res
                elif res == "BACK":
                    return res
            except Exception:
                log.exception("Error happend in key handle loop")

    def resize_handler(self, signum: int, frame: Any) -> None:
        curses.endwin()
        self.view.stdscr.refresh()
        self.resize()

    def resize(self) -> None:
        self.queue.put(self._resize)

    def _resize(self) -> None:
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

    def draw(self) -> None:
        while self.is_running:
            try:
                log.info("Queue size: %d", self.queue.qsize())
                fun = self.queue.get()
                fun()
            except Exception:
                log.exception("Error happened in draw loop")

    def present_error(self, msg: str) -> None:
        return self.update_status("Error", msg)

    def present_info(self, msg: str) -> None:
        return self.update_status("Info", msg)

    def update_status(self, level: str, msg: str) -> None:
        self.queue.put(partial(self._update_status, level, msg))

    def _update_status(self, level: str, msg: str) -> None:
        self.view.status.draw(f"{level}: {msg}")

    def render(self) -> None:
        self.queue.put(self._render)

    def _render(self) -> None:
        self.render_chats()
        self.render_msgs()
        self.view.status.draw()

    def render_chats(self) -> None:
        self.queue.put(self._render_chats)

    def _render_chats(self) -> None:
        page_size = self.view.chats.h - 1
        chats = self.model.get_chats(
            self.model.current_chat, page_size, MSGS_LEFT_SCROLL_THRESHOLD
        )
        selected_chat = min(
            self.model.current_chat, page_size - MSGS_LEFT_SCROLL_THRESHOLD
        )
        self.view.chats.draw(selected_chat, chats, self.model.chats.title)

    def render_msgs(self) -> None:
        self.queue.put(self._render_msgs)

    def _render_msgs(self) -> None:
        current_msg_idx = self.model.get_current_chat_msg_idx()
        if current_msg_idx is None:
            return
        msgs = self.model.fetch_msgs(
            current_position=current_msg_idx,
            page_size=self.view.msgs.h - 1,
            msgs_left_scroll_threshold=MSGS_LEFT_SCROLL_THRESHOLD,
        )
        chat = self.model.chats.chats[self.model.current_chat]
        self.view.msgs.draw(
            current_msg_idx, msgs, MSGS_LEFT_SCROLL_THRESHOLD, chat
        )

    def notify_for_message(self, chat_id: int, msg: MsgProxy) -> None:
        # do not notify, if muted
        # TODO: optimize
        for chat in self.model.chats.chats:
            if chat_id == chat["id"]:
                break
        else:
            # chat not found, do not notify
            return

        # TODO: handle cases when all chats muted on global level
        if chat["notification_settings"]["mute_for"]:
            return

        # notify
        if self.model.is_me(msg["sender_user_id"]):
            return
        user = self.model.users.get_user(msg.sender_id)
        name = f"{user['first_name']} {user['last_name']}"

        if text := msg.text_content if msg.is_text else msg.content_type:
            notify(text, title=name)

    def refresh_current_chat(self, current_chat_id: Optional[int]) -> None:
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


def insert_replied_msg(msg: MsgProxy) -> str:
    text = msg.text_content if msg.is_text else msg.content_type
    if not text:
        return ""
    return (
        "\n".join([f"{REPLY_MSG_PREFIX} {line}" for line in text.split("\n")])
        # adding line with whitespace so text editor could start editing from last line
        + "\n "
    )


def strip_replied_msg(msg: str) -> str:
    return "\n".join(
        [
            line
            for line in msg.split("\n")
            if not line.startswith(REPLY_MSG_PREFIX)
        ]
    )
