from enum import Enum
from typing import Any, Dict, List

from telegram.client import AsyncResult, Telegram


class ChatAction(Enum):
    chatActionTyping = "typing"
    chatActionCancel = "cancel"
    chatActionRecordingVideo = "recording video"
    chatActionUploadingVideo = "uploading video"
    chatActionRecordingVoiceNote = "recording voice"
    chatActionUploadingVoiceNote = "uploading voice"
    chatActionUploadingPhoto = "uploading photo"
    chatActionUploadingDocument = "uploading document"
    chatActionChoosingLocation = "choosing location"
    chatActionChoosingContact = "choosing contact"
    chatActionStartPlayingGame = "start playing game"
    chatActionRecordingVideoNote = "recording video"
    chatActionUploadingVideoNote = "uploading video"


class ChatType(Enum):
    chatTypePrivate = "private"
    chatTypeBasicGroup = "group"
    chatTypeSupergroup = "supergroup"
    channel = "channel"
    chatTypeSecret = "secret"


class UserStatus(Enum):
    userStatusEmpty = ""
    userStatusOnline = "online"
    userStatusOffline = "offline"
    userStatusRecently = "recently"
    userStatusLastWeek = "last week"
    userStatusLastMonth = "last month"


class Tdlib(Telegram):
    def download_file(
        self,
        file_id: int,
        priority: int = 16,
        offset: int = 0,
        limit: int = 0,
        synchronous: bool = False,
    ) -> None:
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

    def reply_message(
        self, chat_id: int, reply_to_message_id: int, text: str
    ) -> AsyncResult:
        data = {
            "@type": "sendMessage",
            "chat_id": chat_id,
            "reply_to_message_id": reply_to_message_id,
            "input_message_content": {
                "@type": "inputMessageText",
                "text": {"@type": "formattedText", "text": text},
            },
        }

        return self._send_data(data)

    def send_doc(self, file_path: str, chat_id: int) -> AsyncResult:
        data = {
            "@type": "sendMessage",
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessageDocument",
                "document": {"@type": "inputFileLocal", "path": file_path},
            },
        }
        return self._send_data(data)

    def send_audio(self, file_path: str, chat_id: int) -> AsyncResult:
        data = {
            "@type": "sendMessage",
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessageAudio",
                "audio": {"@type": "inputFileLocal", "path": file_path},
            },
        }
        return self._send_data(data)

    def send_photo(self, file_path: str, chat_id: int) -> AsyncResult:
        data = {
            "@type": "sendMessage",
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessagePhoto",
                "photo": {"@type": "inputFileLocal", "path": file_path},
            },
        }
        return self._send_data(data)

    def send_video(
        self,
        file_path: str,
        chat_id: int,
        width: int,
        height: int,
        duration: int,
    ) -> AsyncResult:
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

    def send_voice(
        self, file_path: str, chat_id: int, duration: int, waveform: str
    ) -> AsyncResult:
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

    def edit_message_text(
        self, chat_id: int, message_id: int, text: str
    ) -> AsyncResult:
        data = {
            "@type": "editMessageText",
            "message_id": message_id,
            "chat_id": chat_id,
            "input_message_content": {
                "@type": "inputMessageText",
                "text": {"@type": "formattedText", "text": text},
            },
        }
        return self._send_data(data)

    def toggle_chat_is_marked_as_unread(
        self, chat_id: int, is_marked_as_unread: bool
    ) -> AsyncResult:
        data = {
            "@type": "toggleChatIsMarkedAsUnread",
            "chat_id": chat_id,
            "is_marked_as_unread": is_marked_as_unread,
        }
        return self._send_data(data)

    def toggle_chat_is_pinned(
        self, chat_id: int, is_pinned: bool
    ) -> AsyncResult:
        data = {
            "@type": "toggleChatIsPinned",
            "chat_id": chat_id,
            "is_pinned": is_pinned,
        }
        return self._send_data(data)

    def set_chat_nottification_settings(
        self, chat_id: int, notification_settings: dict
    ) -> AsyncResult:
        data = {
            "@type": "setChatNotificationSettings",
            "chat_id": chat_id,
            "notification_settings": notification_settings,
        }
        return self._send_data(data)

    def view_messages(
        self, chat_id: int, message_ids: list, force_read: bool = True
    ) -> AsyncResult:
        data = {
            "@type": "viewMessages",
            "chat_id": chat_id,
            "message_ids": message_ids,
            "force_read": force_read,
        }
        return self._send_data(data)

    def open_message_content(
        self, chat_id: int, message_id: int
    ) -> AsyncResult:
        data = {
            "@type": "openMessageContent",
            "chat_id": chat_id,
            "message_id": message_id,
        }
        return self._send_data(data)

    def forward_messages(
        self,
        chat_id: int,
        from_chat_id: int,
        message_ids: List[int],
        as_album: bool = False,
        send_copy: bool = False,
        remove_caption: bool = False,
        options: Dict[str, Any] = {},
    ) -> AsyncResult:
        data = {
            "@type": "forwardMessages",
            "chat_id": chat_id,
            "from_chat_id": from_chat_id,
            "message_ids": message_ids,
            "as_album": as_album,
            "send_copy": send_copy,
            "remove_caption": remove_caption,
            "options": options,
        }
        return self._send_data(data)

    def get_basic_group(self, basic_group_id: int,) -> AsyncResult:
        data = {
            "@type": "getBasicGroup",
            "basic_group_id": basic_group_id,
        }
        return self._send_data(data)

    def get_supergroup(self, supergroup_id: int,) -> AsyncResult:
        data = {
            "@type": "getSupergroup",
            "supergroup_id": supergroup_id,
        }
        return self._send_data(data)

    def send_chat_action(
        self, chat_id: int, action: ChatAction, progress: int = None
    ) -> AsyncResult:
        data = {
            "@type": "sendChatAction",
            "chat_id": chat_id,
            "action": {"@type": action.name, "progress": progress},
        }
        return self._send_data(data)
