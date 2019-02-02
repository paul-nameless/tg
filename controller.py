import logging
import threading

logger = logging.getLogger(__name__)


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
