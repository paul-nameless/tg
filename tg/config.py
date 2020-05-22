"""
Every parameter (except for DEFAULT_CONFIG) can be
overwritten by external config file
"""
import os
import platform
import runpy

_os_name = platform.system()
_darwin = "Darwin"
_linux = "Linux"


DEFAULT_CONFIG = os.path.expanduser("~/.config/tg/conf.py")
DEFAULT_FILES = os.path.expanduser("~/.cache/tg/")
LOG_LEVEL = "INFO"

API_ID = "559815"
API_HASH = "fd121358f59d764c57c55871aa0807ca"

PHONE = None
ENC_KEY = None

TDLIB_PATH = None
TDLIB_VERBOSITY = 0

MAX_DOWNLOAD_SIZE = "10MB"

# TODO: check platform
NOTIFY_CMD = "/usr/local/bin/terminal-notifier -title '{title}' -subtitle '{subtitle}' -message '{msg}' -appIcon '{icon_path}'"
# TODO: check platform
if _os_name == _linux:
    RECORD_CMD = "ffmpeg -f alsa -i default -ar 22050 -b:a 32k '{file_path}'"
else:
    RECORD_CMD = (
        "ffmpeg -f avfoundation -i default -ar 22050 -b:a 32k '{file_path}'"
    )

# TODO: use mailcap instead of editor
LONG_MSG_CMD = "vim -c 'startinsert' {file_path}"
EDITOR = os.environ.get("EDITOR", "vi")

if _os_name == _linux:
    DEFAULT_OPEN = "xdg-open '{file_path}'"
else:
    DEFAULT_OPEN = "open '{file_path}'"

if _os_name == _linux:
    DEFAULT_COPY = "xclip -selection c"
else:
    DEFAULT_COPY = "pbcopy"


if os.path.isfile(DEFAULT_CONFIG):
    env_config_params = runpy.run_path(DEFAULT_CONFIG)
    for param, value in env_config_params.items():
        if param.isupper():
            globals()[param] = value
