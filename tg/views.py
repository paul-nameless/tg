import curses
import logging
from _curses import window  # type: ignore
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from tg import config
from tg.colors import (
    blue,
    bold,
    cyan,
    get_color,
    magenta,
    reverse,
    white,
    yellow,
)
from tg.models import Model, UserModel
from tg.msg import MsgProxy
from tg.tdlib import ChatType, get_chat_type
from tg.utils import emoji_pattern, get_color_by_str, num, truncate_to_len

log = logging.getLogger(__name__)

MAX_KEYBINDING_LENGTH = 5
MULTICHAR_KEYBINDINGS = (
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

    def resize(self, rows: int, cols: int) -> None:
        self.w = cols - 1
        self.y = rows - 1
        self.win.resize(self.h, self.w)
        self.win.mvwin(self.y, self.x)

    def draw(self, msg: Optional[str] = None) -> None:
        self.win.clear()
        if not msg:
            return
        self.win.addstr(0, 0, msg.replace("\n", " ")[: self.w])
        self._refresh()

    def get_input(self, msg: str = "") -> str:
        self.draw(msg)
        curses.curs_set(1)

        buff = ""
        while True:
            key = self.win.get_wch(0, min(len(buff) + len(msg), self.w - 1))
            key = ord(key)
            if key == 10:  # return
                break
            elif key == 127:  # del
                if buff:
                    buff = buff[:-1]
            elif key in (7, 27):  # (^G, <esc>) cancel
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
    def __init__(self, stdscr: window, model: Model) -> None:
        self.stdscr = stdscr
        self.h = 0
        self.w = 0
        self.win = stdscr.subwin(self.h, self.w, 0, 0)
        self._refresh = self.win.refresh
        self.model = model

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

    def _chat_attributes(
        self, is_selected: bool, title: str, user: Optional[str]
    ) -> Tuple[int, ...]:
        attrs = (
            get_color(cyan, -1),
            get_color(get_color_by_str(title), -1),
            get_color(get_color_by_str(user or ""), -1),
            self._msg_color(is_selected),
        )
        if is_selected:
            return tuple(attr | reverse for attr in attrs)
        return attrs

    def draw(
        self, current: int, chats: List[Dict[str, Any]], title: str = "Chats"
    ) -> None:
        self.win.erase()
        line = curses.ACS_VLINE  # type: ignore
        width = self.w - 1
        self.win.vline(0, width, line, self.h)
        self.win.addstr(
            0, 0, title.center(width)[:width], get_color(cyan, -1) | bold
        )

        for i, chat in enumerate(chats, 1):
            is_selected = i == current + 1
            date = get_date(chat)
            title = chat["title"]
            offset = 0

            last_msg_sender, last_msg = self._get_last_msg_data(chat)
            sender_label = f" {last_msg_sender}" if last_msg_sender else ""

            for attr, elem in zip(
                self._chat_attributes(is_selected, title, last_msg_sender),
                [f"{date} ", title, sender_label, f" {last_msg}"],
            ):
                if not elem:
                    continue
                item = truncate_to_len(elem, max(0, width - offset))
                if len(item) > 1:
                    self.win.addstr(i, offset, item, attr)
                    offset += len(elem) + sum(
                        map(len, emoji_pattern.findall(elem))
                    )

            if flags := self._get_flags(chat):
                flags_len = len(flags) + sum(
                    map(len, emoji_pattern.findall(flags))
                )
                self.win.addstr(
                    i,
                    max(0, width - flags_len),
                    flags[-width:],
                    self._unread_color(is_selected),
                )

        self._refresh()

    def _get_last_msg_data(
        self, chat: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        user, last_msg = get_last_msg(chat)
        if user:
            last_msg_sender = get_user_label(self.model.users, user)
            chat_type = get_chat_type(chat)
            if chat_type and chat_type.is_group(chat_type):
                return last_msg_sender, last_msg

        return None, last_msg

    def _get_flags(self, chat: Dict[str, Any]) -> str:
        flags = []

        msg = chat.get("last_message")
        if (
            msg
            and self.model.is_me(msg["sender_user_id"])
            and msg["id"] > chat["last_read_outbox_message_id"]
            and not self.model.is_me(chat["id"])
        ):
            # last msg haven't been seen by recipient
            flags.append("unseen")

        if action_label := _get_action_label(self.model.users, chat):
            flags.append(action_label)

        if self.model.users.is_online(chat["id"]):
            flags.append("online")

        if chat["is_pinned"]:
            flags.append("pinned")

        if chat["notification_settings"]["mute_for"]:
            flags.append("muted")

        if chat["is_marked_as_unread"]:
            flags.append("unread")
        elif chat["unread_count"]:
            flags.append(str(chat["unread_count"]))

        if get_chat_type(chat) == ChatType.chatTypeSecret:
            flags.append("secret")

        label = " ".join(config.CHAT_FLAGS.get(flag, flag) for flag in flags)
        if label:
            return f" {label}"
        return label


class MsgView:
    def __init__(self, stdscr: window, model: Model,) -> None:
        self.model = model
        self.stdscr = stdscr
        self.h = 0
        self.w = 0
        self.x = 0
        self.win = self.stdscr.subwin(self.h, self.w, 0, self.x)
        self._refresh = self.win.refresh
        self.states = {
            "messageSendingStateFailed": "failed",
            "messageSendingStatePending": "pending",
        }

    def resize(self, rows: int, cols: int, p: float = 0.5) -> None:
        self.h = rows - 1
        self.w = round(cols * p)
        self.x = cols - self.w
        self.win.resize(self.h, self.w)
        self.win.mvwin(0, self.x)

    def _get_flags(self, msg_proxy: MsgProxy) -> str:
        flags = []
        chat = self.model.chats.chats[self.model.current_chat]

        if msg_proxy.msg_id in self.model.selected[chat["id"]]:
            flags.append("selected")

        if msg_proxy.forward is not None:
            flags.append("forwarded")

        if (
            not self.model.is_me(msg_proxy.sender_id)
            and msg_proxy.msg_id > chat["last_read_inbox_message_id"]
        ):
            flags.append("new")
        elif (
            self.model.is_me(msg_proxy.sender_id)
            and msg_proxy.msg_id > chat["last_read_outbox_message_id"]
        ):
            if not self.model.is_me(chat["id"]):
                flags.append("unseen")
        if state := msg_proxy.msg.get("sending_state"):
            log.info("state: %s", state)
            state_type = state["@type"]
            flags.append(self.states.get(state_type, state_type))
        if msg_proxy.msg["edit_date"]:
            flags.append("edited")

        if not flags:
            return ""
        return " ".join(config.MSG_FLAGS.get(flag, flag) for flag in flags)

    def _format_reply_msg(
        self, chat_id: int, msg: str, reply_to: int, width_limit: int
    ) -> str:
        _msg = self.model.msgs.get_message(chat_id, reply_to)
        if not _msg:
            return msg
        reply_msg = MsgProxy(_msg)
        if reply_msg_content := self._parse_msg(reply_msg):
            reply_sender = get_user_label(
                self.model.users, reply_msg.sender_id
            )
            sender_name = f" {reply_sender}:" if reply_sender else ""
            reply_line = f">{sender_name} {reply_msg_content}"
            if len(reply_line) >= width_limit:
                reply_line = f"{reply_line[:width_limit - 4]}..."
            msg = f"{reply_line}\n{msg}"
        return msg

    def _format_url(self, msg_proxy: MsgProxy) -> str:
        if not msg_proxy.is_text or "web_page" not in msg_proxy.msg["content"]:
            return ""
        web = msg_proxy.msg["content"]["web_page"]
        name = web["site_name"]
        title = web["title"]
        description = web["description"].replace("\n", "")
        url = f"\n | {name}: {title}"
        if description:
            url += f"\n | {description}"
        return url

    def _format_msg(
        self, msg_proxy: MsgProxy, user_id_item: int, width_limit: int
    ) -> str:
        msg = self._parse_msg(msg_proxy)
        if caption := msg_proxy.caption:
            msg += "\n" + caption.replace("\n", " ")
        msg += self._format_url(msg_proxy)
        if reply_to := msg_proxy.reply_msg_id:
            msg = self._format_reply_msg(
                msg_proxy.chat_id, msg, reply_to, width_limit
            )
        return msg

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

                user_id = get_user_label(self.model.users, user_id_item)
                flags = self._get_flags(msg_proxy)
                if user_id and flags:
                    # if not channel add space between name and flags
                    flags = " " + flags
                label_elements = f" {dt} ", user_id, flags
                label_len = sum(len(e) for e in label_elements)

                msg = self._format_msg(
                    msg_proxy, user_id_item, width_limit=self.w - label_len - 1
                )
                elements = *label_elements, f" {msg}"
                needed_lines = 0
                for i, msg_line in enumerate(msg.split("\n")):
                    # count wide character utf-8 symbols that take > 1 bytes to
                    # print it causes invalid offset
                    emojies_count = sum(
                        map(len, emoji_pattern.findall(msg_line))
                    )
                    line_len = len(msg_line) + emojies_count
                    # first line cotains msg lable, e.g user name, date
                    if i == 0:
                        line_len += label_len

                    needed_lines += (line_len // self.w) + 1

                line_num -= needed_lines
                if line_num < 0:
                    tail_lines = needed_lines + line_num - 1
                    # try preview long message that did fit in the screen
                    if tail_lines > 0 and not is_selected_msg:
                        limit = self.w * tail_lines
                        tail_chatacters = len(msg) - limit - 3
                        elements = (
                            "",
                            "",
                            "",
                            f" ...{msg[tail_chatacters:]}",
                        )
                        collected_items.append((elements, is_selected_msg, 0))
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
        chat: Dict[str, Any],
    ) -> None:
        self.win.erase()
        msgs_to_draw = self._collect_msgs_to_draw(
            current_msg_idx, msgs, min_msg_padding
        )

        if not msgs_to_draw:
            log.error("Can't collect message for drawing!")

        for elements, selected, line_num in msgs_to_draw:
            column = 0
            user = elements[1]
            for attr, elem in zip(
                self._msg_attributes(selected, user), elements
            ):
                if not elem:
                    continue
                lines = (column + len(elem)) // self.w
                last_line = self.h == line_num + lines
                # work around agaist curses behaviour, when you cant write
                # char to the lower right coner of the window
                # see https://stackoverflow.com/questions/21594778/how-to-fill-to-lower-right-corner-in-python-curses/27517397#27517397
                if last_line:
                    start, stop = 0, self.w - column
                    for i in range(lines):
                        # insstr does not wraps long strings
                        self.win.insstr(
                            line_num + i,
                            column if not i else 0,
                            elem[start:stop],
                            attr,
                        )
                        start, stop = stop, stop + self.w
                else:
                    self.win.addstr(line_num, column, elem, attr)
                column += len(elem)

        self.win.addstr(
            0, 0, self._msg_title(chat), get_color(cyan, -1) | bold
        )
        self._refresh()

    def _msg_title(self, chat: Dict[str, Any]) -> str:
        chat_type = get_chat_type(chat)
        status = ""

        if action_label := _get_action_label(self.model.users, chat):
            status = action_label
        elif chat_type == ChatType.chatTypePrivate:
            status = self.model.users.get_status(chat["id"])
        elif chat_type == ChatType.chatTypeBasicGroup:
            if group := self.model.users.get_group_info(
                chat["type"]["basic_group_id"]
            ):
                status = f"{group['member_count']} members"
        elif chat_type == ChatType.chatTypeSupergroup:
            if supergroup := self.model.users.get_supergroup_info(
                chat["type"]["supergroup_id"]
            ):
                status = f"{supergroup['member_count']} members"
        elif chat_type == ChatType.channel:
            if supergroup := self.model.users.get_supergroup_info(
                chat["type"]["supergroup_id"]
            ):
                status = f"{supergroup['member_count']} subscribers"

        return f"{chat['title']}: {status}".center(self.w)[: self.w]

    def _msg_attributes(self, is_selected: bool, user: str) -> Tuple[int, ...]:
        attrs = (
            get_color(cyan, -1),
            get_color(get_color_by_str(user), -1),
            get_color(yellow, -1),
            get_color(white, -1),
        )

        if is_selected:
            return tuple(attr | reverse for attr in attrs)
        return attrs

    def _parse_msg(self, msg: MsgProxy) -> str:
        if msg.is_message:
            return parse_content(msg["content"])
        log.debug("Unknown message type: %s", msg)
        return "unknown msg type: " + str(msg["content"])


def get_last_msg(chat: Dict[str, Any]) -> Tuple[Optional[int], str]:
    last_msg = chat.get("last_message")
    if not last_msg:
        return None, "<No messages yet>"
    content = last_msg["content"]
    return last_msg["sender_user_id"], parse_content(content)


def get_date(chat: Dict[str, Any]) -> str:
    last_msg = chat.get("last_message")
    if not last_msg:
        return "<No date>"
    dt = datetime.fromtimestamp(last_msg["date"])
    date_fmt = "%d %b %y"
    if datetime.today().date() == dt.date():
        date_fmt = "%H:%M"
    elif datetime.today().year == dt.year:
        date_fmt = "%d %b"
    return dt.strftime(date_fmt)


def parse_content(content: Dict[str, Any]) -> str:
    msg = MsgProxy({"content": content})
    if msg.is_text:
        return content["text"]["text"].replace("\n", " ")

    _type = content["@type"]

    if _type == "messageBasicGroupChatCreate":
        return "[created the group]"
    if _type == "messageChatAddMembers":
        return "[joined the group]"

    if not msg.content_type:
        # not implemented
        return f"[{_type}]"

    content_text = ""
    if msg.is_poll:
        content_text = f"\n {msg.poll_question}"
        for option in msg.poll_options:
            content_text += f"\n * {option['voter_count']} ({option['vote_percentage']}%) | {option['text']}"

    fields = dict(
        name=msg.file_name,
        download=get_download(msg.local, msg.size),
        size=msg.human_size,
        duration=msg.duration,
        listened=format_bool(msg.is_listened),
        viewed=format_bool(msg.is_viewed),
        animated=msg.is_animated,
        emoji=msg.sticker_emoji,
        closed=msg.is_closed_poll,
    )
    info = ", ".join(f"{k}={v}" for k, v in fields.items() if v is not None)

    return f"[{msg.content_type}: {info}]{content_text}"


def format_bool(value: Optional[bool]) -> Optional[str]:
    if value is None:
        return None
    return "yes" if value else "no"


def get_download(
    local: Dict[str, Union[str, bool, int]], size: Optional[int]
) -> Optional[str]:
    if not size:
        return None
    elif local["is_downloading_completed"]:
        return "yes"
    elif local["is_downloading_active"]:
        d = int(local["downloaded_size"])
        percent = int(d * 100 / size)
        return f"{percent}%"
    return "no"


def get_user_label(users: UserModel, user_id: int) -> str:
    if user_id == 0:
        return ""
    user = users.get_user(user_id)
    if user["first_name"] and user["last_name"]:
        return f'{user["first_name"]} {user["last_name"]}'[:20]

    if user["first_name"]:
        return f'{user["first_name"]}'[:20]

    if user.get("username"):
        return "@" + user["username"]
    return "<Unknown>"


def _get_action_label(users: UserModel, chat: Dict[str, Any]) -> Optional[str]:
    actioner, action = users.get_user_action(chat["id"])
    if actioner and action:
        label = f"{action}..."
        chat_type = get_chat_type(chat)
        if chat_type and chat_type.is_group(chat_type):
            user_label = get_user_label(users, actioner)
            label = f"{user_label} {label}"

        return label

    return None
