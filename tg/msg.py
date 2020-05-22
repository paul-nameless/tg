import logging
from datetime import datetime
from typing import Any, Dict, Optional

from tg import utils

log = logging.getLogger(__name__)


class MsgProxy:

    fields_mapping = {
        "messageDocument": ("document", "document"),
        "messageVoiceNote": ("voice_note", "voice"),
        "messageText": ("text", "text"),
        "messagePhoto": ("photo", "sizes", -1, "photo"),
        "messageAudio": ("audio", "audio"),
        "messageVideo": ("video", "video"),
        "messageVideoNote": ("video_note", "video"),
        "messageSticker": ("sticker", "sticker"),
    }

    types = {
        "messageDocument": "document",
        "messageVoiceNote": "voice",
        "messageText": "text",
        "messagePhoto": "photo",
        "messageAudio": "audio",
        "messageVideo": "video",
        "messageVideoNote": "recording",
        "messageSticker": "sticker",
    }

    @classmethod
    def get_doc(cls, msg, deep=10):
        doc = msg["content"]
        _type = doc["@type"]
        fields = cls.fields_mapping.get(_type)
        if fields is None:
            log.error("msg type not supported: %s", _type)
            return {}
        for field in fields[:deep]:
            if isinstance(field, int):
                doc = doc[field]
            else:
                doc = doc.get(field)
            if doc is None:
                return {}
        return doc

    def __init__(self, msg: Dict[str, Any]):
        self.msg = msg

    def __getitem__(self, key: str) -> Any:
        return self.msg[key]

    def __setitem__(self, key, value):
        self.msg[key] = value

    @property
    def type(self) -> Optional[str]:
        return self.msg.get("@type")

    @property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.msg["date"])

    @property
    def is_message(self):
        return self.type == "message"

    @property
    def content_type(self):
        return self.types.get(self.msg["content"]["@type"])

    @property
    def size(self):
        doc = self.get_doc(self.msg)
        return doc["size"]

    @property
    def human_size(self):
        doc = self.get_doc(self.msg)
        return utils.humanize_size(doc["size"])

    @property
    def duration(self):
        if self.content_type not in ("audio", "voice", "video", "recording"):
            return None
        doc = self.get_doc(self.msg, deep=1)
        return utils.humanize_duration(doc["duration"])

    @property
    def file_name(self):
        if self.content_type not in ("audio", "document", "video"):
            return None
        doc = self.get_doc(self.msg, deep=1)
        return doc["file_name"]

    @property
    def file_id(self):
        if self.content_type not in (
            "audio",
            "document",
            "photo",
            "video",
            "recording",
            "sticker",
            "voice",
        ):
            return None
        doc = self.get_doc(self.msg)
        return doc["id"]

    @property
    def local_path(self):
        if self.msg["content"]["@type"] is None:
            return None
        doc = self.get_doc(self.msg)
        return doc["local"]["path"]

    @property
    def local(self):
        doc = self.get_doc(self.msg)
        return doc["local"]

    @local.setter
    def local(self, value):
        if self.msg["content"]["@type"] is None:
            return None
        doc = self.get_doc(self.msg)
        doc["local"] = value

    @property
    def is_text(self):
        return self.msg["content"]["@type"] == "messageText"

    @property
    def text_content(self) -> str:
        return self.msg["content"]["text"]["text"]

    @property
    def is_downloaded(self):
        doc = self.get_doc(self.msg)
        return doc["local"]["is_downloading_completed"]

    @property
    def is_listened(self) -> Optional[bool]:
        if self.content_type != "voice":
            return None
        return self.msg["content"]["is_listened"]

    @is_listened.setter
    def is_listened(self, value: bool):
        if self.content_type == "voice":
            self.msg["content"]["is_listened"] = value

    @property
    def is_viewed(self) -> Optional[bool]:
        if self.content_type != "recording":
            return None
        return self.msg["content"]["is_viewed"]

    @is_viewed.setter
    def is_viewed(self, value: bool):
        if self.content_type == "recording":
            self.msg["content"]["is_viewed"] = value

    @property
    def msg_id(self) -> int:
        return self.msg["id"]

    @property
    def can_be_edited(self) -> bool:
        return self.msg["can_be_edited"]

    @property
    def reply_msg_id(self) -> Optional[int]:
        return self.msg.get("reply_to_message_id")

    @property
    def chat_id(self) -> int:
        return self.msg["chat_id"]

    @property
    def sender_id(self) -> int:
        return self.msg["sender_user_id"]

    @property
    def forward(self) -> Optional[Dict[str, Any]]:
        return self.msg.get("forward_info")
