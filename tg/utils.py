import logging
import os
from typing import Optional
import subprocess
from functools import wraps
import curses

log = logging.getLogger(__name__)


def num(value: str, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(value)
    except ValueError:
        return default


def notify(msg, subtitle="New message", title="Telegram"):
    msg = "-message {!r}".format(msg)
    subtitle = "-subtitle {!r}".format(subtitle)
    title = "-title {!r}".format(title)
    sound = "-sound default"
    icon_path = os.path.join(os.path.dirname(__file__), "tg.png")
    icon = f"-appIcon {icon_path}"
    cmd = "/usr/local/bin/terminal-notifier"

    log.debug("####: %s", f"{cmd} {icon} {sound} {title} {subtitle} {msg}")
    os.system(f"{cmd} {icon} {sound} {title} {subtitle} {msg}")


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

    def __enter__(self):
        curses.endwin()
        return self

    def __exit__(self, exc_type, exc_val, tb):
        # works without it, actually
        curses.doupdate()
