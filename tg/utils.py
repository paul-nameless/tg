import curses
import logging
import math
import os
import subprocess
from datetime import datetime
from functools import wraps
from typing import Optional

from tg import config

log = logging.getLogger(__name__)


def humanize_size(
    num, suffix="B", suffixes=("", "K", "M", "G", "T", "P", "E", "Z")
):
    magnitude = int(math.floor(math.log(num, 1024)))
    val = num / math.pow(1024, magnitude)
    if magnitude > 7:
        return "{:.1f}{}{}".format(val, "Yi", suffix)
    return "{:3.1f}{}{}".format(val, suffixes[magnitude], suffix)


def humanize_duration(seconds):
    dt = datetime.utcfromtimestamp(seconds)
    fmt = "%-M:%S"
    if seconds >= 3600:
        fmt = "%-H:%M:%S"
    return dt.strftime(fmt)


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
        curses.endwin()
        return self

    def __exit__(self, exc_type, exc_val, tb):
        # works without it, actually
        curses.doupdate()
