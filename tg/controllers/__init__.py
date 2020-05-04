import logging
import os
import threading

from utils import notify

log = logging.getLogger(__name__)

SUPPORTED_MSG_TYPES = "updateNewMessage", "updateChatLastMessage"


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

    def run(self):
        try:
            self.handle_chats()
        except Exception as e:
            log.exception('Error happened in main loop')

    def handle_msgs(self):
        # set width to 0.25, move window to left
        # refresh everything
        self.view.chats.resize(0.2)
        self.view.msgs.resize(0.2)
        self.refresh_chats()

        while True:

            repeat_factor, keys = self.view.get_keys(self.view.chats.h, self.view.chats.w)
            log.info('Pressed keys: %s', keys)
            if keys == 'q':
                return 'QUIT'
            elif keys == ']':
                if self.model.next_chat():
                    self.refresh_chats()
            elif keys == '[':
                if self.model.prev_chat():
                    self.refresh_chats()
            elif keys == 'J':
                if self.model.jump_next_msg():
                    self.refresh_msgs()
            elif keys == 'K':
                if self.model.jump_prev_msg():
                    self.refresh_msgs()
            elif keys in ('j', '^B'):
                if self.model.next_msg(repeat_factor):
                    self.refresh_msgs()
            elif keys in ('k', '^C'):
                if self.model.prev_msg(repeat_factor):
                    self.refresh_msgs()
            elif keys == 'G':
                if self.model.jump_bottom():
                    self.refresh_msgs()

            elif keys == '/':
                # search
                pass
            elif keys == 'gg':
                # move to the top
                pass
            elif keys == 'e':
                # edit msg
                pass
            elif keys == 'r':
                # reply to this msg
                # print to status line
                pass
            elif keys == 'I':
                # open vim or emacs to write long messages
                pass
            elif keys == 'i':
                # write new message
                msg = self.view.get_input()
                if msg:
                    self.model.send_message(text=msg)
                    self.view.draw_status(f'Sent: {msg}')

            elif keys in ('h', '^D'):
                return 'BACK'

    def handle_chats(self):
        # set width to 0.5, move window to center?
        # refresh everything
        self.view.chats.resize(0.5)
        self.view.msgs.resize(0.5)
        self.refresh_chats()
        while True:

            repeat_factor, keys = self.view.get_keys(self.view.chats.h, self.view.chats.w)
            log.info('Pressed keys: %s', keys)
            if keys == 'q':
                return
            elif keys in ('l', '^E'):
                rc = self.handle_msgs()
                if rc == 'QUIT':
                    return
                self.view.chats.resize(0.5)
                self.view.msgs.resize(0.5)
                self.refresh_chats()

            elif keys in ('j', '^B'):
                is_changed = self.model.next_chat(repeat_factor)
                if is_changed:
                    self.refresh_chats()

            elif keys in ('k', '^C'):
                is_changed = self.model.prev_chat(repeat_factor)
                if is_changed:
                    self.refresh_chats()

            elif keys == 'gg':
                is_changed = self.model.first_chat()
                if is_changed:
                    self.refresh_chats()

    def refresh_chats(self):
        with self.lock:
            # using lock here, because refresh_chats is used from another
            # thread
            self.view.draw_chats(
                self.model.current_chat,
                self.model.get_chats(limit=self.view.chats.h)
            )
            self.refresh_msgs()
            self.view.draw_status()

    def refresh_msgs(self):
        self.view.msgs.users = self.model.users
        msgs = self.model.get_current_msgs(limit=self.view.msgs.h)
        self.view.draw_msgs(self.model.get_current_msg(), msgs)

    def update_handler(self, update):
        try:
            _type = update['@type']
            log.info('===Received %s type: %s', _type, update)
            if _type == 'updateNewMessage':
                # with self.lock():
                chat_id = update['message']['chat_id']
                self.model.msgs.msgs[chat_id].append(update['message'])
                # msgs = self.model.get_current_msgs()
                self.refresh_msgs()
                if not update.get('disable_notification'):
                    if update['message']['content'] == 'text':
                        notify(update['message']['content']['text']['text'])
            elif _type == 'updateChatLastMessage':
                log.info("Proccessing updateChatLastMessage")
                chat_id = update['chat_id']
                message = update['last_message']
                self.model.chats.update_last_message(chat_id, message)
                self.refresh_chats()

        except Exception:
            log.exception("Error happened in update_handler")
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
