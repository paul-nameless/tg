import logging
import logging.handlers
import os
import threading
from curses import wrapper, window
from functools import partial

from telegram.client import Telegram

from tg.controllers import Controller
from tg.models import Model
from tg.views import View

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "DEBUG"),
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            "./tg.log", backupCount=1, maxBytes=1024 * 256
        ),
    ],
)

log = logging.getLogger(__name__)
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")
if PHONE is None:
    raise Exception("Environment variables did not provided")


def run(tg: Telegram, stdscr: window) -> None:
    # run this function in thread?
    view = View(stdscr)
    model = Model(tg)
    controller = Controller(model, view, tg)
    for msg_type, handler in controller.handlers.items():
        tg.add_update_handler(msg_type, handler)

    t = threading.Thread(target=controller.run,)
    t.start()
    t.join()


class TelegramApi(Telegram):
    def download_file(
        self, file_id, priority=16, offset=0, limit=0, synchronous=False,
    ):
        result = self.call_method(
            "downloadFile",
            params=dict(
                file_id=file_id,
                priority=priority,
                offset=offset,
                limit=limit,
                synchronous=synchronous,
            ),
            block=False,
        )
        result.wait()


def main():
    log.debug("#" * 64)
    tg = TelegramApi(
        api_id=API_ID,
        api_hash=API_HASH,
        phone=PHONE,
        database_encryption_key="changeme1234",
        files_directory=os.path.expanduser("~/.cache/tg/"),
        tdlib_verbosity=0,
        # TODO: add in config
        library_path="/usr/local/Cellar/tdlib/1.6.0/lib/libtdjson.dylib",
    )
    tg.login()
    wrapper(partial(run, tg))


if __name__ == "__main__":
    main()
