import argparse
import io
import shlex
import unittest
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import patch

from tg import cli, config
from tg.cli import commands, render
from tg.cli.commands import Ctx
from tg.cli.session import EXIT_BUSY, EXIT_CHAT, EXIT_SEND, EXIT_USAGE, CliError

WRITE_METHODS = {
    "viewMessages",
    "openChat",
    "readAllChatMentions",
    "sendMessage",
    "toggleChatIsMarkedAsUnread",
}
ME = 999


def make_msg(chat_id: int, msg_id: int, text: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": msg_id,
        "chat_id": chat_id,
        "date": 1_700_000_000 + msg_id,
        "is_outgoing": False,
        "sender_id": {"@type": "messageSenderUser", "user_id": 1},
        "content": {"@type": "messageText", "text": {"text": text or f"m{msg_id}"}},
    }


def make_chat(
    chat_id: int,
    title: str,
    unread: int = 0,
    last_read: int = 0,
    mute_for: Optional[int] = 0,
    kind: str = "private",
    marked_unread: bool = False,
    last_message_id: int = 0,
) -> Dict[str, Any]:
    if kind == "private":
        chat_type: Dict[str, Any] = {"@type": "chatTypePrivate", "user_id": 1}
    elif kind == "channel":
        chat_type = {
            "@type": "chatTypeSupergroup",
            "supergroup_id": 7,
            "is_channel": True,
        }
    else:
        chat_type = {"@type": "chatTypeBasicGroup", "basic_group_id": 3}
    settings = (
        {"use_default_mute_for": True, "mute_for": 0}
        if mute_for is None
        else {"use_default_mute_for": False, "mute_for": mute_for}
    )
    return {
        "id": chat_id,
        "title": title,
        "type": chat_type,
        "unread_count": unread,
        "last_read_inbox_message_id": last_read,
        "unread_mention_count": 0,
        "notification_settings": settings,
        "is_marked_as_unread": marked_unread,
        "last_message": {"id": last_message_id} if last_message_id else None,
    }


class FakeSession:
    def __init__(
        self,
        chats: List[Dict[str, Any]],
        history: Optional[Dict[int, List[int]]] = None,
        search_hits: Optional[List[int]] = None,
        short_first_page: bool = True,
    ) -> None:
        self.chats = {c["id"]: c for c in chats}
        self.order = [c["id"] for c in chats]
        self.history = {
            k: sorted(v, reverse=True) for k, (v) in (history or {}).items()
        }
        self.search_hits = search_hits
        self.short_first_page = short_first_page
        self.log: List[Any] = []
        self.handlers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self.stale = False
        self.scope_muted: Dict[str, int] = {}
        self.send_result: Optional[str] = "ok"

    def call(self, method: str, timeout: float = 0, **params: Any) -> Dict[str, Any]:
        self.log.append((method, params))
        result: Dict[str, Any] = getattr(self, method)(**params)
        return result

    def on(self, update_type: str, func: Callable[[Dict[str, Any]], None]) -> None:
        self.handlers.setdefault(update_type, []).append(func)

    def fire(self, update_type: str, update: Dict[str, Any]) -> None:
        for func in self.handlers.get(update_type, []):
            func({"@type": update_type, **update})

    def methods(self) -> List[str]:
        return [method for method, _ in self.log]

    def getMe(self) -> Dict[str, Any]:
        return {"id": ME, "first_name": "Me", "usernames": {}}

    def getChat(self, chat_id: int) -> Dict[str, Any]:
        if chat_id not in self.chats:
            raise CliError("getChat: Chat not found")
        return self.chats[chat_id]

    def getUser(self, user_id: int) -> Dict[str, Any]:
        return {
            "id": user_id,
            "first_name": "Ann",
            "last_name": "",
            "type": {"@type": "userTypeRegular"},
            "usernames": {"active_usernames": ["ann"]},
        }

    def getSupergroup(self, supergroup_id: int) -> Dict[str, Any]:
        return {"usernames": None}

    def getScopeNotificationSettings(self, scope: Dict[str, str]) -> Dict[str, Any]:
        return {"mute_for": self.scope_muted.get(scope["@type"], 0)}

    def getChats(self, chat_list: Dict[str, str], limit: int) -> Dict[str, Any]:
        return {"chat_ids": self.order[:limit]}

    def searchChats(self, query: str, limit: int) -> Dict[str, Any]:
        if self.search_hits is not None:
            return {"chat_ids": self.search_hits}
        q = query.casefold()
        ids = [i for i in self.order if q in self.chats[i]["title"].casefold()]
        return {"chat_ids": ids[:limit]}

    def searchPublicChat(self, username: str) -> Dict[str, Any]:
        raise CliError("searchPublicChat: USERNAME_NOT_OCCUPIED")

    def createPrivateChat(self, user_id: int, force: bool) -> Dict[str, Any]:
        return make_chat(user_id, "Saved Messages")

    def getChatHistory(
        self,
        chat_id: int,
        from_message_id: int,
        offset: int,
        limit: int,
        only_local: bool,
    ) -> Dict[str, Any]:
        ids = self.history.get(chat_id, [])
        if from_message_id == 0:
            start = 0
            if self.short_first_page:
                limit = 1
                self.short_first_page = False
        else:
            start = next(
                (i for i, mid in enumerate(ids) if mid <= from_message_id), len(ids)
            )
        start = max(start + offset, 0)
        return {"messages": [make_msg(chat_id, i) for i in ids[start : start + limit]]}

    def sendMessage(self, chat_id: int, **params: Any) -> Dict[str, Any]:
        if self.send_result == "ok":
            self.fire(
                "updateMessageSendSucceeded",
                {"old_message_id": 1, "message": {"id": 555}},
            )
        elif self.send_result == "fail":
            self.fire(
                "updateMessageSendFailed",
                {"old_message_id": 1, "error": {"message": "CHAT_WRITE_FORBIDDEN"}},
            )
        return {"id": 1}

    def viewMessages(
        self, chat_id: int, message_ids: List[int], force_read: bool
    ) -> Dict[str, Any]:
        self.fire("updateChatReadInbox", {"chat_id": chat_id + 1, "unread_count": 9})
        self.fire("updateChatReadInbox", {"chat_id": chat_id, "unread_count": 0})
        return {}

    def toggleChatIsMarkedAsUnread(
        self, chat_id: int, is_marked_as_unread: bool
    ) -> Dict[str, Any]:
        return {}


def parse(argv: List[str]) -> argparse.Namespace:
    return cli.build_parser().parse_args(argv)


def run(session: FakeSession, argv: List[str]) -> Dict[str, Any]:
    args = parse(argv)
    data, _ = commands.COMMANDS[args.command](Ctx(session, args), args)  # type: ignore[arg-type]
    return data


def ctx(session: FakeSession) -> Ctx:
    return Ctx(session, parse(["whoami"]))  # type: ignore[arg-type]


class HistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = FakeSession([make_chat(1, "A")], {1: list(range(1, 251))})

    def ids(self, msgs: List[Dict[str, Any]]) -> List[int]:
        return [m["id"] for m in msgs]

    def test_older_from_latest_survives_short_first_page(self) -> None:
        msgs = ctx(self.session).history_older(1, 0, 20)
        self.assertEqual(self.ids(msgs), list(range(250, 230, -1)))

    def test_older_stops_at_after(self) -> None:
        msgs = ctx(self.session).history_older(1, 0, 50, after=240)
        self.assertEqual(self.ids(msgs), list(range(250, 240, -1)))

    def test_older_excludes_anchor(self) -> None:
        msgs = ctx(self.session).history_older(1, 100, 5)
        self.assertEqual(self.ids(msgs), [99, 98, 97, 96, 95])

    def test_newer_ascending_without_anchor(self) -> None:
        msgs = ctx(self.session).history_newer(1, 100, 150)
        self.assertEqual(self.ids(msgs), list(range(101, 251)))
        self.assertEqual(ctx(self.session).history_newer(1, 250, 10), [])

    def test_older_gives_up_on_repeating_pages(self) -> None:
        self.session.getChatHistory = lambda **kw: {"messages": []}  # type: ignore[method-assign]
        self.assertEqual(ctx(self.session).history_older(1, 0, 20), [])

    def follow(self, argv: List[str]) -> List[int]:
        seen: List[int] = []
        while argv:
            data = run(self.session, argv)
            seen += [m["msg_id"] for m in data["chat"]["messages"]]
            argv = shlex.split(data["next"])[1:] if data["next"] else []
        return seen

    def test_next_backwards_covers_everything_once(self) -> None:
        seen = self.follow(["history", "1", "--limit", "30"])
        self.assertEqual(sorted(seen), list(range(1, 251)))
        self.assertEqual(len(seen), len(set(seen)))

    def test_next_forwards_covers_everything_once(self) -> None:
        seen = self.follow(["history", "1", "--after", "100", "--limit", "40"])
        self.assertEqual(seen, list(range(101, 251)))

    def test_next_between_before_and_after(self) -> None:
        argv = ["history", "1", "--before", "200", "--after", "150", "--limit", "7"]
        seen = self.follow(argv)
        self.assertEqual(sorted(seen), list(range(151, 200)))


class ChatsTest(unittest.TestCase):
    def test_iter_chats_yields_each_chat_once(self) -> None:
        for count in (0, 99, 100, 200, 250):
            session = FakeSession([make_chat(i, f"c{i}") for i in range(1, count + 1)])
            ids = [c["id"] for c in ctx(session).iter_chats()]
            self.assertEqual(ids, list(range(1, count + 1)))

    def test_iter_chats_survives_reordering(self) -> None:
        session = FakeSession([make_chat(i, f"c{i}") for i in range(1, 151)])
        original = session.getChats

        def moving(chat_list: Dict[str, str], limit: int) -> Dict[str, Any]:
            if limit > 100:
                session.order.insert(0, session.order.pop(120))
            return original(chat_list, limit)

        session.getChats = moving  # type: ignore[method-assign]
        ids = [c["id"] for c in ctx(session).iter_chats()]
        self.assertEqual(sorted(ids), list(range(1, 151)))

    def test_chats_paging(self) -> None:
        session = FakeSession([make_chat(i, f"c{i}") for i in range(1, 6)])
        data = run(session, ["chats", "--limit", "2"])
        self.assertEqual([c["chat_id"] for c in data["chats"]], [1, 2])
        self.assertEqual(data["next"], "tg chats --offset 2 --limit 2")
        last = run(session, ["chats", "--limit", "2", "--offset", "4"])
        self.assertEqual([c["chat_id"] for c in last["chats"]], [5])
        self.assertIsNone(last["next"])


class ResolveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = FakeSession(
            [
                make_chat(1, "Team"),
                make_chat(2, "Team A"),
                make_chat(3, "Straße"),
                make_chat(4, "Annual report"),
            ]
        )

    def resolve(self, ref: str, strict: bool = False) -> int:
        chat_id: int = ctx(self.session).resolve(ref, strict)["id"]
        return chat_id

    def test_ids_and_titles(self) -> None:
        self.assertEqual(self.resolve("2"), 2)
        self.assertEqual(self.resolve("team"), 1)
        self.assertEqual(self.resolve("STRASSE".lower().replace("ss", "ß")), 3)
        self.assertEqual(self.resolve("me"), ME)

    def test_not_found(self) -> None:
        for ref in ("42", "@nobody", "nothing"):
            with self.assertRaises(CliError) as e:
                self.resolve(ref)
            self.assertEqual(e.exception.code, EXIT_CHAT)

    def test_ambiguous_lists_candidates(self) -> None:
        self.session.chats[5] = make_chat(5, "team")
        self.session.order.append(5)
        with self.assertRaises(CliError) as e:
            self.resolve("Team")
        self.assertEqual(e.exception.code, EXIT_CHAT)
        self.assertIn("chat_id=1", str(e.exception))
        self.assertIn("chat_id=5", str(e.exception))

    def test_strict_needs_exact_title(self) -> None:
        self.assertEqual(self.resolve("annual"), 4)
        with self.assertRaises(CliError) as e:
            self.resolve("annual", strict=True)
        self.assertEqual(e.exception.code, EXIT_CHAT)
        self.assertEqual(self.resolve("annual report", strict=True), 4)

    def test_falls_back_to_chat_list_when_search_misses(self) -> None:
        self.session.search_hits = []
        self.assertEqual(self.resolve("Straße"), 3)
        self.assertIn("getChats", self.session.methods())


class UnreadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = FakeSession(
            [
                make_chat(1, "read"),
                make_chat(2, "unread", unread=3, last_read=7),
                make_chat(3, "muted", unread=2, mute_for=3600),
                make_chat(4, "default muted", unread=1, mute_for=None, kind="channel"),
                make_chat(5, "marked", marked_unread=True),
                make_chat(6, "many", unread=15, last_read=5),
            ],
            {2: list(range(1, 11)), 6: list(range(1, 21))},
            short_first_page=False,
        )
        self.session.scope_muted["notificationSettingsScopeChannelChats"] = 999

    def test_skips_muted_and_shows_newest_unread(self) -> None:
        data = run(self.session, ["unread"])
        self.assertEqual([c["chat_id"] for c in data["chats"]], [2, 5, 6])
        self.assertEqual(data["muted_skipped"], 2)
        messages = [m["msg_id"] for m in data["chats"][0]["messages"]]
        self.assertEqual(messages, [8, 9, 10])
        many = data["chats"][2]
        self.assertEqual([m["msg_id"] for m in many["messages"]], list(range(11, 21)))
        self.assertEqual(many["more"], "tg history 6 --before 11 --after 5")
        self.assertNotIn("more", data["chats"][0])

    def test_muted_flag_and_paging(self) -> None:
        data = run(self.session, ["unread", "--muted", "--limit", "2"])
        self.assertEqual([c["chat_id"] for c in data["chats"]], [2, 3])
        self.assertEqual(
            data["next"], "tg unread --offset 2 --limit 2 --per-chat 10 --muted"
        )
        data = run(self.session, ["unread", "--muted", "--limit", "2", "--offset", "4"])
        self.assertEqual([c["chat_id"] for c in data["chats"]], [6])
        self.assertIsNone(data["next"])

    def test_scope_settings_fetched_once(self) -> None:
        run(self.session, ["unread"])
        self.assertEqual(
            self.session.methods().count("getScopeNotificationSettings"), 1
        )

    def test_reading_never_writes(self) -> None:
        for argv in (
            ["unread", "--muted"],
            ["chats"],
            ["history", "6"],
            ["unread", "--chat", "2"],
        ):
            run(self.session, argv)
        self.assertFalse(WRITE_METHODS & set(self.session.methods()))


class SendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = FakeSession([make_chat(1, "Ann"), make_chat(2, "Bob")])
        patcher = patch.object(commands, "SEND_TIMEOUT", 0.05)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, enabled: bool, allowlist: List[Any], argv: List[str]) -> Any:
        with (
            patch.object(config, "CLI_SEND", enabled),
            patch.object(config, "CLI_SEND_ALLOWLIST", allowlist),
        ):
            return run(self.session, ["send", *argv])

    def assert_blocked(self, code: int, *call: Any) -> None:
        with self.assertRaises(CliError) as e:
            self.send(*call)
        self.assertEqual(e.exception.code, code)
        self.assertNotIn("sendMessage", self.session.methods())

    def test_gating(self) -> None:
        self.assert_blocked(EXIT_SEND, False, [], ["1", "hi"])
        self.assert_blocked(EXIT_SEND, True, [2], ["1", "hi"])
        self.assert_blocked(EXIT_SEND, True, ["@bob"], ["1", "hi"])
        self.assert_blocked(EXIT_USAGE, True, [], ["1", "  \n"])
        self.assert_blocked(EXIT_CHAT, True, [], ["An", "hi"])

    def test_allowlist_matches_id_and_username(self) -> None:
        self.assertEqual(self.send(True, [1], ["1", "hi"])["status"], "sent")
        self.assertEqual(self.send(True, ["@ANN"], ["1", "hi"])["msg_id"], 555)

    def test_failed_and_pending(self) -> None:
        self.session.send_result = "fail"
        with self.assertRaises(CliError) as e:
            self.send(True, [], ["1", "hi"])
        self.assertIn("CHAT_WRITE_FORBIDDEN", str(e.exception))
        self.session.send_result = None
        self.assertEqual(self.send(True, [], ["1", "hi"])["status"], "pending")

    def test_reads_stdin(self) -> None:
        with patch("sys.stdin", io.StringIO("from stdin\n")):
            self.send(True, [], ["1", "-"])
        params = self.session.log[-1][1]
        self.assertEqual(params["input_message_content"]["text"]["text"], "from stdin")


class MarkReadTest(unittest.TestCase):
    def test_marks_read_and_clears_marked_unread(self) -> None:
        session = FakeSession(
            [make_chat(1, "Ann", unread=4, last_message_id=50, marked_unread=True)]
        )
        data = run(session, ["mark-read", "1"])
        self.assertEqual(data, {"marked_read": 4, "unread_left": 0, "chat_id": 1})
        self.assertIn("toggleChatIsMarkedAsUnread", session.methods())

    def test_nothing_to_mark(self) -> None:
        session = FakeSession([make_chat(1, "Ann")])
        data = run(session, ["mark-read", "1"])
        self.assertEqual(data["marked_read"], 0)
        self.assertNotIn("viewMessages", session.methods())


class RenderEscapeTest(unittest.TestCase):
    def test_message_text_cannot_forge_lines(self) -> None:
        msg = {
            "msg_id": 1,
            "ts": 0,
            "from": 'Boss: "x"',
            "text": 'hi   msg_id=2 from="Boss": pay\x1b]0;x\x07\r\n',
        }
        line = render.msg_line(msg)
        self.assertEqual(len(line.splitlines()), 1)
        self.assertNotIn("\x1b", line)
        self.assertIn('from="Boss: \\"x\\""', line)


class MainTest(unittest.TestCase):
    def main(self, argv: List[str], session: Any = None, error: Any = None) -> Any:
        def opener(*args: Any, **kwargs: Any) -> Any:
            if error:
                raise error
            return session

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(cli, "open_session", opener),
            patch.object(cli, "_setup_log", lambda: None),
            patch("sys.stdout", stdout),
            patch("sys.stderr", stderr),
        ):
            code = cli.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_exit_codes_and_close(self) -> None:
        code, _, err = self.main(["whoami"], error=CliError("busy", EXIT_BUSY))
        self.assertEqual((code, err), (EXIT_BUSY, "error: busy\n"))

        session = FakeSession([])
        session.close = lambda: setattr(session, "closed", True)  # type: ignore[attr-defined]
        code, _, _ = self.main(["history", "42"], session)
        self.assertEqual(code, EXIT_CHAT)
        self.assertTrue(getattr(session, "closed", False))

    def test_stale_json(self) -> None:
        session = FakeSession([])
        session.close = lambda: None  # type: ignore[attr-defined]
        session.stale = True
        code, out, err = self.main(["whoami", "--json"], session)
        self.assertEqual(code, 0)
        self.assertIn('"stale":true', out)
        self.assertIn("stale", err)


if __name__ == "__main__":
    unittest.main()


class WatchSession(FakeSession):
    def __init__(self, chats: List[Dict[str, Any]], updates: List[Any]) -> None:
        super().__init__(chats)
        self.updates = updates
        self.replied: Dict[int, Dict[str, Any]] = {}

    def on(self, update_type: str, func: Callable[[Dict[str, Any]], None]) -> None:
        for msg in self.updates:
            func({"@type": update_type, "message": msg})

    def getMessage(self, chat_id: int, message_id: int) -> Dict[str, Any]:
        if message_id not in self.replied:
            raise CliError("getMessage: not found")
        return self.replied[message_id]


class WatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.chats = [make_chat(1, "Ann"), make_chat(2, "Muted", mute_for=60)]

    def watch(self, updates: List[Any], argv: List[str]) -> List[str]:
        session = WatchSession(self.chats, updates)
        out = io.StringIO()
        with patch("sys.stdout", out):
            self.assertIsNone(run_raw(session, ["watch", *argv]))
        return out.getvalue().splitlines()

    def test_prints_incoming_and_stops_at_count(self) -> None:
        own = {**make_msg(1, 9), "is_outgoing": True}
        lines = self.watch([own, make_msg(2, 5), make_msg(1, 10)], ["--count", "1"])
        self.assertEqual(len(lines), 1)
        self.assertIn("chat_id=1", lines[0])
        self.assertIn("msg_id=10", lines[0])

    def test_chat_filter_and_json(self) -> None:
        updates = [make_msg(2, 5), make_msg(1, 6)]
        lines = self.watch(updates, ["--chat", "2", "--count", "1", "--json"])
        self.assertIn('"msg_id":5', lines[0])

    def test_mentions_only(self) -> None:
        plain = make_msg(1, 7)
        mention = {**make_msg(1, 8), "contains_unread_mention": True}
        lines = self.watch([plain, mention], ["--mentions", "--count", "1"])
        self.assertIn("msg_id=8", lines[0])

    def test_reply_to_me_counts_as_mention(self) -> None:
        reply = {
            **make_msg(1, 9),
            "reply_to": {"@type": "messageReplyToMessage", "message_id": 3},
        }
        session = WatchSession(self.chats, [make_msg(1, 7), reply])
        session.replied[3] = {"id": 3, "is_outgoing": True}
        out = io.StringIO()
        with patch("sys.stdout", out):
            run_raw(session, ["watch", "--mentions", "--count", "1"])
        self.assertIn("msg_id=9", out.getvalue())

    def test_timeout(self) -> None:
        with self.assertRaises(CliError) as e:
            self.watch([make_msg(1, 7)], ["--count", "2", "--timeout", "0.05"])
        self.assertEqual(e.exception.code, commands.EXIT_TIMEOUT)


def run_raw(session: FakeSession, argv: List[str]) -> Any:
    args = parse(argv)
    return commands.COMMANDS[args.command](Ctx(session, args), args)  # type: ignore[arg-type]
