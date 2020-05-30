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

    # handle ctrl+c, to avoid interrupting tg when subprocess is called
    def interrupt_signal_handler(sig, frame):
        # TODO: draw on status pane: to quite press <q>
        log.info("Interrupt signal is handled and ignored on purpose.")

    signal.signal(signal.SIGINT, interrupt_signal_handler)

    model = Model(tg)
    status_view = StatusView(stdscr)
    msg_view = MsgView(stdscr, model.msgs, model, model.users)
    chat_view = ChatView(stdscr)
    view = View(stdscr, chat_view, msg_view, status_view)
    controller = Controller(model, view, tg)

    # hanlde resize of terminal correctly
    signal.signal(signal.SIGWINCH, controller.resize_handler)

    for msg_type, handler in update_handlers.handlers.items():
        tg.add_update_handler(msg_type, partial(handler, controller))

    thread = threading.Thread(target=controller.run,)
    thread.daemon = True
    thread.start()

    log.info("count:: after %d", threading.active_count())
    controller.draw()


def main():
    utils.setup_log(config.LOG_LEVEL)
    log.info("count:: before %d", threading.active_count())

    tg = Tdlib(
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        phone=config.PHONE,
        database_encryption_key=config.ENC_KEY,
        files_directory=config.DEFAULT_FILES,
        tdlib_verbosity=config.TDLIB_VERBOSITY,
        library_path=config.TDLIB_PATH,
    )
    tg.login()
    log.info("count:: tdlib %d", threading.active_count())

    wrapper(partial(run, tg))


if __name__ == "__main__":
    main()
