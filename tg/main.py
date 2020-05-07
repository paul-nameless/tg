import logging
import logging.handlers
import threading
from curses import wrapper, window
from functools import partial

from telegram.client import Telegram

from tg.controllers import Controller
from tg.models import Model
from tg.views import View
from tg import config, utils


log = logging.getLogger(__name__)


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
    cfg = config.get_cfg()["DEFAULT"]
    utils.setup_log(cfg.get("level", "DEBUG"))
    log.debug("#" * 64)
    tg = TelegramApi(
        api_id=cfg["api_id"],
        api_hash=cfg["api_hash"],
        phone=cfg["phone"],
        database_encryption_key=cfg["enc_key"],
        files_directory=cfg.get("files", config.DEFAULT_FILES),
        tdlib_verbosity=cfg.get("tdlib_verbosity", 0),
        library_path=cfg.get("library_path"),
    )
    tg.login()
    wrapper(partial(run, tg))


if __name__ == "__main__":
    main()
