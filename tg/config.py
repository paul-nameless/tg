"""
Every parameter (except for CONFIG_FILE) can be
overwritten by external config file
"""

import os
import platform
import runpy
from typing import Dict, Optional

_os_name = platform.system()
_darwin = "Darwin"
_linux = "Linux"


CONFIG_DIR = os.path.expanduser("~/.config/tg/")
CONFIG_FILE = os.path.join(CONFIG_DIR, "conf.py")
FILES_DIR = os.path.expanduser("~/.cache/tg/")
MAILCAP_FILE: Optional[str] = None

LOG_LEVEL = "INFO"
LOG_PATH = os.path.expanduser("~/.local/share/tg/")

API_ID = 559815
API_HASH = "fd121358f59d764c57c55871aa0807ca"

PHONE = None
ENC_KEY = ""

TDLIB_PATH = None

if _os_name == _darwin and platform.machine() == "arm64":
    import hashlib
    import urllib.request
    import zipfile

    TDLIB_URL = "https://github.com/ForNeVeR/tdlib.native/releases/download/v1.8.45/tdlib.native.macos.aarch64.zip"
    EXPECTED_HASH = "8b0a61cd0f567391599f7afa6d5ad4f5067cb4f804cd87792ab7714d571cee9f"
    ZIP_PATH = os.path.join(FILES_DIR, "tdlib.native.macos.aarch64.zip")
    TDLIB_LIB_PATH = os.path.join(FILES_DIR, "libtdjson.dylib")

    try:
        os.makedirs(FILES_DIR, exist_ok=True)

        if not os.path.exists(TDLIB_LIB_PATH):
            print(f"Downloading tdlib for macOS ARM from {TDLIB_URL}...")
            urllib.request.urlretrieve(TDLIB_URL, ZIP_PATH)

            with open(ZIP_PATH, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            if file_hash == EXPECTED_HASH:
                with zipfile.ZipFile(ZIP_PATH, "r") as zip_ref:
                    zip_ref.extractall(FILES_DIR)
                print("Successfully downloaded and verified tdlib library")
                TDLIB_PATH = TDLIB_LIB_PATH
            else:
                print("Checksum verification failed for tdlib library")
                # Clean up downloaded file
                if os.path.exists(ZIP_PATH):
                    os.remove(ZIP_PATH)
        else:
            TDLIB_PATH = TDLIB_LIB_PATH
    except Exception as e:
        print(f"Error downloading or verifying tdlib library for macOS ARM: {e}")

TDLIB_VERBOSITY = 0

MAX_DOWNLOAD_SIZE = "10MB"

# TODO: check platform
NOTIFY_CMD = "/usr/local/bin/terminal-notifier -title {title} -subtitle {subtitle} -message {msg} -appIcon {icon_path}"

VIEW_TEXT_CMD = "less"
FZF = "fzf"

if _os_name == _linux:
    # for more info see https://trac.ffmpeg.org/wiki/Capture/ALSA
    VOICE_RECORD_CMD = "ffmpeg -f alsa -i hw:0 -c:a libopus -b:a 32k {file_path}"
else:
    VOICE_RECORD_CMD = (
        "ffmpeg -f avfoundation -i ':0' -c:a libopus -b:a 32k {file_path}"
    )

# TODO: use mailcap instead of editor
LONG_MSG_CMD = "vim + -c 'startinsert' {file_path}"
EDITOR = os.environ.get("EDITOR", "vi")

if _os_name == _linux:
    DEFAULT_OPEN = "xdg-open {file_path}"
else:
    DEFAULT_OPEN = "open {file_path}"

if _os_name == _linux:
    if os.environ.get("WAYLAND_DISPLAY"):
        COPY_CMD = "wl-copy"
    else:
        COPY_CMD = "xclip -selection c"
else:
    COPY_CMD = "pbcopy"

CHAT_FLAGS: Dict[str, str] = {}

MSG_FLAGS: Dict[str, str] = {}

ICON_PATH = os.path.join(os.path.dirname(__file__), "resources", "tg.png")

URL_VIEW = "urlview"

USERS_COLORS = tuple(range(2, 16))

KEEP_MEDIA = 7

FILE_PICKER_CMD = "ranger --choosefile={file_path}"

DOWNLOAD_DIR = os.path.expanduser("~/Downloads/")

if os.path.isfile(CONFIG_FILE):
    config_params = runpy.run_path(CONFIG_FILE)
    for param, value in config_params.items():
        if param.isupper():
            globals()[param] = value
else:
    os.makedirs(CONFIG_DIR, exist_ok=True)

    if not PHONE:
        print(
            "Enter your phone number in international format (including country code)"
        )
        PHONE = input("phone> ")
        if not PHONE.startswith("+"):
            PHONE = "+" + PHONE

    with open(CONFIG_FILE, "w") as f:
        f.write(f"PHONE = '{PHONE}'\n")
