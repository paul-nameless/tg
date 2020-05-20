import curses
import logging
from _curses import window  # type: ignore
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, cast

from tg.colors import blue, cyan, get_color, magenta, reverse, white
from tg.models import MsgModel
from tg.models import UserModel
from tg.msg import MsgProxy
from tg.utils import emoji_pattern, num, truncate_to_len

log = logging.getLogger(__name__)

MAX_KEYBINDING_LENGTH = 5
MULTICHAR_KEYBINDINGS = (
    "gg",
    "dd",
    "sd",
    "sp",
    "sa",
    "sv",
    "bp",
)


class View:
    def __init__(
        self,
        stdscr: window,
        chat_view: "ChatView",
        msg_view: "MsgView",
        status_view: "StatusView",
    ) -> None:
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)
        curses.curs_set(0)

        curses.start_color()
        curses.use_default_colors()
        # init white color first to initialize colors correctly
        get_color(white, -1)

        self.stdscr = stdscr
        self.chats = chat_view
        self.msgs = msg_view
        self.status = status_view
        self.max_read = 2048

    def get_keys(self) -> Tuple[int, str]:
        keys = repeat_factor = ""

        for _ in range(MAX_KEYBINDING_LENGTH):
            ch = self.stdscr.getch()
            log.info("raw ch without unctrl: %s", ch)
            try:
                key = curses.unctrl(ch).decode()
            except Exception:
                log.warning("cant uncrtl: %s", ch)
                break
            if key.isdigit():
                repeat_factor += key
                continue
            keys += key
            # if match found or there are not any shortcut matches at all
            if all(
                p == keys or not p.startswith(keys)
                for p in MULTICHAR_KEYBINDINGS
            ):
                break

        return cast(int, num(repeat_factor, default=1)), keys or "UNKNOWN"


class StatusView:
    def __init__(self, stdscr: window) -> None:
        self.h = 1
        self.w = curses.COLS
        self.y = curses.LINES - 1
        self.x = 0
        self.stdscr = stdscr
        self.win = stdscr.subwin(self.h, self.w, self.y, self.x)
        self._refresh = self.win.refresh

    def resize(self, rows: int, cols: int):
        self.w = cols
        self.y = rows - 1
        self.win.resize(self.h, self.w)
        self.win.mvwin(self.y, self.x)

    def draw(self, msg: Optional[str] = None) -> None:
        self.win.clear()
        if not msg:
            return
        self.win.addstr(0, 0, msg[: self.w - 1])
        self._refresh()

    def get_input(self, msg="") -> str:
        self.draw(msg)
        curses.curs_set(1)

        buff = ""
        while True:
            log.info("here:")
            key = self.win.get_wch(0, min(len(buff) + len(msg), self.w - 1))
            key = ord(key)
            if key == 10:  # return
                break
            elif key == 127:  # del
                if buff:
                    buff = buff[:-1]
            elif key == 7:  # ^G cancel
                buff = ""
                break
            elif chr(key).isprintable():
                buff += chr(key)
            self.win.erase()
            line = (msg + buff)[-(self.w - 1) :]
            self.win.addstr(0, 0, line)

        self.win.clear()
        curses.curs_set(0)
        curses.cbreak()
        curses.noecho()
        return buff


class ChatView:
    def __init__(self, stdscr: window, p: float = 0.5) -> None:
        self.stdscr = stdscr
        self.h = 0
        self.w = 0
        self.win = stdscr.subwin(self.h, self.w, 0, 0)
        self._refresh = self.win.refresh

    def resize(self, rows: int, cols: int, p: float = 0.25) -> None:
        self.h = rows - 1
        self.w = round(cols * p)
        self.win.resize(self.h, self.w)

    def _msg_color(self, is_selected: bool = False) -> int:
        color = get_color(white, -1)
        if is_selected:
            return color | reverse
        return color

    def _unread_color(self, is_selected: bool = False) -> int:
        color = get_color(magenta, -1)
        if is_selected:
            return color | reverse
        return color

    def _chat_attributes(self, is_selected: bool = False) -> Tuple[int, ...]:
        attrs = (
            get_color(cyan, -1),
            get_color(blue, -1),
            self._msg_color(is_selected),
        )
        if is_selected:
            return tuple(attr | reverse for attr in attrs)
        return attrs

    def draw(self, current: int, chats: List[Dict[str, Any]]) -> None:
        self.win.erase()
        line = curses.ACS_VLINE  # type: ignore
        self.win.vline(0, self.w - 1, line, self.h)
        for i, chat in enumerate(chats):
            is_selected = i == current
            unread_count = chat["unread_count"]
            if chat["is_marked_as_unread"]:
                unread_count = "unread"

            date = get_date(chat)
            title = chat["title"]
            is_pinned = chat["is_pinned"]
            last_msg = get_last_msg(chat)
            offset = 0
            for attr, elem in zip(
                self._chat_attributes(is_selected), [f"{date} ", title]
            ):
                self.win.addstr(
                    i,
                    offset,
                    truncate_to_len(elem, max(0, self.w - offset - 1)),
                    attr,
                )
                offset += len(elem)

            last_msg = " " + last_msg.replace("\n", " ")
            last_msg = truncate_to_len(last_msg, max(0, self.w - offset))
            if last_msg.strip():
                self.win.addstr(
                    i, offset, last_msg, self._msg_color(is_selected)
                )

            if left_label := self._get_chat_label(
                unread_count, is_pinned, chat
            ):
                self.win.addstr(
                    i,
                    self.w - len(left_label) - 1,
                    left_label,
                    self._unread_color(is_selected),
                )

        self._refresh()

    @staticmethod
    def _get_chat_label(
        unread_count: int, is_pinned: bool, chat: Dict[str, Any]
    ) -> str:
        labels = []
        if is_pinned:
            labels.append("pinned")

        if chat["notification_settings"]["mute_for"]:
            labels.append("muted")

        if unread_count:
            labels.append(str(unread_count))

        label = " ".join(labels)
        if label:
            return f" {label}"
        return label


class MsgView:
    def __init__(
        self,
        stdscr: window,
        msg_model: MsgModel,
        users: UserModel,
        p: float = 0.5,
    ) -> None:
        self.msg_model = msg_model
        self.users = users
        self.stdscr = stdscr
        self.h = 0
        self.w = 0
        self.x = 0
        self.win = self.stdscr.subwin(self.h, self.w, 0, self.x)
        self._refresh = self.win.refresh

    def resize(self, rows: int, cols: int, p: float = 0.5) -> None:
        self.h = rows - 1
        self.w = round(cols * p)
        self.x = cols - self.w
        self.win.resize(self.h, self.w)
        self.win.mvwin(0, self.x)

    def _format_msg(
        self, msg_proxy: MsgProxy, user_id_item: int
    ) -> Tuple[str, bool]:
        msg = self._parse_msg(msg_proxy)
        reply_sender = None
        reply_to = msg_proxy.reply_msg_id
        if reply_to:
            reply_msg = MsgProxy(
                self.msg_model.get_message(msg_proxy.chat_id, reply_to)
            )
            reply_sender = self._get_user_by_id(reply_msg.sender_id)
            reply_msg_content = self._parse_msg(reply_msg)

        msg = msg.replace("\n", " ")
        if reply_to and reply_msg_content:
            reply_msg_content = reply_msg_content.replace("\n", " ")
            if len(reply_msg_content) > 68:
                # trimming old reply messages as it done in tg web & desktop
                reply_msg_content = f"{reply_msg_content[:65]}..."
            sender_text = f" {reply_sender}:" if reply_sender else ""
            msg = f">{sender_text} {reply_msg_content}\n{msg}"
        return msg, bool(reply_to)

    def _collect_msgs_to_draw(
        self,
        current_msg_idx: int,
        msgs: List[Tuple[int, Dict[str, Any]]],
        min_msg_padding: int,
    ) -> List[Tuple[Tuple[str, ...], bool, int]]:
        """
        Tries to collect list of messages that will satisfy `min_msg_padding`
        theshold. Long messages could prevent other messages from displaying on
        the screen. In order to prevent scenario when *selected* message moved
        out from the visible area of the screen by some long messages, this
        function will remove message one by one from the start until selected
        message could be visible on the screen.
        """
        selected_item_idx: Optional[int] = None
        collected_items: List[Tuple[Tuple[str, ...], bool, int]] = []
        for ignore_before in range(len(msgs)):
            if selected_item_idx is not None:
                break
            collected_items = []
            line_num = self.h
            for msg_idx, msg_item in msgs[ignore_before:]:
                is_selected_msg = current_msg_idx == msg_idx
                msg_proxy = MsgProxy(msg_item)
                dt = msg_proxy.date.strftime("%H:%M:%S")
                user_id_item = msg_proxy.sender_id

                msg, is_reply = self._format_msg(msg_proxy, user_id_item)
                user_id = self._get_user_by_id(user_id_item)

                # count wide character utf-8 symbols that take > 1 bytes to
                # print it causes invalid offset
                wide_char_len = sum(map(len, emoji_pattern.findall(msg)))
                elements = (f" {dt} ", user_id, " " + msg)
                total_len = sum(len(e) for e in elements) + wide_char_len

                needed_lines = (total_len // self.w) + 1 + int(is_reply)
                line_num -= needed_lines
                if line_num <= 0:
                    break
                collected_items.append((elements, is_selected_msg, line_num))
                if is_selected_msg:
                    selected_item_idx = len(collected_items) - 1
            if (
                # ignore first and last msg
                selected_item_idx not in (0, len(msgs) - 1, None)
                and selected_item_idx is not None
                and len(collected_items) - 1 - selected_item_idx
                < min_msg_padding
            ):
                selected_item_idx = None

        return collected_items

    def draw(
        self,
        current_msg_idx: int,
        msgs: List[Tuple[int, Dict[str, Any]]],
        min_msg_padding: int,
    ) -> None:
        self.win.erase()
        msgs_to_draw = self._collect_msgs_to_draw(
            current_msg_idx, msgs, min_msg_padding
        )

        if not msgs_to_draw:
            log.error("Can't collect message for drawing!")

        for elements, selected, line_num in msgs_to_draw:
            column = 0
            for attr, elem in zip(self._msg_attributes(selected), elements):
                if not elem:
                    continue
                self.win.addstr(line_num, column, elem, attr)
                column += len(elem)

        self._refresh()

    def _msg_attributes(self, is_selected: bool) -> Tuple[int, ...]:
        attrs = (
            get_color(cyan, -1),
            get_color(blue, -1),
            get_color(white, -1),
        )

        if is_selected:
            return tuple(attr | reverse for attr in attrs)
        return attrs

    def _get_user_by_id(self, user_id: int) -> str:
        if user_id == 0:
            return ""
        user = self.users.get_user(user_id)
        if user["first_name"] and user["last_name"]:
            return f'{user["first_name"]} {user["last_name"]}'[:20]

        if user["first_name"]:
            return f'{user["first_name"]}'[:20]

        if user.get("username"):
            return "@" + user["username"]
        return "Unknown?"

    def _parse_msg(self, msg: MsgProxy) -> str:
        if msg.is_message:
            return parse_content(msg["content"])
        log.debug("Unknown message type: %s", msg)
        return "unknown msg type: " + str(msg["content"])


def get_last_msg(chat: Dict[str, Any]) -> str:
    last_msg = chat.get("last_message")
    if not last_msg:
        return "<No messages yet>"
    content = last_msg["content"]
    return parse_content(content)


def get_date(chat: Dict[str, Any]) -> str:
    last_msg = chat.get("last_message")
    if not last_msg:
        return "<NA>"
    dt = datetime.fromtimestamp(last_msg["date"])
    if datetime.today().date() == dt.date():
        return dt.strftime("%H:%M")
    return dt.strftime("%d %b %y")


def parse_content(content: Dict[str, Any]) -> str:
    msg = MsgProxy({"content": content})
    if msg.is_text:
        return content["text"]["text"]

    if not msg.content_type:
        # not implemented
        _type = content["@type"]
        return f"[{_type}]"

    fields = dict(
        name=msg.file_name,
        duration=msg.duration,
        size=msg.human_size,
        download=get_download(msg.local, msg.size),
    )
    info = ", ".join(f"{k}={v}" for k, v in fields.items() if v)

    return f"[{msg.content_type}: {info}]"


def get_download(local, size):
    if local["is_downloading_completed"]:
        return "yes"
    elif local["is_downloading_active"]:
        d = local["downloaded_size"]
        percent = int(d * 100 / size)
        return f"{percent}%"
    return "no"
