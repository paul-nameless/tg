import curses
import logging
import math
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class View:

    def __init__(self, stdscr):
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
        self.max_read = 2048

    def draw_chats(self, current, chats):
        self.chats.draw(current, chats)

    def draw_msgs(self, current, msgs):
        self.msgs.draw(current, msgs)

    def get_key(self, y, x):
        # return self.stdscr.getkey()

        ch = self.stdscr.getch(y, x)
        logger.info('raw ch without unctrl: %s', ch)
        return curses.unctrl(ch).decode()

        # self.stdscr.addstr(self.msgs.h, self.chats.w, ' ' * self.msgs.w-10)
        # self.chats.win.addstr(self.msgs.h, self.chats.w +
        #                       5, ' ' * self.msgs.w-10)

        # _input = self.stdscr.getstr(
        #     self.msgs.h, self.chats.w, self.max_read).decode()
        # return _input


emoji_pattern = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "]+",
    flags=re.UNICODE
)


class ChatView:
    def __init__(self, stdscr):
        self.h = curses.LINES - 1
        self.w = int((curses.COLS - 1) * 0.25)
        self.win = stdscr.subwin(self.h, self.w, 0, 0)

    def draw(self, current, chats):
        self.win.clear()
        # self.win.vline(0, self.w-1, curses.ACS_VLINE, self.h)
        for i, chat in enumerate(chats):
            msg = f'{get_date(chat)} {chat["title"]} {chat["unread_count"]}: {get_last_msg(chat)}'
            msg = emoji_pattern.sub(r'', msg)[:self.w-1]
            if len(msg) < self.w:
                msg += ' ' * (self.w - len(msg) - 1)
            if i == current:
                self.win.addstr(i, 0, msg, curses.A_REVERSE)
                continue
            self.win.addstr(i, 0, msg)

        self.win.refresh()


class MsgView:
    def __init__(self, stdscr):
        self.h = curses.LINES - 1
        self.w = curses.COLS - int((curses.COLS - 1) * 0.25)
        self.s = curses.COLS - self.w
        self.win = stdscr.subwin(self.h, self.w, 0, self.s)
        self.lines = 0

    def draw(self, current, msgs):
        logger.info('Dwaring msgs')
        self.win.clear()
        count = 0
        current = len(msgs) - current - 1

        for i, msg in enumerate(msgs):
            s = self._parse_msg(msg)
            s = s.replace('\n', ' ')
            if len(s) < self.w:
                s += ' ' * (self.w - len(s) - 1)
            offset = math.ceil(len(s) / self.w)
            if count + offset > self.h-1:
                logger.warning('Reched end of lines')
                break
            if i == current:
                self.win.addstr(count, 0, s, curses.A_REVERSE)
            else:
                self.win.addstr(count, 0, s)
            count += offset

        self.lines = count
        self.win.refresh()

    def _parse_msg(self, msg):
        dt = datetime.fromtimestamp(
            msg['date']).strftime("%H:%M:%S")
        _type = msg['@type']
        if _type == 'message':
            return "{} {}: {}".format(
                dt,
                msg['sender_user_id'],
                parse_content(msg['content'])
            )
        logger.debug('Unknown message type: %s', msg)
        return 'unknown msg type: ' + str(msg['content'])


def get_last_msg(chat):
    content = chat['last_message']['content']
    _type = content['@type']
    if _type == 'messageText':
        return content['text']['text']
    elif _type == 'messageVoiceNote':
        return '[voice msg]'
    else:
        logger.error(chat)
        return f'[unknown type {_type}]'


def get_date(chat):
    dt = datetime.fromtimestamp(chat['last_message']['date'])
    if datetime.today().date() == dt.date():
        return dt.strftime("%H:%M")
    return dt.strftime("%d/%b/%y")


def parse_content(content):
    _type = content['@type']
    if _type == 'messageText':
        return content['text']['text']
    elif _type == 'messageVoiceNote':
        return '[voice msg]'
    else:
        logger.debug('Unknown content: %s', content)
        return f'[unknown type {_type}]'


emoji_pattern = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "]+",
    flags=re.UNICODE
)
