"""
Every parameter (except for CONFIG_FILE) can be
overwritten by external config file
"""
import os
import platform
import runpy

_os_name = platform.system()
_darwin = "Darwin"
_linux = "Linux"


CONFIG_DIR = os.path.expanduser("~/.config/tg/")
CONFIG_FILE = os.path.join(CONFIG_DIR, "conf.py")
FILES_DIR = os.path.expanduser("~/.cache/tg/")

LOG_LEVEL = "INFO"
LOG_PATH = os.path.expanduser("~/.local/share/tg/")

API_ID = "559815"
API_HASH = "fd121358f59d764c57c55871aa0807ca"

PHONE = None
ENC_KEY = ""

TDLIB_PATH = None
TDLIB_VERBOSITY = 0

MAX_DOWNLOAD_SIZE = "10MB"

# TODO: check platform
NOTIFY_CMD = "/usr/local/bin/terminal-notifier -title '{title}' -subtitle '{subtitle}' -message '{msg}' -appIcon '{icon_path}'"

if _os_name == _linux:
    VOICE_RECORD_CMD = (
        "ffmpeg -f alsa -i default -c:a libopus -b:a 32k '{file_path}'"
    )
else:
    VOICE_RECORD_CMD = (
        "ffmpeg -f avfoundation -i ':0' -c:a libopus -b:a 32k '{file_path}'"
    )

# TODO: use mailcap instead of editor
LONG_MSG_CMD = "vim + -c 'startinsert' {file_path}"
EDITOR = os.environ.get("EDITOR", "vi")

if _os_name == _linux:
    DEFAULT_OPEN = "xdg-open '{file_path}'"
else:
    DEFAULT_OPEN = "open '{file_path}'"

if _os_name == _linux:
    COPY_CMD = "xclip -selection c"
else:
    COPY_CMD = "pbcopy"


if os.path.isfile(CONFIG_FILE):
    config_params = runpy.run_path(CONFIG_FILE)
    for param, value in config_params.items():
        if param.isupper():
            globals()[param] = value
else:
    for directory in (LOG_PATH, CONFIG_DIR, FILES_DIR):
        os.makedirs(directory, exist_ok=True)

    if not PHONE:
        PHONE = input("phone> ")

    with open(CONFIG_FILE, "w") as f:
        f.write(f"PHONE = '{PHONE}'\n")
