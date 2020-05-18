import configparser
import mailcap
import mimetypes
import os
from typing import Optional

DEFAULT_CONFIG = os.path.expanduser("~/.config/tg/tg.conf")
DEFAULT_FILES = os.path.expanduser("~/.cache/tg/")
max_download_size = "10MB"
record_cmd = None


def get_cfg(config: str = DEFAULT_CONFIG) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(config)
    return cfg


def save_cfg(cfg, config=DEFAULT_CONFIG):
    config_dir = os.path.dirname(config)
    if not os.path.isdir(config_dir):
        os.makedirs(config_dir)
    with open(config, "w") as f:
        cfg.write(f)


def get_file_handler(file_name: str, default=None) -> Optional[str]:
    mtype, _ = mimetypes.guess_type(file_name)
    if not mtype:
        return default
    caps = mailcap.getcaps()
    handler, view = mailcap.findmatch(caps, mtype, filename=file_name)
    return handler
