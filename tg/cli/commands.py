import argparse
import math
import os
import re
import shlex
import shutil
import sys
import threading
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple

from tg import config, utils
from tg.cli import render
from tg.cli.session import EXIT_CHAT, EXIT_SEND, EXIT_USAGE, CliError, Session
from tg.msg import MsgProxy
from tg.tdlib import ChatType, get_chat_type

Output = Tuple[Dict[str, Any], List[str]]

CHATS_PAGE = 100
MAX_SCANNED_CHATS = 5000
MAX_RESOLVE_CHATS = 1000
HISTORY_PAGE = 100
MAX_HISTORY_REQUESTS = 30
DOWNLOAD_TIMEOUT = 600.0
UPDATE_TIMEOUT = 10.0
SEND_TIMEOUT = 30.0

SCOPES = {
    "private": "notificationSettingsScopePrivateChats",
    "secret": "notificationSettingsScopePrivateChats",
    "bot": "notificationSettingsScopePrivateChats",
    "group": "notificationSettingsScopeGroupChats",
    "supergroup": "notificationSettingsScopeGroupChats",
    "channel": "notificationSettingsScopeChannelChats",
}

MEDIA_TYPES = {
    "messagePhoto": "photo",
    "messageVideo": "video",
    "messageVideoNote": "video_note",
    "messageVoiceNote": "voice",
    "messageAudio": "audio",
    "messageDocument": "document",
    "messageAnimation": "animation",
    "messageSticker": "sticker",
    "messagePoll": "poll",
}


def cmd(*parts: Any) -> str:
    return "tg " + " ".join(shlex.quote(str(p)) for p in parts)


class Ctx:
    def __init__(self, session: Session, args: argparse.Namespace) -> None:
        self.session = session
        self.args = args
        self.call = session.call
        self._chats: Dict[int, Dict[str, Any]] = {}
        self._users: Dict[int, Dict[str, Any]] = {}
        self._scope_muted: Dict[str, bool] = {}
        self._me: Optional[Dict[str, Any]] = None

    def me(self) -> Dict[str, Any]:
        if self._me is None:
            self._me = self.call("getMe")
        return self._me

    def chat(self, chat_id: int) -> Dict[str, Any]:
        if chat_id not in self._chats:
            self._chats[chat_id] = self.call("getChat", chat_id=chat_id)
        return self._chats[chat_id]

    def user(self, user_id: int) -> Dict[str, Any]:
        if user_id not in self._users:
            self._users[user_id] = self.call("getUser", user_id=user_id)
        return self._users[user_id]

    def chat_list(self) -> Dict[str, str]:
        if getattr(self.args, "archive", False):
            return {"@type": "chatListArchive"}
        return {"@type": "chatListMain"}

    def chat_type(self, chat: Dict[str, Any]) -> str:
        chat_type = get_chat_type(chat)
        if chat_type is None:
            return "unknown"
        if chat_type == ChatType.chatTypePrivate:
            user_type = self.user(chat["type"]["user_id"]).get("type", {})
            if user_type.get("@type") == "userTypeBot":
                return "bot"
        return chat_type.value

    def username(self, chat: Dict[str, Any]) -> Optional[str]:
        kind = chat["type"]["@type"]
        try:
            if kind in ("chatTypePrivate", "chatTypeSecret"):
                usernames = self.user(chat["type"]["user_id"]).get("usernames")
            elif kind == "chatTypeSupergroup":
                usernames = self.call(
                    "getSupergroup", supergroup_id=chat["type"]["supergroup_id"]
                ).get("usernames")
            else:
                return None
        except CliError:
            return None
        active = (usernames or {}).get("active_usernames") or []
        return active[0] if active else None

    def is_muted(self, chat: Dict[str, Any]) -> bool:
        settings = chat.get("notification_settings", {})
        if not settings.get("use_default_mute_for"):
            return settings.get("mute_for", 0) > 0
        scope = SCOPES.get(self.chat_type(chat))
        if scope is None:
            return False
        if scope not in self._scope_muted:
            scope_settings = self.call(
                "getScopeNotificationSettings", scope={"@type": scope}
            )
            self._scope_muted[scope] = scope_settings.get("mute_for", 0) > 0
        return self._scope_muted[scope]

    def chat_info(self, chat: Dict[str, Any], unread: bool = True) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "chat_id": chat["id"],
            "type": self.chat_type(chat),
            "title": chat.get("title", ""),
            "username": self.username(chat),
        }
        if unread:
            info["unread"] = chat.get("unread_count", 0)
            info["mentions"] = chat.get("unread_mention_count", 0)
            info["muted"] = self.is_muted(chat)
            info["marked_unread"] = chat.get("is_marked_as_unread", False)
        return info

    def sender(self, msg: Dict[str, Any]) -> Tuple[str, Optional[int]]:
        if msg.get("is_outgoing"):
            return "me", self.me()["id"]
        sender = msg.get("sender_id", {})
        try:
            if sender.get("@type") == "messageSenderUser":
                user = self.user(sender["user_id"])
                name = f"{user.get('first_name', '')} {user.get('last_name', '')}"
                return name.strip() or "unknown", sender["user_id"]
            if sender.get("@type") == "messageSenderChat":
                return self.chat(sender["chat_id"]).get("title", ""), sender["chat_id"]
        except CliError:
            pass
        return "unknown", None

    def msg_info(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        content = msg.get("content", {})
        kind = content.get("@type", "")
        text = ""
        media: Optional[Dict[str, Any]] = None
        if kind == "messageText":
            text = content.get("text", {}).get("text", "")
        else:
            text = (content.get("caption") or {}).get("text", "")
            media = {"type": MEDIA_TYPES.get(kind) or service_name(kind)}
            if kind in MEDIA_TYPES:
                media.update(media_details(msg))
            if kind == "messageSticker":
                text = content.get("sticker", {}).get("emoji", "")
            elif kind == "messagePoll":
                question = content.get("poll", {}).get("question", "")
                text = (
                    question.get("text", "") if isinstance(question, dict) else question
                )
        name, sender_id = self.sender(msg)
        reply = msg.get("reply_to") or {}
        reply_to = (
            reply.get("message_id")
            if reply.get("@type") == "messageReplyToMessage"
            else None
        )
        return {
            "msg_id": msg["id"],
            "ts": msg.get("date", 0),
            "from": name,
            "from_id": sender_id,
            "reply_to": reply_to or None,
            "forwarded": bool(msg.get("forward_info")),
            "media": media,
            "text": render.clip(text, self.args.max_chars),
        }

    def iter_chats(
        self, max_chats: int = MAX_SCANNED_CHATS
    ) -> Iterator[Dict[str, Any]]:
        yielded: Set[int] = set()
        limit = CHATS_PAGE
        while len(yielded) < max_chats:
            ids = self.call("getChats", chat_list=self.chat_list(), limit=limit).get(
                "chat_ids", []
            )
            for chat_id in ids:
                if chat_id not in yielded:
                    yielded.add(chat_id)
                    yield self.chat(chat_id)
            if len(ids) < limit:
                return
            limit += CHATS_PAGE

    def history_older(
        self, chat_id: int, before: int, limit: int, after: int = 0
    ) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = []
        from_id = before
        for _ in range(MAX_HISTORY_REQUESTS):
            batch = self.call(
                "getChatHistory",
                chat_id=chat_id,
                from_message_id=from_id,
                offset=0,
                limit=min(HISTORY_PAGE, limit - len(msgs) + 1),
                only_local=self.session.stale,
            ).get("messages", [])
            new = [m for m in batch if m and (from_id == 0 or m["id"] < from_id)]
            if not new:
                break
            for msg in new:
                if msg["id"] <= after:
                    return msgs
                msgs.append(msg)
                if len(msgs) >= limit:
                    return msgs
            from_id = new[-1]["id"]
        return msgs

    def history_newer(
        self, chat_id: int, after: int, limit: int
    ) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = []
        from_id = after
        for _ in range(MAX_HISTORY_REQUESTS):
            count = min(HISTORY_PAGE - 2, limit - len(msgs))
            batch = self.call(
                "getChatHistory",
                chat_id=chat_id,
                from_message_id=from_id,
                offset=-(count + 1),
                limit=count + 2,
                only_local=self.session.stale,
            ).get("messages", [])
            new = sorted(
                (m for m in batch if m and m["id"] > from_id), key=lambda m: m["id"]
            )
            if not new:
                break
            msgs.extend(new)
            if len(msgs) >= limit:
                return msgs[:limit]
            from_id = new[-1]["id"]
        return msgs

    def resolve(self, ref: str, strict: bool = False) -> Dict[str, Any]:
        if re.fullmatch(r"-?\d+", ref):
            try:
                return self.chat(int(ref))
            except CliError:
                raise CliError(f"chat not found: {ref}", EXIT_CHAT)
        if ref.lower() in ("me", "saved"):
            chat = self.call("createPrivateChat", user_id=self.me()["id"], force=False)
            self._chats[chat["id"]] = chat
            return chat
        if ref.startswith("@"):
            try:
                chat = self.call("searchPublicChat", username=ref[1:])
            except CliError:
                raise CliError(f"chat not found: {ref}", EXIT_CHAT)
            self._chats[chat["id"]] = chat
            return chat
        ids = self.call("searchChats", query=ref, limit=50).get("chat_ids", [])
        chats = [self.chat(chat_id) for chat_id in ids]
        folded = ref.casefold()
        if not any(folded in c.get("title", "").casefold() for c in chats):
            chats = list(self.iter_chats(MAX_RESOLVE_CHATS))
        exact = [c for c in chats if c.get("title", "").casefold() == folded]
        partial = [c for c in chats if folded in c.get("title", "").casefold()]
        if len(exact) == 1:
            return exact[0]
        if not strict and not exact and len(partial) == 1:
            return partial[0]
        matches = exact or partial
        if not matches:
            raise CliError(f"chat not found: {render.quote(ref)}", EXIT_CHAT)
        candidates = "\n".join(
            render.chat_line(self.chat_info(c, unread=False)) for c in matches[:20]
        )
        reason = "ambiguous chat" if len(matches) > 1 else "no exact title match for"
        raise CliError(
            f"{reason} {render.quote(ref)}, use chat_id:\n{candidates}", EXIT_CHAT
        )


def service_name(kind: str) -> str:
    name = kind[len("message") :] if kind.startswith("message") else kind
    return name[:1].lower() + name[1:] or "unknown"


def media_details(msg: Dict[str, Any]) -> Dict[str, Any]:
    proxy = MsgProxy(msg)
    details: Dict[str, Any] = {}
    for key in ("file_name", "human_size", "duration"):
        try:
            value = getattr(proxy, key)
        except (KeyError, TypeError, IndexError, AttributeError):
            continue
        if value:
            details[{"file_name": "name", "human_size": "size"}.get(key, key)] = value
    return details


def is_unread(chat: Dict[str, Any]) -> bool:
    return bool(chat.get("unread_count") or chat.get("is_marked_as_unread"))


def take(
    chats: Iterator[Dict[str, Any]],
    offset: int,
    limit: int,
    keep: Callable[[Dict[str, Any]], bool],
) -> Tuple[List[Dict[str, Any]], bool]:
    matches: List[Dict[str, Any]] = []
    for chat in chats:
        if not keep(chat):
            continue
        if len(matches) == offset + limit:
            return matches[offset:], True
        matches.append(chat)
    return matches[offset:], False


def unread(ctx: Ctx, args: argparse.Namespace) -> Output:
    skipped = 0

    def keep(chat: Dict[str, Any]) -> bool:
        nonlocal skipped
        if not is_unread(chat):
            return False
        if not args.chat and not args.muted and ctx.is_muted(chat):
            skipped += 1
            return False
        return True

    source = iter([ctx.resolve(args.chat)]) if args.chat else ctx.iter_chats()
    page, has_more = take(source, args.offset, args.limit, keep)

    result = []
    for chat in page:
        info = ctx.chat_info(chat)
        last_read = chat.get("last_read_inbox_message_id", 0)
        msgs = ctx.history_older(chat["id"], 0, args.per_chat, after=last_read)
        msgs = [m for m in reversed(msgs) if not m.get("is_outgoing")]
        info["shown"] = len(msgs)
        info["messages"] = [ctx.msg_info(m) for m in msgs]
        if msgs and chat.get("unread_count", 0) > len(msgs):
            info["more"] = cmd(
                "history", chat["id"], "--before", msgs[0]["id"], "--after", last_read
            )
        result.append(info)

    next_cmd = None
    if has_more:
        parts: List[Any] = ["unread", "--offset", args.offset + args.limit]
        parts += ["--limit", args.limit, "--per-chat", args.per_chat]
        if args.muted:
            parts.append("--muted")
        if args.archive:
            parts.append("--archive")
        next_cmd = cmd(*parts)

    data = {
        "shown_chats": len(result),
        "shown_msgs": sum(len(c["messages"]) for c in result),
        "muted_skipped": skipped,
        "chats": result,
        "next": next_cmd,
    }
    lines = [
        render.kv(
            shown_chats=data["shown_chats"],
            shown_msgs=data["shown_msgs"],
            muted_skipped=skipped,
        )
    ]
    for info in result:
        lines += render.chat_block(info)
    if not result:
        lines.append("no unread chats")
    if next_cmd:
        lines.append(f"next: {next_cmd}")
    return data, lines


def chats(ctx: Ctx, args: argparse.Namespace) -> Output:
    source: Iterator[Dict[str, Any]]
    if args.query:
        limit = min(args.offset + args.limit + 1, 500)
        ids = ctx.call("searchChats", query=args.query, limit=limit)
        source = (ctx.chat(i) for i in ids.get("chat_ids", []))
    else:
        source = ctx.iter_chats()
    page, has_more = take(
        source, args.offset, args.limit, is_unread if args.unread else bool
    )
    result = [ctx.chat_info(c) for c in page]
    next_cmd = None
    if has_more:
        parts: List[Any] = ["chats", "--offset", args.offset + args.limit]
        parts += ["--limit", args.limit]
        if args.unread:
            parts.append("--unread")
        if args.query:
            parts += ["--query", args.query]
        if args.archive:
            parts.append("--archive")
        next_cmd = cmd(*parts)
    lines = [render.chat_line(c) for c in result] or ["no chats"]
    if next_cmd:
        lines.append(f"next: {next_cmd}")
    return {"chats": result, "next": next_cmd}, lines


def history(ctx: Ctx, args: argparse.Namespace) -> Output:
    chat = ctx.resolve(args.chat)
    chat_id = chat["id"]
    next_parts: Optional[List[Any]] = None
    if args.after and not args.before:
        msgs = ctx.history_newer(chat_id, args.after, args.limit + 1)
        has_more = len(msgs) > args.limit
        msgs = msgs[: args.limit]
        if has_more:
            next_parts = ["history", chat_id, "--after", msgs[-1]["id"]]
    else:
        msgs = ctx.history_older(
            chat_id, args.before or 0, args.limit + 1, after=args.after or 0
        )
        has_more = len(msgs) > args.limit
        msgs = msgs[: args.limit]
        msgs.reverse()
        if has_more:
            next_parts = ["history", chat_id, "--before", msgs[0]["id"]]
            if args.after:
                next_parts += ["--after", args.after]
    next_cmd = cmd(*next_parts, "--limit", args.limit) if next_parts else None
    info = ctx.chat_info(chat, unread=False)
    info["messages"] = [ctx.msg_info(m) for m in msgs]
    lines = render.chat_block(info)
    if not msgs:
        lines.append("  no messages")
    if next_cmd:
        lines.append(f"next: {next_cmd}")
    return {"chat": info, "next": next_cmd}, lines


def search(ctx: Ctx, args: argparse.Namespace) -> Output:
    if args.chat:
        chat = ctx.resolve(args.chat)
        found = ctx.call(
            "searchChatMessages",
            chat_id=chat["id"],
            query=args.query,
            from_message_id=int(args.offset or 0),
            offset=0,
            limit=args.limit,
        )
        next_offset: Any = found.get("next_from_message_id") or None
    else:
        params: Dict[str, Any] = {}
        if args.archive:
            params["chat_list"] = ctx.chat_list()
        found = ctx.call(
            "searchMessages",
            query=args.query,
            offset=args.offset or "",
            limit=args.limit,
            min_date=0,
            max_date=0,
            **params,
        )
        next_offset = found.get("next_offset") or None

    groups: Dict[int, Dict[str, Any]] = {}
    for msg in found.get("messages", []):
        if not msg:
            continue
        chat_id = msg["chat_id"]
        if chat_id not in groups:
            groups[chat_id] = ctx.chat_info(ctx.chat(chat_id), unread=False)
            groups[chat_id]["messages"] = []
        groups[chat_id]["messages"].append(ctx.msg_info(msg))

    next_cmd = None
    if next_offset:
        parts: List[Any] = ["search", args.query, "--offset", next_offset]
        if args.chat:
            parts += ["--chat", args.chat]
        parts += ["--limit", args.limit]
        if args.archive:
            parts.append("--archive")
        next_cmd = cmd(*parts)
    shown = sum(len(g["messages"]) for g in groups.values())
    total = found.get("total_count", shown)
    lines = [render.kv(query=args.query, total=total, shown=shown)]
    for info in groups.values():
        lines += render.chat_block(info)
    if next_cmd:
        lines.append(f"next: {next_cmd}")
    data = {
        "query": args.query,
        "total": total,
        "shown": shown,
        "chats": list(groups.values()),
        "next": next_cmd,
    }
    return data, lines


def ensure_send_enabled() -> None:
    if not config.CLI_SEND:
        raise CliError(
            "sending is disabled; set CLI_SEND = True in ~/.config/tg/conf.py",
            EXIT_SEND,
        )


def send_allowed(ctx: Ctx, chat: Dict[str, Any]) -> None:
    ensure_send_enabled()
    allowlist = config.CLI_SEND_ALLOWLIST
    if not allowlist:
        return
    username = ctx.username(chat)
    allowed = {str(item).lower() for item in allowlist}
    keys = {str(chat["id"])}
    if username:
        keys.add(f"@{username.lower()}")
    if not keys & allowed:
        raise CliError(f"chat {chat['id']} is not in CLI_SEND_ALLOWLIST", EXIT_SEND)


def send(ctx: Ctx, args: argparse.Namespace) -> Output:
    ensure_send_enabled()
    chat = ctx.resolve(args.chat, strict=True)
    send_allowed(ctx, chat)
    text = sys.stdin.read() if args.text == "-" else args.text
    text = text.rstrip("\n")
    if not text.strip():
        raise CliError("empty message", EXIT_USAGE)

    results: Dict[int, Dict[str, Any]] = {}
    done = threading.Condition()

    def on_result(update: Dict[str, Any]) -> None:
        with done:
            results[update["old_message_id"]] = update
            done.notify_all()

    ctx.session.on("updateMessageSendSucceeded", on_result)
    ctx.session.on("updateMessageSendFailed", on_result)

    params: Dict[str, Any] = {
        "chat_id": chat["id"],
        "input_message_content": {
            "@type": "inputMessageText",
            "text": {"@type": "formattedText", "text": text},
        },
    }
    if args.reply_to:
        params["reply_to"] = {
            "@type": "inputMessageReplyToMessage",
            "message_id": args.reply_to,
        }
    temp_id = ctx.call("sendMessage", **params)["id"]
    with done:
        done.wait_for(lambda: temp_id in results, timeout=SEND_TIMEOUT)
    update = results.get(temp_id)

    title = chat.get("title", "")
    if update is None:
        data = {"status": "pending", "msg_id": temp_id, "chat_id": chat["id"]}
        line = render.kv(pending="yes", msg_id=temp_id, chat_id=chat["id"], title=title)
        return data, [line, "note: queued, Telegram sends it later; do not resend"]
    if update["@type"] == "updateMessageSendFailed":
        error = update.get("error", {}).get("message", "unknown error")
        raise CliError(f"send failed: {error}")
    msg_id = update["message"]["id"]
    data = {"status": "sent", "msg_id": msg_id, "chat_id": chat["id"]}
    return data, [render.kv(sent="yes", msg_id=msg_id, chat_id=chat["id"], title=title)]


def mark_read(ctx: Ctx, args: argparse.Namespace) -> Output:
    chat = ctx.resolve(args.chat, strict=True)
    chat_id = chat["id"]
    before = chat.get("unread_count", 0)
    up_to = args.up_to or (chat.get("last_message") or {}).get("id")

    left: Dict[str, int] = {}
    updated = threading.Event()

    def on_read(update: Dict[str, Any]) -> None:
        if update.get("chat_id") == chat_id:
            left["count"] = update.get("unread_count", 0)
            updated.set()

    if before and up_to:
        ctx.session.on("updateChatReadInbox", on_read)
        ctx.call("viewMessages", chat_id=chat_id, message_ids=[up_to], force_read=True)
        if not updated.wait(UPDATE_TIMEOUT):
            left["count"] = ctx.call("getChat", chat_id=chat_id).get("unread_count", 0)
    if chat.get("is_marked_as_unread") and not args.up_to:
        ctx.call(
            "toggleChatIsMarkedAsUnread", chat_id=chat_id, is_marked_as_unread=False
        )
    unread_left = left.get("count", before)
    data = {
        "marked_read": max(before - unread_left, 0),
        "unread_left": unread_left,
        "chat_id": chat_id,
    }
    return data, [render.kv(**data, title=chat.get("title", ""))]


def unique_path(directory: str, name: str) -> str:
    base, ext = os.path.splitext(name)
    path = os.path.join(directory, name)
    n = 1
    while os.path.exists(path):
        path = os.path.join(directory, f"{base}-{n}{ext}")
        n += 1
    return path


def download(ctx: Ctx, args: argparse.Namespace) -> Output:
    chat = ctx.resolve(args.chat)
    msg = ctx.call("getMessage", chat_id=chat["id"], message_id=args.msg_id)
    proxy = MsgProxy(msg)
    try:
        file_id = proxy.file_id
        size = proxy.size or 0
    except (KeyError, TypeError, IndexError, AttributeError):
        file_id, size = None, 0
    if not file_id:
        raise CliError(f"message {args.msg_id} has no file")
    max_size = utils.parse_size(args.max_size or config.MAX_DOWNLOAD_SIZE)
    if size > max_size:
        raise CliError(
            f"file is {utils.humanize_size(size)}, over the limit;"
            f" pass --max-size {math.ceil(size / 10**6)}MB to download it"
        )
    file = ctx.call(
        "downloadFile",
        timeout=DOWNLOAD_TIMEOUT,
        file_id=file_id,
        priority=32,
        offset=0,
        limit=0,
        synchronous=True,
    )
    local = file.get("local", {})
    path = local.get("path")
    if not path or not local.get("is_downloading_completed"):
        raise CliError("download did not complete")
    if args.out:
        out_dir = os.path.expanduser(args.out)
        os.makedirs(out_dir, exist_ok=True)
        name = proxy.file_name or os.path.basename(path)
        dest = unique_path(out_dir, os.path.basename(name))
        shutil.copyfile(path, dest)
        path = dest
    data = {"path": path, "size": utils.humanize_size(size or os.path.getsize(path))}
    return data, [render.kv(**data)]


def user_info(ctx: Ctx) -> Dict[str, Any]:
    me = ctx.me()
    usernames = (me.get("usernames") or {}).get("active_usernames") or []
    name = f"{me.get('first_name', '')} {me.get('last_name', '')}".strip()
    phone = me.get("phone_number", "")
    return {
        "user_id": me["id"],
        "name": name,
        "username": f"@{usernames[0]}" if usernames else None,
        "phone": f"…{phone[-2:]}" if phone else None,
        "session": config.FILES_DIR,
    }


def whoami(ctx: Ctx, args: argparse.Namespace) -> Output:
    info = user_info(ctx)
    return info, [render.kv(**info)]


def login(ctx: Ctx, args: argparse.Namespace) -> Output:
    info = {"logged_in": "yes", **user_info(ctx)}
    return info, [render.kv(**info)]


COMMANDS: Dict[str, Callable[[Ctx, argparse.Namespace], Output]] = {
    "unread": unread,
    "chats": chats,
    "history": history,
    "search": search,
    "send": send,
    "mark-read": mark_read,
    "download": download,
    "whoami": whoami,
    "login": login,
}
