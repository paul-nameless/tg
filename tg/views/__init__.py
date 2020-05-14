import curses
import logging
import re
from _curses import window
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Iterator

from tg.colors import blue, cyan, get_color, magenta, reverse, white
from tg.msg import MsgProxy
from tg.utils import num

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
    def __init__(self, stdscr: window) -> None:
        curses.start_color()
        curses.noecho()
        curses.cbreak()
        stdscr.keypad(True)
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()

        self.stdscr = stdscr
        self.chats = ChatView(stdscr)
        self.msgs = MsgView(stdscr)
        self.status = StatusView(stdscr)
        self.max_read = 2048

    def get_keys(self, y: int, x: int) -> Tuple[int, str]:
        keys = repeat_factor = ""

        for _ in range(MAX_KEYBINDING_LENGTH):
            ch = self.stdscr.getch(y, x)
            log.info("raw ch without unctrl: %s", ch)
            try:
                key = curses.unctrl(ch).decode()
            except UnicodeDecodeError:
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

        return num(repeat_factor, default=1), keys or "UNKNOWN"


class StatusView:
    def __init__(self, stdscr: window) -> None:
        self.h = 1
        self.w = curses.COLS
        self.y = curses.LINES - 1
        self.x = 0
        self.win = stdscr.subwin(self.h, self.w, self.y, self.x)
        self._refresh = self.win.refresh

    def resize(self):
        self.w = curses.COLS
        self.y = curses.LINES - 1
        self.win.resize(self.h, self.w)
        self.win.wmove(self.y, self.x)

    def draw(self, msg: Optional[str] = None) -> None:
        self.win.clear()
        if not msg:
            return
        self.win.addstr(0, 0, msg[: self.w - 1])
        self._refresh()

    def get_input(self, msg="") -> Optional[str]:
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
                buff = None
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
        self.h = 0
        self.w = 0
        self.win = stdscr.subwin(self.h, self.w, 0, 0)
        self._refresh = self.win.refresh

    def resize(self, p: float = 0.25) -> None:
        self.h = curses.LINES - 1
        self.w = round(curses.COLS * p)
        self.win.resize(self.h, self.w)

    def _msg_color(self, is_selected: bool = False) -> int:
        return get_color(white, -1) | (reverse if is_selected else 0)

    def _unread_color(self, is_selected: bool = False) -> int:
        return get_color(magenta, -1) | (reverse if is_selected else 0)

    def _msg_attribures(self, is_selected: bool = False) -> List[int]:
        return map(
            lambda x: x | (reverse if is_selected else 0),
            [get_color(cyan, -1), get_color(blue, -1), self._msg_color(),],
        )

    def draw(self, current: int, chats: List[Dict[str, Any]]) -> None:
        self.win.erase()
        self.win.vline(0, self.w - 1, curses.ACS_VLINE, self.h)
        for i, chat in enumerate(chats):
            is_selected = i == current
            date, title, unread_count, last_msg = (
                get_date(chat),
                chat["title"],
                chat["unread_count"],
                get_last_msg(chat),
            )
            offset = 0
            for attr, elem in zip(
                self._msg_attribures(is_selected), [f"{date} ", title]
            ):
                if offset > self.w:
                    break
                self.win.addstr(i, offset, elem[: self.w - offset - 1], attr)
                offset += len(elem)

            if offset >= self.w:
                continue

            last_msg = " " + last_msg.replace("\n", " ")
            wide_char_len = sum(map(len, emoji_pattern.findall(last_msg)))
            last_msg = last_msg[: self.w - offset - 1 - wide_char_len]

            # log.info(f"4242, {i=}, {offset=} {len(last_msg)=}")
            self.win.addstr(i, offset, last_msg, self._msg_color(is_selected))

            if left_label := self._get_chat_label(unread_count, chat):
                self.win.addstr(
                    i,
                    self.w - len(left_label) - 1,
                    left_label,
                    self._unread_color(is_selected),
                )

        self._refresh()

    @staticmethod
    def _get_chat_label(unread_count: int, chat: Dict[str, Any]) -> str:
        label = ""
        if unread_count:
            label = f"{unread_count} "

        if chat["notification_settings"]["mute_for"]:
            label = f"muted {label}"

        return f" {label}"


class MsgView:
    def __init__(self, stdscr: window, p: float = 0.5) -> None:
        self.stdscr = stdscr
        self.h = 0
        self.w = 0
        self.x = 0
        self.win = self.stdscr.subwin(self.h, self.w, 0, self.x)
        self._refresh = self.win.refresh

    def resize(self, p: float = 0.5) -> None:
        self.h = curses.LINES - 1
        self.w = round(curses.COLS * p)
        self.x = curses.COLS - self.w
        self.win.resize(self.h, self.w)
        self.win.mvwin(0, self.x)

    def draw(self, current: int, msgs: Any) -> None:
        self.win.erase()
        line_num = self.h

        for i, msg in enumerate(msgs):
            dt, user_id, msg = self._parse_msg(msg)
            user_id = self._get_user_by_id(user_id)
            msg = msg.replace("\n", " ")
            # count wide character utf-8 symbols that take > 1 bytes to print
            # it causes invalid offset
            wide_char_len = sum(map(len, emoji_pattern.findall(msg)))
            elements = (" {} ".format(dt), user_id, " " + msg)
            total_len = sum(len(e) for e in elements) + wide_char_len
            needed_lines = (total_len // self.w) + 1
            line_num -= needed_lines
            if line_num <= 0:
                break

            attrs = [
                get_color(cyan, -1),
                get_color(blue, -1),
                get_color(white, -1),
            ]
            if i == current:
                attrs = [attr | reverse for attr in attrs]

            column = 0
            for attr, elem in zip(attrs, elements):
                if not elem:
                    continue
                self.win.addstr(line_num, column, elem, attr)
                column += len(elem)

        self._refresh()

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

    def _parse_msg(self, msg: Dict[str, Any]) -> Tuple[str, int, str]:
        dt = datetime.fromtimestamp(msg["date"]).strftime("%H:%M:%S")
        _type = msg["@type"]
        if _type == "message":
            return dt, msg["sender_user_id"], parse_content(msg["content"])
        log.debug("Unknown message type: %s", msg)
        return (
            dt,
            msg["sender_user_id"],
            "unknown msg type: " + str(msg["content"]),
        )


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

    if not msg.type:
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

    return f"[{msg.type}: {info}]"


def get_download(local, size):
    if local["is_downloading_completed"]:
        return "yes"
    elif local["is_downloading_active"]:
        d = local["downloaded_size"]
        percent = int(d * 100 / size)
        return f"{percent}%"
    return "no"


emoji_pattern = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)
