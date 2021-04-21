import base64
import curses
import hashlib
import logging
import mailcap
import math
import mimetypes
import os
import random
import shlex
import struct
import subprocess
import sys
import unicodedata
from datetime import datetime
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from subprocess import CompletedProcess
from types import TracebackType
from typing import Any, Dict, Optional, Tuple, Type

from tg import config

log = logging.getLogger(__name__)
units = {"B": 1, "KB": 10 ** 3, "MB": 10 ** 6, "GB": 10 ** 9, "TB": 10 ** 12}


class LogWriter:
    def __init__(self, level: Any) -> None:
        self.level = level

    def write(self, message: str) -> None:
        if message != "\n":
            self.level.log(self.level, message)

    def flush(self) -> None:
        pass


def setup_log() -> None:
    os.makedirs(config.LOG_PATH, exist_ok=True)

    handlers = []

    for level, filename in (
        (config.LOG_LEVEL, "all.log"),
        (logging.ERROR, "error.log"),
    ):
        handler = RotatingFileHandler(
            os.path.join(config.LOG_PATH, filename),
            maxBytes=parse_size("32MB"),
            backupCount=1,
        )
        handler.setLevel(level)  # type: ignore
        handlers.append(handler)

    logging.basicConfig(
        format="%(levelname)s [%(asctime)s] %(filename)s:%(lineno)s - %(funcName)s | %(message)s",
        handlers=handlers,
    )
    logging.getLogger().setLevel(config.LOG_LEVEL)
    sys.stderr = LogWriter(log.error)  # type: ignore
    logging.captureWarnings(True)


def get_mime(file_path: str) -> str:
    mtype, _ = mimetypes.guess_type(file_path)
    if not mtype:
        return ""
    if mtype == "image/gif":
        return "animation"
    return mtype.split("/")[0]


def get_mailcap() -> Dict:
    if config.MAILCAP_FILE:
        with open(config.MAILCAP_FILE) as f:
            return mailcap.readmailcapfile(f)  # type: ignore
    return mailcap.getcaps()


def get_file_handler(file_path: str) -> str:
    mtype, _ = mimetypes.guess_type(file_path)
    if not mtype:
        return config.DEFAULT_OPEN.format(file_path=shlex.quote(file_path))

    caps = get_mailcap()
    handler, view = mailcap.findmatch(
        caps, mtype, filename=shlex.quote(file_path)
    )
    if not handler:
        return config.DEFAULT_OPEN.format(file_path=shlex.quote(file_path))
    return handler


def parse_size(size: str) -> int:
    if size[-2].isalpha():
        number, unit = size[:-2], size[-2:]
    else:
        number, unit = size[:-1], size[-1:]
    return int(float(number) * units[unit])


def humanize_size(
    num: int,
    suffix: str = "B",
    suffixes: Tuple[str, ...] = (
        "",
        "K",
        "M",
        "G",
        "T",
        "P",
        "E",
        "Z",
    ),
) -> str:
    magnitude = int(math.floor(math.log(num, 1024)))
    val = num / math.pow(1024, magnitude)
    if magnitude > 7:
        return "{:.1f}{}{}".format(val, "Yi", suffix)
    return "{:3.1f}{}{}".format(val, suffixes[magnitude], suffix)


def humanize_duration(seconds: int) -> str:
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


def is_yes(resp: str) -> bool:
    return not resp or resp.strip().lower() == "y"


def is_no(resp: str) -> bool:
    return not resp or resp.strip().lower() == "n"


def get_duration(file_path: str) -> int:
    cmd = f"ffprobe -v error -i '{file_path}' -show_format"
    stdout = subprocess.check_output(shlex.split(cmd)).decode().splitlines()
    line = next((line for line in stdout if "duration" in line), None)
    if line:
        _, duration = line.split("=")
        log.info("duration: %s", duration)
        return int(float(duration))
    return 0


def get_video_resolution(file_path: str) -> Tuple[int, int]:
    cmd = f"ffprobe -v error -show_entries stream=width,height -of default=noprint_wrappers=1 '{file_path}'"
    lines = subprocess.check_output(shlex.split(cmd)).decode().splitlines()
    info = {line.split("=")[0]: line.split("=")[1] for line in lines}
    return int(str(info.get("width"))), int(str(info.get("height")))


def get_waveform(file_path: str) -> str:
    # stub for now
    waveform = (random.randint(0, 255) for _ in range(100))
    packed = struct.pack("100B", *waveform)
    return base64.b64encode(packed).decode()


def notify(
    msg: str,
    subtitle: str = "",
    title: str = "tg",
    cmd: str = config.NOTIFY_CMD,
) -> None:
    if not cmd:
        return
    notify_cmd = cmd.format(
        icon_path=shlex.quote(config.ICON_PATH),
        title=shlex.quote(title),
        subtitle=shlex.quote(subtitle),
        msg=shlex.quote(msg),
    )
    subprocess.Popen(notify_cmd, shell=True)


def string_len_dwc(string: str) -> int:
    """Returns string len including count for double width characters"""
    return sum(1 + (unicodedata.east_asian_width(c) in "WF") for c in string)


def truncate_to_len(string: str, width: int) -> str:
    real_len = string_len_dwc(string)
    if real_len <= width:
        return string

    cur_len = 0
    out_string = ""

    for char in string:
        cur_len += 2 if unicodedata.east_asian_width(char) in "WF" else 1
        out_string += char
        if cur_len >= width:
            break
    return out_string


def copy_to_clipboard(text: str) -> None:
    subprocess.run(
        config.COPY_CMD, universal_newlines=True, input=text, shell=True
    )


class suspend:
    # FIXME: can't explicitly set type "View" due to circular import
    def __init__(self, view: Any) -> None:
        self.view = view

    def call(self, cmd: str) -> CompletedProcess:
        return subprocess.run(cmd, shell=True)

    def run_with_input(self, cmd: str, text: str) -> None:
        proc = subprocess.run(
            cmd, universal_newlines=True, input=text, shell=True
        )
        if proc.returncode:
            input(f"Command <{cmd}> failed: press <enter> to continue")

    def open_file(self, file_path: str, cmd: str = None) -> None:
        if cmd:
            cmd = cmd % shlex.quote(file_path)
        else:
            cmd = get_file_handler(file_path)

        proc = self.call(cmd)
        if proc.returncode:
            input(f"Command <{cmd}> failed: press <enter> to continue")

    def __enter__(self) -> "suspend":
        for view in (self.view.chats, self.view.msgs, self.view.status):
            view._refresh = view.win.noutrefresh
        self.view.resize_handler = self.view.resize_stub
        curses.echo()
        curses.nocbreak()
        self.view.stdscr.keypad(False)
        curses.curs_set(1)
        curses.endwin()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        for view in (self.view.chats, self.view.msgs, self.view.status):
            view._refresh = view.win.refresh
        self.view.resize_handler = self.view.resize
        curses.noecho()
        curses.cbreak()
        self.view.stdscr.keypad(True)
        curses.curs_set(0)
        curses.doupdate()


def set_shorter_esc_delay(delay: int = 25) -> None:
    os.environ.setdefault("ESCDELAY", str(delay))


def pretty_ts(ts: int) -> str:
    now = datetime.utcnow()
    diff = now - datetime.utcfromtimestamp(ts)
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ""

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return f"{second_diff} seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return f"{int(second_diff / 60)} minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return f"{int(second_diff / 3600)} hours ago"
    if day_diff == 1:
        return "yesterday"
    if day_diff < 7:
        return f"{day_diff} days ago"
    if day_diff < 31:
        return f"{int(day_diff / 7)} weeks ago"
    if day_diff < 365:
        return f"{int(day_diff / 30)} months ago"
    return f"{int(day_diff / 365)} years ago"


@lru_cache(maxsize=256)
def get_color_by_str(user: str) -> int:
    index = int(hashlib.sha1(user.encode()).hexdigest(), 16) % len(
        config.USERS_COLORS
    )
    return config.USERS_COLORS[index]


def cleanup_cache() -> None:
    if not config.KEEP_MEDIA:
        return
    files_path = os.path.join(config.FILES_DIR, "files")
    cmd = f"find {files_path} -type f -mtime +{config.KEEP_MEDIA} -delete"
    subprocess.Popen(cmd, shell=True)
