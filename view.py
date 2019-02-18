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
        try:
            return curses.unctrl(ch).decode()
        except UnicodeDecodeError:
            logger.warning('cant uncrtl: %s', ch)
            return 'UNKNOWN'

    def get_key_input(self, y, x):
        ch = self.msgs.win.getch(y, x)
        logger.info('raw ch without unctrl in msgs: %s', ch)
        return ch
        # return curses.unctrl(ch).decode()

    def get_input(self):
        curses.curs_set(1)

        buff = ''
        while True:
            key = self.msgs.win.get_wch(
                self.msgs.h-1, min(len(buff), self.msgs.w-1))
            key = ord(key)
            logger.info('Pressed in send msg: "%s"', key)
            # try:
            logger.info('Trying to chr: %s', chr(key))
            # except ValueError:
            # logger.exception()
            if key == 10:
                logger.info('Sending msg: %s', buff)
                break
            elif key == 127:
                if buff:
                    buff = buff[:-1]
            elif key == 7:
                logger.info('Not Sending msg: %s', buff)
                buff = None
                break
            elif chr(key).isprintable():
                buff += chr(key)
            if len(buff) >= self.msgs.w:
                start = len(buff) - self.msgs.w
                buff_wrapped = buff[start+1:]
            else:
                buff_wrapped = (buff + ' ' * (self.msgs.w -
                                              len(buff) - 1))
            self.msgs.win.addstr(self.msgs.h-1, 0, buff_wrapped)
            self.msgs.win.move(self.msgs.h-1, min(len(buff), self.msgs.w-1))

        curses.curs_set(0)
        return buff


class StatusView:

    def __init__(self, stdscr):
        # self.stdscr = stdscr
        pass

    def resize(self):
        pass

    def draw(self, msg):
        # draw msg on the last line
        pass


emoji_pattern = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE
)


class ChatView:
    def __init__(self, stdscr, p=0.5):
        self.h = 0
        self.w = 0
        self.win = stdscr.subwin(self.h, self.w, 0, 0)
        # self.win.scrollok(True)
        # self.win.idlok(True)

    def resize(self, p=0.25):
        self.h = curses.LINES - 1
        self.w = int((curses.COLS - 1) * p)
        self.win.resize(self.h, self.w)

    def draw(self, current, chats):
        self.win.clear()
        # self.win.vline(0, self.w-1, curses.ACS_VLINE, self.h)
        for i, chat in enumerate(chats):
            msg = f'{get_date(chat)} {chat["title"]} [{chat["unread_count"]}]: {get_last_msg(chat)}'
            msg = emoji_pattern.sub(r'', msg)[:self.w-1]
            # msg = msg[:self.w-1]
            if len(msg) < self.w:
                msg += ' ' * (self.w - len(msg) - 1)
            if i == current:
                self.win.addstr(i, 0, msg, curses.A_REVERSE)
                continue
            self.win.addstr(i, 0, msg)

        self.win.refresh()


class MsgView:
    def __init__(self, stdscr, p=0.5):
        self.stdscr = stdscr
        # self.h = curses.LINES - 1
        # self.w = curses.COLS - int((curses.COLS - 1) * p)
        # self.x = curses.COLS - self.w
        self.h = 0
        self.w = 0
        # self.x = curses.COLS - (curses.COLS - int((curses.COLS - 1) * p))
        self.x = 0
        # self.win = stdscr.subwin(self.h, self.w, 0, self.x)
        self.win = None
        # self.win.scrollok(True)
        # self.win.idlok(True)
        self.lines = 0

    def resize(self, p=0.5):
        self.h = curses.LINES - 1
        self.w = curses.COLS - int((curses.COLS - 1) * p)
        self.x = curses.COLS - self.w

        # if self.win is None:
        self.win = self.stdscr.subwin(self.h, self.w, 0, self.x)
        # else:
        # self.win.resize(self.h, self.w)
        # self.win.mvwin(0, self.x)

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
