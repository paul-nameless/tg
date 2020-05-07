import logging

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

    def __init__(self, msg):
        self.msg = msg

    def __getitem__(self, key):
        return self.msg[key]

    def __setitem__(self, key, value):
        self.msg[key] = value

    @property
    def type(self):
        return self.types.get(self.msg["content"]["@type"])

    @property
    def size(self):
        doc = self.get_doc(self.msg)
        return doc["size"]

    @property
    def duration(self):
        if self.type not in ("audio", "voice"):
            return None
        doc = self.get_doc(self.msg, deep=1)
        return doc["duration"]

    @property
    def file_name(self):
        if self.type not in ("audio", "document", "video"):
            return None
        doc = self.get_doc(self.msg, deep=1)
        return doc["file_name"]

    @property
    def file_id(self):
        if self.type not in (
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
        if self.msg["content"]["@type"] not in self.types:
            return None
        doc = self.get_doc(self.msg)
        return doc["local"]["path"]

    @property
    def local(self):
        doc = self.get_doc(self.msg)
        return doc["local"]

    @local.setter
    def local(self, value):
        if self.msg["content"]["@type"] not in self.types:
            return None
        doc = self.get_doc(self.msg)
        doc["local"] = value

    @property
    def is_text(self):
        return self.msg["content"]["@type"] == "messageText"

    @property
    def is_downloaded(self):
        doc = self.get_doc(self.msg)
        return doc["local"]["is_downloading_completed"]
