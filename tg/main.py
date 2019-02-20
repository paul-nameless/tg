import logging
import logging.handlers
import os
import threading
from curses import wrapper
from functools import partial

from telegram.client import Telegram

from tg.controllers import Controller
from tg.models import Model
from tg.views import View

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            './tg.log',
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


def run(tg, stdscr):
    # run this function in thread?
    view = View(stdscr)
    model = Model(tg)
    controller = Controller(model, view)
    controller.tg = tg
    tg.add_message_handler(controller.update_handler)

    t = threading.Thread(
        target=controller.run,
    )
    t.start()
    t.join()


def main():
    logger.debug('#' * 64)
    tg = Telegram(
        api_id=API_ID,
        api_hash=API_HASH,
        phone=PHONE,
        database_encryption_key='changeme1234',
    )
    tg.login()

    # model = Model(tg)
    # print(model.get_me())
    # print(model.get_user(246785877))
    # print(model.chats.get_chat(77769955))
    # return

    wrapper(partial(run, tg))


if __name__ == '__main__':
    main()
