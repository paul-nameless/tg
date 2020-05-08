import logging
import os
from typing import Optional
import subprocess
from functools import wraps
import curses
from tg import config

log = logging.getLogger(__name__)


def num(value: str, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except ValueError:
        return default


def setup_log(level="DEBUG"):
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.handlers.RotatingFileHandler(
                "./tg.log", backupCount=1, maxBytes=1024 * 1024
            ),
        ],
    )


def notify(
    msg,
    subtitle="",
    title="tg",
    cmd=config.get_cfg()["DEFAULT"].get("notify_cmd"),
):
    if not cmd:
        return
    icon_path = os.path.join(os.path.dirname(__file__), "tg.png")
    notify_cmd = cmd.format(
        icon_path=icon_path, title=title, subtitle=subtitle, msg=msg
    )
    log.info("notify-cmd: %s", notify_cmd)
    os.system(notify_cmd)


def handle_exception(fun):
    @wraps(fun)
    def wrapper(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except Exception:
            log.exception("Error happened in %s handler", fun.__name__)

    return wrapper


class suspend:
    def __init__(self, view):
        self.view = view

    def call(self, *args, **kwargs):
        subprocess.call(*args, **kwargs)

    def run(self, file_path):
        cmd = config.get_file_handler(file_path)
        if not cmd:
            return
        subprocess.call(cmd, shell=True)

    def __enter__(self):
        for view in (self.view.chats, self.view.msgs, self.view.status):
            view._refresh = view.win.noutrefresh
        curses.endwin()
        return self

    def __exit__(self, exc_type, exc_val, tb):
        for view in (self.view.chats, self.view.msgs, self.view.status):
            view._refresh = view.win.refresh
        curses.doupdate()
