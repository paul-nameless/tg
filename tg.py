import curses
import logging
import logging.handlers
import math
import os
import re
import threading
from collections import defaultdict
from curses import wrapper
from datetime import datetime

from telegram.client import Telegram

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            './debug.log',
            backupCount=1,
            maxBytes=1024*256
        ),
    ]
)
logger = logging.getLogger(__name__)
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
PHONE = os.getenv('PHONE')
if PHONE is None:
    raise Exception('Environment variables did not provided')


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
    # return str(datetime.fromtimestamp(chat['last_message']['date']))
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


class ChatModel:

    def __init__(self, tg):
        self.tg = tg
        self.chats = []  # Dict[int, list]
        self.chat_ids = []

    def get_chats(self, offset=0, limit=10):
        if offset + limit < len(self.chats):
            # return data from cache
            return self.chats[offset:limit]

        self.get_chat_ids(
            offset=len(self.chats),
            limit=len(self.chats) + limit
        )
        for i in range(3):
            for chat_id in self.chat_ids:
                chat = self.get_chat(chat_id)
                self.chats.append(chat)
                logger.debug(
                    '#### %s: %s, %s', chat_id, chat, i)
            if len(self.chats) >= offset + limit:
                break

        return self.chats[offset:limit]

    def get_chat_ids(self, offset=0, limit=10):
        for i in range(3):
            if len(self.chats):
                result = self.tg.get_chats(
                    offset_chat_id=self.chats[-1]['id'],
                    limit=limit
                )
            else:
                result = self.tg.get_chats(
                    offset_order=2 ** 63 - 1,
                    offset_chat_id=offset,
                    limit=limit
                )

            result.wait()
            if result.error:
                logger.error(f'get chat ids error: {result.error_info}')
                return {}

            for chat_id in result.update['chat_ids']:
                self.chat_ids.append(chat_id)

            if len(self.chat_ids) >= offset + limit:
                break

        return self.chat_ids[offset:limit]

    def get_chat(self, chat_id):
        result = self.tg.get_chat(chat_id)
        result.wait()

        if result.error:
            logger.error(f'get chat error: {result.error_info}')
            return {}
        return result.update


class MsgModel:

    def __init__(self, tg):
        self.tg = tg
        self.msgs = defaultdict(list)  # Dict[int, list]

    def get_msgs(self, chat_id, offset=0, limit=10):
        if offset + limit < len(self.msgs[chat_id]):
            return sorted(self.msgs[chat_id], key=lambda d: d['id'])[::-1][offset:limit][::-1]

        for i in range(3):
            if len(self.msgs[chat_id]):
                result = self.tg.get_chat_history(
                    chat_id,
                    from_message_id=self.msgs[chat_id][-1]['id'],
                    limit=len(self.msgs[chat_id]) + limit
                )
            else:
                result = self.tg.get_chat_history(
                    chat_id,
                    offset=len(self.msgs[chat_id]),
                    limit=len(self.msgs[chat_id]) + limit
                )

            result.wait()
            for msg in result.update['messages']:
                self.msgs[chat_id].append(msg)
            if len(self.msgs[chat_id]) >= offset + limit:
                break

        return sorted(self.msgs[chat_id], key=lambda d: d['id'])[::-1][offset:limit][::-1]


class UserModel:

    def __init__(self, tg):
        self.tg = tg


class Model:

    def __init__(self, tg):
        self.chats = ChatModel(tg)
        self.msgs = MsgModel(tg)
        self.users = UserModel(tg)
        self.current_chat = 0

    def get_current_chat_id(self):
        return self.chats.chat_ids[self.current_chat]

    def next_chat(self):
        if self.current_chat < len(self.chats.chats):
            self.current_chat += 1
            return True
        return False

    def prev_chat(self):
        if self.current_chat > 0:
            self.current_chat -= 1
            return True
        return False

    def get_chats(self, offset=0, limit=10):
        return self.chats.get_chats(offset=offset, limit=limit)

    def get_current_msgs(self, offset=0, limit=10):
        chat_id = self.chats.chat_ids[self.current_chat]
        return self.msgs.get_msgs(
            chat_id, offset=offset, limit=limit
        )

    def send_msg(self, chat_id, msg):
        result = self.users.tg.send_message(
            chat_id=chat_id,
            text=msg,
        )

        result.wait()
        if result.error:
            logger.info(f'send message error: {result.error_info}')
        else:
            logger.info(f'message has been sent: {result.update}')


class View:

    def __init__(self, stdscr):
        curses.start_color()
        curses.echo()

        self.stdscr = stdscr
        self.chats = ChatView(stdscr)
        self.msgs = MsgView(stdscr)
        self.max_read = 2048

    def draw_chats(self, current, chats):
        self.chats.draw(current, chats)

    def draw_msgs(self, msgs):
        self.msgs.draw(msgs)

    def get_key(self):
        # return self.stdscr.getkey()
        _input = self.stdscr.getstr(
            self.msgs.h, self.chats.w, self.max_read).decode()
        # self.stdscr.addstr(self.msgs.h, self.chats.w, ' ' * self.msgs.w-10)
        # self.chats.win.addstr(self.msgs.h, self.chats.w +
        #                       5, ' ' * self.msgs.w-10)
        return _input


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
        self.win.vline(0, self.w-1, curses.ACS_VLINE, self.h)
        for i, chat in enumerate(chats):
            msg = f'{i:>2} {get_date(chat)} {chat["title"]} {chat["unread_count"]}: {get_last_msg(chat)}'
            msg = emoji_pattern.sub(r'', msg)[:self.w-1]
            # msg = msg.encode('utf-8').decode('ascii', 'ignore')[:self.w-1]
            if i == current:
                self.win.addstr(i, 0, msg, curses.color_pair(1))
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

    def draw(self, msgs):
        self.win.clear()
        count = 0

        for msg in msgs:
            logger.debug('##########: %s', msg)
            s = self._parse_msg(msg)
            s = s.replace('\n', ' ')
            offset = math.ceil(len(s) / self.w)
            if count + offset > self.h-1:
                logger.warning('Reched end of lines')
                break
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


class Controller:
    """
    # MVC
    # Model is data from telegram
    # Controller handles keyboad events
    # View is terminal vindow
    """

    def __init__(self, model, view):
        self.model = model
        self.view = view
        self.lock = threading.Lock()

    def init(self):
        self.view.draw_chats(
            self.model.current_chat,
            self.model.get_chats()
        )
        msgs = self.model.get_current_msgs()
        self.view.draw_msgs(msgs)

    def run(self):
        while True:
            key = self.view.get_key()
            logger.info('Pressed key: %s', key)
            if key == '/q':
                return
            elif key == '/j':
                is_changed = self.model.next_chat()
                logger.info('Is changed: %s', is_changed)
                if is_changed:
                    self.view.draw_chats(
                        self.model.current_chat,
                        self.model.get_chats()
                    )
                    msgs = self.model.get_current_msgs()
                    self.view.draw_msgs(msgs)
            elif key == '/k':
                is_changed = self.model.prev_chat()
                if is_changed:
                    self.view.draw_chats(
                        self.model.current_chat,
                        self.model.get_chats()
                    )
                    msgs = self.model.get_current_msgs()
                    self.view.draw_msgs(msgs)
            elif not key.startswith('/'):
                chat_id = self.model.get_current_chat_id()
                self.model.send_msg(chat_id, key)
                self.view.draw_chats(
                    self.model.current_chat,
                    self.model.get_chats()
                )
                msgs = self.model.get_current_msgs()
                self.view.draw_msgs(msgs)

    def update_handler(self, update):
        logger.debug('===============Received: %s', update)
        _type = update['@type']
        if _type == 'updateNewMessage':
            logger.debug('Updating... new message')
            # with self.lock:
            chat_id = update['message']['chat_id']
            self.model.msgs.msgs[chat_id].append(update['message'])
            msgs = self.model.get_current_msgs()
            self.view.draw_msgs(msgs)
        # message_content = update['message']['content'].get('text', {})
        # we need this because of different message types: photos, files, etc.
        # message_text = message_content.get('text', '').lower()

        # if message_text == 'ping':
        #     chat_id = update['message']['chat_id']
        #     # print(f'Ping has been received from {chat_id}')
        #     self.tg.send_message(
        #         chat_id=chat_id,
        #         text='pong',
        #     )


def main(stdscr):
    logger.info('#' * 64)
    tg = Telegram(
        api_id=API_ID,
        api_hash=API_HASH,
        phone=PHONE,
        database_encryption_key='changeme1234',
    )
    tg.login()

    view = View(stdscr)
    model = Model(tg)
    controller = Controller(model, view)
    controller.tg = tg
    controller.init()

    t = threading.Thread(
        target=controller.run,
    )
    t.start()
    t.join()


if __name__ == '__main__':
    wrapper(main)
