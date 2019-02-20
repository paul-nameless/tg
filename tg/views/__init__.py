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

        # default
        curses.init_pair(1, -1, -1)
        curses.init_pair(2, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_BLUE, -1)
        curses.init_pair(4, curses.COLOR_MAGENTA, -1)
        curses.init_pair(5, curses.COLOR_YELLOW, -1)
        curses.init_pair(6, curses.COLOR_BLACK, -1)

        # selection
        curses.init_pair(7, -1, curses.COLOR_BLACK)
        curses.init_pair(8, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(9, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(10, curses.COLOR_MAGENTA, curses.COLOR_BLACK)

        self.stdscr = stdscr
        self.chats = ChatView(stdscr)
        self.msgs = MsgView(stdscr)
        self.status = StatusView(stdscr)
        self.max_read = 2048

    def draw_chats(self, current, chats):
        self.chats.draw(current, chats)

    def draw_status(self, msg=None):
        self.status.draw(msg)

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
        return self.status.get_input()


class StatusView:

    def __init__(self, stdscr):
        self.h = 1
        self.w = curses.COLS
        self.y = curses.LINES - 1
        self.x = 0
        self.win = stdscr.subwin(self.h, self.w, self.y, self.x)

    def resize(self):
        self.w = curses.COLS
        self.y = curses.LINES - 1
        self.win.resize(self.h, self.w)
        self.win.wmove(self.y, self.x)

    def draw(self, msg):
        # msg = '-' * (self.w - 1)
        # msg = '>'
        if not msg:
            msg = 'Status'
        self.win.addstr(0, 0, msg[:self.w])
        self.win.refresh()

    def get_input(self):
        curses.curs_set(1)
        self.win.clear()

        buff = ''
        while True:
            key = self.win.get_wch(0, min(len(buff), self.w-1))
            key = ord(key)
            logger.info('Pressed in send msg: "%s"', key)
            # try:
            logger.info('Trying to chr: %s', chr(key))
            # except ValueError:
            # logger.exception()
            if key == 10:  # return
                logger.info('Sending msg: %s', buff)
                break
            elif key == 127:  # del
                if buff:
                    buff = buff[:-1]
            elif key == 7:  # ^G cancel
                logger.info('Not Sending msg: %s', buff)
                buff = None
                break
            elif chr(key).isprintable():
                buff += chr(key)
            if len(buff) >= self.w:
                start = len(buff) - self.w
                buff_wrapped = buff[start+1:]
            else:
                buff_wrapped = (buff + ' ' * (self.w -
                                              len(buff) - 1))
            self.win.addstr(0, 0, buff_wrapped)
            self.win.move(0, min(len(buff), self.w-1))

        curses.curs_set(0)
        return buff


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
            # msg = f' {get_date(chat)} {chat["title"]} [{chat["unread_count"]}]: {get_last_msg(chat)}'
            date, title, unread, last_msg = get_date(
                chat), chat["title"], chat["unread_count"], get_last_msg(chat)
            # msg = emoji_pattern.sub(r'', msg)[:self.w-1]
            # last_msg = emoji_pattern.sub(r'', msg)[:self.w-2] + ' '
            last_msg = emoji_pattern.sub(r'', last_msg)
            # msg = msg[:self.w-1]
            # if len(msg) < self.w:
            #     msg += ' ' * (self.w - len(msg) - 1)

            if i == current:
                colors = [8, 9, 7, 10]
            else:
                colors = [2, 3, 1, 4]

            offset = 0
            j = 0
            # for color, e in zip(colors, msg.split(' ', maxsplit=3)):
            for color, e in zip(colors, [' ' + date, title]):
                attr = curses.color_pair(color)
                if offset > self.w:
                    break
                j += 1
                if j < 4:
                    e = e + ' '
                self.win.addstr(i, offset, e[:self.w-offset-1], attr)
                offset += len(e)

            if offset >= self.w:
                continue

            attr = curses.color_pair(colors[-2])
            msg = last_msg[:self.w-offset-1]

            # msg = msg[:self.w-1]
            if len(msg) < self.w:
                msg += ' ' * (self.w - offset - len(msg) - 1)

            self.win.addstr(i, offset, msg, attr)

            if unread:
                attr = curses.color_pair(colors[-1])
                unread = ' ' + str(unread) + ' '
                self.win.addstr(i, self.w - len(unread) - 1, unread, attr)

            # if i == current:
            #     # attr = curses.A_REVERSE | curses.color_pair(1)
            #     attr = curses.A_REVERSE
            #     self.win.addstr(i, 0, msg, attr)
            #     continue
            # self.win.addstr(i, 0, msg)

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
        self.lines = 0

    def resize(self, p=0.5):
        self.h = curses.LINES - 1
        self.w = curses.COLS - int((curses.COLS - 1) * p)
        self.x = curses.COLS - self.w

        # if self.win is None:
        self.win = self.stdscr.subwin(self.h, self.w, 0, self.x)
        # self.win.scrollok(True)
        # self.win.idlok(True)
        # else:
        # self.win.resize(self.h, self.w)
        # self.win.mvwin(0, self.x)

    def draw(self, current, msgs):
        # logger.info('Dwaring msgs')
        self.win.clear()
        count = self.h

        for i, msg in enumerate(msgs):
            # s = self._parse_msg(msg)
            dt, user_id, msg = self._parse_msg(msg)
            user_id = self._get_user_by_id(user_id)
            msg = msg.replace('\n', ' ')
            s = ' '.join([' ' + dt, user_id, msg])
            # s = s.replace('\n', ' ')
            # if len(s) < self.w:
            #     s += ' ' * (self.w - len(s) - 1)
            offset = math.ceil((len(s) - 1) / self.w)
            count -= offset
            if count <= 0:
                # logger.warning('Reched end of lines')
                break

            if i == current:
                colors = [7, 8, 9, 7]
            else:
                colors = [1, 2, 3, 1]

            offset = 0
            j = 0
            for color, e in zip(colors, s.split(' ', maxsplit=3)):
                attr = curses.color_pair(color)
                j += 1
                if j < 4:
                    e = e + ' '
                # logger.info('####: %s', (e, offset, count))
                self.win.addstr(count, offset, e, attr)
                offset += len(e)

        self.win.refresh()

    def _get_user_by_id(self, user_id):
        if user_id == 0:
            return ''
        user = self.users.get_user(user_id)
        if user["first_name"] and user["last_name"]:
            return f'{user["first_name"]} {user["last_name"]}'[:20]

        if user["first_name"]:
            return f'{user["first_name"]}'[:20]

        if user.get('username'):
            return '@' + user['username']
        return 'Unknown?'

    def _parse_msg(self, msg):
        dt = datetime.fromtimestamp(
            msg['date']).strftime("%H:%M:%S")
        _type = msg['@type']
        if _type == 'message':
            return dt, msg['sender_user_id'], parse_content(msg['content'])
        logger.debug('Unknown message type: %s', msg)
        return dt, msg['sender_user_id'], 'unknown msg type: ' + str(msg['content'])


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
        return f'[unknown content type {_type}]'


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
