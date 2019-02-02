import logging
import logging.handlers
import os
import threading
from curses import wrapper

from telegram.client import Telegram

from controller import Controller
from model import Model
from view import View

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


def main(stdscr):
    logger.debug('#' * 64)
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
    tg.add_message_handler(controller.update_handler)

    t = threading.Thread(
        target=controller.run,
    )
    t.start()
    t.join()


if __name__ == '__main__':
    wrapper(main)
