import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

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
        "messageSticker": ("sticker", "thumbnail", "photo"),
        "messagePoll": (),
        "messageAnimation": ("animation", "animation"),
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
        "messagePoll": "poll",
        "messageAnimation": "animation",
    }

    @classmethod
    def get_doc(cls, msg: Dict[str, Any], deep: int = 10) -> Dict[str, Any]:
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
            if "file" in doc:
                return doc["file"]
            if doc is None:
                return {}
        return doc

    def __init__(self, msg: Dict[str, Any]) -> None:
        self.msg = msg

    def __getitem__(self, key: str) -> Any:
        return self.msg[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.msg[key] = value

    @property
    def type(self) -> Optional[str]:
        return self.msg.get("@type")

    @property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.msg["date"])

    @property
    def is_message(self) -> bool:
        return self.type == "message"

    @property
    def content_type(self) -> Optional[str]:
        return self.types.get(self.msg["content"]["@type"])

    @property
    def size(self) -> Optional[int]:
        doc = self.get_doc(self.msg)
        return doc.get("size")

    @property
    def human_size(self) -> Optional[str]:
        if self.size:
            return utils.humanize_size(self.size)

    @property
    def duration(self) -> Optional[str]:
        if self.content_type not in ("audio", "voice", "video", "recording"):
            return None
        doc = self.get_doc(self.msg, deep=1)
        return utils.humanize_duration(doc["duration"])

    @property
    def file_name(self) -> Optional[str]:
        if self.content_type not in ("audio", "document", "video"):
            return None
        doc = self.get_doc(self.msg, deep=1)
        return doc["file_name"]

    @property
    def file_id(self) -> Optional[int]:
        if self.content_type not in (
            "audio",
            "document",
            "photo",
            "video",
            "recording",
            "sticker",
            "voice",
            "animation",
        ):
            return None
        doc = self.get_doc(self.msg)
        return doc["id"]

    @property
    def local_path(self) -> Optional[str]:
        if self.content_type is None:
            return None
        doc = self.get_doc(self.msg)
        return doc["local"]["path"]

    @property
    def local(self) -> Dict:
        doc = self.get_doc(self.msg)
        return doc.get("local", {})

    @local.setter
    def local(self, value: Dict) -> None:
        if self.msg["content"]["@type"] is None:
            return
        doc = self.get_doc(self.msg)
        doc["local"] = value

    @property
    def is_text(self) -> bool:
        return self.msg["content"]["@type"] == "messageText"

    @property
    def is_poll(self) -> bool:
        return self.msg["content"]["@type"] == "messagePoll"

    @property
    def poll_question(self) -> str:
        assert self.is_poll
        return self.msg["content"]["poll"]["question"]

    @property
    def poll_options(self) -> List[Dict]:
        assert self.is_poll
        return self.msg["content"]["poll"]["options"]

    @property
    def is_closed_poll(self) -> Optional[bool]:
        if not self.is_poll:
            return None
        return self.msg["content"]["poll"]["is_closed"]

    @property
    def text_content(self) -> str:
        return self.msg["content"]["text"]["text"]

    @property
    def is_downloaded(self) -> bool:
        doc = self.get_doc(self.msg)
        return doc["local"]["is_downloading_completed"]

    @property
    def is_listened(self) -> Optional[bool]:
        if self.content_type != "voice":
            return None
        return self.msg["content"]["is_listened"]

    @is_listened.setter
    def is_listened(self, value: bool) -> None:
        if self.content_type == "voice":
            self.msg["content"]["is_listened"] = value

    @property
    def is_viewed(self) -> Optional[bool]:
        if self.content_type != "recording":
            return None
        return self.msg["content"]["is_viewed"]

    @is_viewed.setter
    def is_viewed(self, value: bool) -> None:
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
    def reply_markup(self) -> Optional[Dict[str, Any]]:
        return self.msg.get("reply_markup")

    @property
    def reply_markup_rows(self) -> List[List[Dict[str, Any]]]:
        assert self.reply_markup
        return self.reply_markup.get("rows", [])

    @property
    def chat_id(self) -> int:
        return self.msg["chat_id"]

    @property
    def sender_id(self) -> int:
        return self.msg["sender"].get("user_id") or self.msg["sender"].get(
            "chat_id"
        )

    @property
    def forward(self) -> Optional[Dict[str, Any]]:
        return self.msg.get("forward_info")

    @property
    def caption(self) -> Optional[str]:
        caption = self.msg["content"].get("caption")
        if not caption:
            return None
        return caption["text"]

    @property
    def sticker_emoji(self) -> Optional[str]:
        if self.content_type != "sticker":
            return None
        return self.msg["content"].get("sticker", {}).get("emoji")

    @property
    def is_animated(self) -> Optional[bool]:
        if self.content_type != "sticker":
            return None
        return self.msg["content"].get("sticker", {}).get("is_animated")
