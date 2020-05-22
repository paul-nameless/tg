import logging
import logging.handlers
import signal
import threading
from curses import window, wrapper  # type: ignore
from functools import partial

from tg import config, update_handlers, utils
from tg.controllers import Controller
from tg.models import Model
from tg.tdlib import Tdlib
from tg.views import ChatView, MsgView, StatusView, View

log = logging.getLogger(__name__)


def run(tg: Tdlib, stdscr: window) -> None:
    # run this function in thread?
    model = Model(tg)
    status_view = StatusView(stdscr)
    msg_view = MsgView(stdscr, model.msgs, model, model.users)
    chat_view = ChatView(stdscr)
    view = View(stdscr, chat_view, msg_view, status_view)
    controller = Controller(model, view, tg)
    for msg_type, handler in update_handlers.handlers.items():
        tg.add_update_handler(msg_type, partial(handler, controller))

    t = threading.Thread(target=controller.run,)
    t.start()
    t.join()


def main():
    def signal_handler(sig, frame):
        log.info("You pressed Ctrl+C!")

    signal.signal(signal.SIGINT, signal_handler)

    cfg = config.get_cfg()["DEFAULT"]
    utils.setup_log(cfg.get("level", "DEBUG"))
    log.debug("#" * 64)
    tg = Tdlib(
        api_id=cfg["api_id"],
        api_hash=cfg["api_hash"],
        phone=cfg["phone"],
        database_encryption_key=cfg["enc_key"],
        files_directory=cfg.get("files", config.DEFAULT_FILES),
        tdlib_verbosity=cfg.get("tdlib_verbosity", 0),
        library_path=cfg.get("library_path"),
    )
    config.max_download_size = utils.parse_size(
        cfg.get("max_download_size", config.max_download_size)
    )
    config.record_cmd = cfg.get("record_cmd", config.record_cmd)
    config.long_msg_cmd = cfg.get("long_msg_cmd", config.long_msg_cmd)
    tg.login()

    wrapper(partial(run, tg))


if __name__ == "__main__":
    main()
