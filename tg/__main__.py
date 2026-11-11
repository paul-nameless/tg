import logging.handlers
import signal
import sys
import threading
from curses import window
from functools import partial
from types import FrameType
from typing import Optional

from tg import config
from tg.tdlib import Tdlib, quiet_tdlib

log = logging.getLogger(__name__)


def run(tg: Tdlib, stdscr: window) -> None:
    from tg import update_handlers
    from tg.controllers import Controller
    from tg.models import Model
    from tg.views import ChatView, MsgView, StatusView, View

    # handle ctrl+c, to avoid interrupting tg when subprocess is called
    def interrupt_signal_handler(sig: int, frame: Optional[FrameType]) -> None:
        # TODO: draw on status pane: to quite press <q>
        log.info("Interrupt signal is handled and ignored on purpose.")

    signal.signal(signal.SIGINT, interrupt_signal_handler)

    model = Model(tg)
    status_view = StatusView(stdscr)
    msg_view = MsgView(stdscr, model)
    chat_view = ChatView(stdscr, model)
    view = View(stdscr, chat_view, msg_view, status_view)
    controller = Controller(model, view, tg)

    # hanlde resize of terminal correctly
    signal.signal(signal.SIGWINCH, controller.resize_handler)

    for msg_type, handler in update_handlers.handlers.items():
        tg.add_update_handler(msg_type, partial(handler, controller))

    thread = threading.Thread(target=controller.run)
    thread.daemon = True
    thread.start()

    controller.draw()


def run_tui() -> None:
    from curses import wrapper

    from tg import utils

    utils.cleanup_cache()
    quiet_tdlib(config.TDLIB_PATH, config.TDLIB_VERBOSITY)
    tg = Tdlib(
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        phone=config.ensure_phone(),
        database_encryption_key=config.ENC_KEY,
        files_directory=config.FILES_DIR,
        tdlib_verbosity=config.TDLIB_VERBOSITY,
        library_path=config.TDLIB_PATH,
    )
    tg.login_interactive()

    utils.setup_log()
    utils.set_shorter_esc_delay()

    wrapper(partial(run, tg))


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] in ("-v", "--version"):
        import tg

        print("Terminal Telegram client")
        print("Version:", tg.__version__)
        sys.exit(0)
    if args:
        from tg.cli import main as cli_main

        sys.exit(cli_main(args))
    run_tui()


if __name__ == "__main__":
    main()
