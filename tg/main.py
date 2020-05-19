import logging
import logging.handlers
import signal
import sys
import threading
from curses import window, wrapper
from functools import partial

from telegram.client import Telegram

from tg import config, utils
from tg.controllers import Controller
from tg.models import Model
from tg.views import ChatView, MsgView, StatusView, View

log = logging.getLogger(__name__)


def run(tg: Telegram, stdscr: window) -> None:
    # run this function in thread?
    model = Model(tg)
    status_view = StatusView(stdscr)
    msg_view = MsgView(stdscr, model.msgs)
    chat_view = ChatView(stdscr)
    view = View(stdscr, chat_view, msg_view, status_view)
    controller = Controller(model, view, tg)
    for msg_type, handler in controller.handlers.items():
        tg.add_update_handler(msg_type, handler)

    t = threading.Thread(target=controller.run,)
    t.start()
    t.join()


class TelegramApi(Telegram):
    def download_file(
        self, file_id, priority=16, offset=0, limit=0, synchronous=False,
    ):
        result = self.call_method(
            "downloadFile",
            params=dict(
                file_id=file_id,
                priority=priority,
                offset=offset,
                limit=limit,
                synchronous=synchronous,
            ),
            block=False,
        )
        result.wait()

    def send_doc(self, file_path, chat_id):
        data = {
            "@type": "sendMessage",
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessageDocument",
                "document": {"@type": "inputFileLocal", "path": file_path},
            },
        }
        return self._send_data(data)

    def send_audio(self, file_path, chat_id):
        data = {
            "@type": "sendMessage",
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessageAudio",
                "audio": {"@type": "inputFileLocal", "path": file_path},
            },
        }
        return self._send_data(data)

    def send_photo(self, file_path, chat_id):
        data = {
            "@type": "sendMessage",
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessagePhoto",
                "photo": {"@type": "inputFileLocal", "path": file_path},
            },
        }
        return self._send_data(data)

    def send_video(self, file_path, chat_id, width, height, duration):
        data = {
            "@type": "sendMessage",
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessageVideo",
                "width": width,
                "height": height,
                "duration": duration,
                "video": {"@type": "inputFileLocal", "path": file_path},
            },
        }
        return self._send_data(data)

    def send_voice(self, file_path, chat_id, duration, waveform):
        data = {
            "@type": "sendMessage",
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessageVoiceNote",
                "duration": duration,
                "waveform": waveform,
                "voice_note": {"@type": "inputFileLocal", "path": file_path},
            },
        }
        return self._send_data(data)

    def toggle_chat_is_marked_as_unread(
        self, chat_id: int, is_marked_as_unread: bool
    ):
        data = {
            "@type": "toggleChatIsMarkedAsUnread",
            "chat_id": chat_id,
            "is_marked_as_unread": is_marked_as_unread,
        }
        return self._send_data(data)

    def toggle_chat_is_pinned(self, chat_id: int, is_pinned: bool):
        data = {
            "@type": "toggleChatIsPinned",
            "chat_id": chat_id,
            "is_pinned": is_pinned,
        }
        return self._send_data(data)

    def set_chat_nottification_settings(
        self, chat_id: int, notification_settings: dict
    ):
        data = {
            "@type": "setChatNotificationSettings",
            "chat_id": chat_id,
            "notification_settings": notification_settings,
        }
        return self._send_data(data)

    def view_messages(
        self, chat_id: int, message_ids: list, force_read: bool = True
    ):
        data = {
            "@type": "viewMessages",
            "chat_id": chat_id,
            "message_ids": message_ids,
            "force_read": force_read,
        }
        return self._send_data(data)


def main():
    def signal_handler(sig, frame):
        log.info("You pressed Ctrl+C!")

    signal.signal(signal.SIGINT, signal_handler)

    cfg = config.get_cfg()["DEFAULT"]
    utils.setup_log(cfg.get("level", "DEBUG"))
    log.debug("#" * 64)
    tg = TelegramApi(
        api_id=cfg["api_id"],
        api_hash=cfg["api_hash"],
        phone=cfg["phone"],
        database_encryption_key=cfg["enc_key"],
        files_directory=cfg.get("files", config.DEFAULT_FILES),
        tdlib_verbosity=cfg.get("tdlib_verbosity", 0),
        library_path=cfg.get("library_path"),
    )
    config.max_download_size = utils.parse_size(
        cfg.get("max_download_size", config.max_download_size)
    )
    config.record_cmd = cfg.get("record_cmd")
    tg.login()

    wrapper(partial(run, tg))


if __name__ == "__main__":
    main()
