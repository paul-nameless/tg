import base64
import curses
import logging
import math
import os
import random
import re
import shlex
import struct
import subprocess
from datetime import datetime
from functools import wraps
from typing import Optional

from tg import config

log = logging.getLogger(__name__)

emoji_pattern = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)
units = {"B": 1, "KB": 10 ** 3, "MB": 10 ** 6, "GB": 10 ** 9, "TB": 10 ** 12}


def parse_size(size):
    if size[-2].isalpha():
        number, unit = size[:-2], size[-2:]
    else:
        number, unit = size[:-1], size[-1:]
    return int(float(number) * units[unit])


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


def is_yes(resp):
    if resp.strip().lower() == "y" or resp == "":
        return True
    return False


def get_duration(file_path):
    cmd = f"ffprobe -v error -i '{file_path}' -show_format"
    stdout = subprocess.check_output(shlex.split(cmd)).decode().splitlines()
    line = next((line for line in stdout if "duration" in line), None)
    if line:
        _, duration = line.split("=")
        log.info("duration: %s", duration)
        return int(float(duration))
    return 0


def get_video_resolution(file_path):
    cmd = f"ffprobe -v error -show_entries stream=width,height -of default=noprint_wrappers=1 '{file_path}'"
    lines = subprocess.check_output(shlex.split(cmd)).decode().splitlines()
    info = {line.split("=")[0]: line.split("=")[1] for line in lines}
    return info.get("width"), info.get("height")


def get_waveform(file_path):
    # mock for now
    waveform = (random.randint(0, 255) for _ in range(100))
    packed = struct.pack("100B", *waveform)
    return base64.b64encode(packed).decode()


def setup_log(level="DEBUG"):
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.handlers.RotatingFileHandler(
                "./tg.log", backupCount=1, maxBytes=1024 * 1024 * 10  # 10 MB
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


def truncate_to_len(s: str, target_len: int, encoding: str = "utf-8") -> str:
    target_len -= sum(map(bool, map(emoji_pattern.findall, s[:target_len])))
    return s[: max(1, target_len - 1)]


class suspend:
    def __init__(self, view):
        self.view = view

    def call(self, cmd):
        subprocess.call(cmd, shell=True)

    def open_file(self, file_path):
        cmd = config.get_file_handler(file_path)
        if not cmd:
            return
        self.call(cmd)

    def __enter__(self):
        for view in (self.view.chats, self.view.msgs, self.view.status):
            view._refresh = view.win.noutrefresh
        curses.echo()
        curses.nocbreak()
        self.view.stdscr.keypad(False)
        curses.curs_set(1)
        curses.endwin()
        return self

    def __exit__(self, exc_type, exc_val, tb):
        for view in (self.view.chats, self.view.msgs, self.view.status):
            view._refresh = view.win.refresh
        curses.noecho()
        curses.cbreak()
        self.view.stdscr.keypad(True)
        curses.curs_set(0)
        curses.doupdate()
