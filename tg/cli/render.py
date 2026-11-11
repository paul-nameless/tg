import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

MAX_OUTPUT_CHARS = 30_000
TRUNCATED = "… output truncated, narrow with --chat/--limit"


QUOTED_KEYS = {"title", "name", "query", "from"}


def escape(text: str) -> str:
    out = []
    for char in text:
        if char == "\n":
            out.append("\\n")
        elif char.isprintable():
            out.append(char)
        else:
            out.append(char.encode("unicode_escape").decode("ascii"))
    return "".join(out)


def quote(value: str) -> str:
    return '"' + escape(value.replace("\\", "\\\\").replace('"', '\\"')) + '"'


def kv(**fields: Any) -> str:
    parts = []
    for key, value in fields.items():
        if value is None or value is False:
            continue
        if value is True:
            value = "yes"
        text = str(value)
        if key in QUOTED_KEYS or not text or any(c in text for c in ' "='):
            text = quote(text)
        else:
            text = escape(text)
        parts.append(f"{key}={text}")
    return " ".join(parts)


def clip(text: str, max_chars: int) -> str:
    if max_chars > 0 and len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


def local_date(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M")


def utc_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chat_line(chat: Dict[str, Any]) -> str:
    parts = [
        f"chat_id={chat['chat_id']}",
        f"type={chat['type']}",
        f"title={quote(chat['title'])}",
    ]
    if chat.get("username"):
        parts.append(f"username=@{chat['username']}")
    if "unread" in chat:
        parts.append(f"unread={chat['unread']}")
    if chat.get("mentions"):
        parts.append(f"mentions={chat['mentions']}")
    if chat.get("muted"):
        parts.append("muted=yes")
    if chat.get("marked_unread"):
        parts.append("marked_unread=yes")
    if "shown" in chat:
        parts.append(f"shown={chat['shown']}")
    return " ".join(parts)


def msg_line(msg: Dict[str, Any]) -> str:
    parts = [
        f"msg_id={msg['msg_id']}",
        f"date={local_date(msg['ts'])}",
        f"from={quote(msg['from'])}",
    ]
    if msg.get("reply_to"):
        parts.append(f"reply_to={msg['reply_to']}")
    if msg.get("forwarded"):
        parts.append("forwarded=yes")
    media: Optional[Dict[str, Any]] = msg.get("media")
    if media:
        parts.append(f"media={media['type']}")
        if media.get("name"):
            parts.append(f"name={quote(media['name'])}")
        if media.get("size"):
            parts.append(f"size={media['size']}")
        if media.get("duration"):
            parts.append(f"duration={media['duration']}")
    return "  " + " ".join(parts) + ": " + escape(msg["text"])


def chat_block(chat: Dict[str, Any]) -> List[str]:
    lines = [chat_line(chat)]
    lines.extend(msg_line(m) for m in chat.get("messages", []))
    if chat.get("more"):
        lines.append(f"  more: {chat['more']}")
    return lines


def to_json(data: Dict[str, Any]) -> str:
    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            out = {k: clean(v) for k, v in value.items() if k != "ts"}
            if "ts" in value:
                out["date"] = utc_date(value["ts"])
            return out
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value

    return json.dumps(clean(data), ensure_ascii=False, separators=(",", ":"))


def to_text(lines: List[str]) -> str:
    out: List[str] = []
    size = 0
    for line in lines:
        size += len(line) + 1
        if size > MAX_OUTPUT_CHARS:
            out.append(TRUNCATED)
            break
        out.append(line)
    return "\n".join(out)
