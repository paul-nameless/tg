import logging
import os
from typing import Optional

log = logging.getLogger(__name__)


def num(value: str, default: Optional[int] = None) -> int:
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
