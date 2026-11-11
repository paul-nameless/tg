import argparse
import importlib.resources
import logging
import os
import shutil
import sys
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List

from tg import config
from tg.cli import render
from tg.cli.session import EXIT_ERROR, CliError, open_session

SKILL_DIR = os.path.expanduser("~/.claude/skills/tg")


def _bounded(low: int, high: int) -> Any:
    def parse(value: str) -> int:
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return number

    return parse


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="print JSON")
    common.add_argument(
        "--max-chars",
        type=int,
        default=400,
        help="cut each message text to N chars, 0 for no limit (default 400)",
    )
    common.add_argument(
        "--sync-timeout",
        type=float,
        default=5.0,
        help="seconds to wait for Telegram to sync, 0 for local data only",
    )
    archive = argparse.ArgumentParser(add_help=False)
    archive.add_argument(
        "--archive", action="store_true", help="use the archive chat list"
    )

    parser = argparse.ArgumentParser(
        prog="tg",
        description="Terminal Telegram client. Run without arguments for the TUI.",
        epilog="Exit codes: 0 ok, 1 error, 2 usage, 3 not logged in,"
        " 4 chat not found or ambiguous, 5 send not allowed, 6 session busy",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser(
        "unread", parents=[common, archive], help="unread chats with their messages"
    )
    p.add_argument("--limit", type=_bounded(1, 200), default=20, help="chats")
    p.add_argument("--offset", type=_bounded(0, 5000), default=0)
    p.add_argument("--per-chat", type=_bounded(1, 200), default=10, help="messages")
    p.add_argument("--muted", action="store_true", help="include muted chats")
    p.add_argument("--chat", help="only this chat")

    p = sub.add_parser("chats", parents=[common, archive], help="list chats")
    p.add_argument("--limit", type=_bounded(1, 500), default=30)
    p.add_argument("--offset", type=_bounded(0, 5000), default=0)
    p.add_argument("--unread", action="store_true", help="only unread chats")
    p.add_argument("--query", help="search chats by title or username")

    p = sub.add_parser("history", parents=[common], help="messages of a chat")
    p.add_argument("chat", help="chat_id, @username, me, or title")
    p.add_argument("--limit", type=_bounded(1, 200), default=20)
    p.add_argument("--before", type=int, help="messages older than this msg_id")
    p.add_argument("--after", type=int, help="messages newer than this msg_id")

    p = sub.add_parser("search", parents=[common, archive], help="search messages")
    p.add_argument("query")
    p.add_argument("--chat", help="search only in this chat")
    p.add_argument("--limit", type=_bounded(1, 100), default=20)
    p.add_argument("--offset", help="value from the previous next: line")

    p = sub.add_parser("send", parents=[common], help="send a text message")
    p.add_argument("chat")
    p.add_argument("text", help="message text, - reads stdin")
    p.add_argument("--reply-to", type=int, help="msg_id to reply to")

    p = sub.add_parser("mark-read", parents=[common], help="mark a chat as read")
    p.add_argument("chat")
    p.add_argument("--up-to", type=int, help="mark read up to this msg_id")

    p = sub.add_parser("download", parents=[common], help="download a message file")
    p.add_argument("chat")
    p.add_argument("msg_id", type=int)
    p.add_argument("--out", help="copy the file into this directory")
    p.add_argument("--max-size", help=f"size limit, default {config.MAX_DOWNLOAD_SIZE}")

    sub.add_parser("whoami", parents=[common], help="show the logged in account")
    sub.add_parser("login", parents=[common], help="log in interactively")

    p = sub.add_parser("skill", help="agent skill file")
    p.add_argument("action", choices=["install", "path"])
    p.add_argument("--dir", default=SKILL_DIR, help=f"default {SKILL_DIR}")
    return parser


def _skill_source() -> str:
    return str(importlib.resources.files("tg").joinpath("resources/skill/SKILL.md"))


def skill(args: argparse.Namespace) -> int:
    source = _skill_source()
    if args.action == "path":
        print(source)
        return 0
    target_dir = os.path.expanduser(args.dir)
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, "SKILL.md")
    shutil.copyfile(source, target)
    print(f"installed={target}")
    return 0


def _setup_log() -> None:
    try:
        os.makedirs(config.LOG_PATH, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            os.path.join(config.LOG_PATH, "cli.log"),
            maxBytes=8 * 1024 * 1024,
            backupCount=1,
        )
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(levelname)s [%(asctime)s] %(filename)s:%(lineno)s | %(message)s"
        )
    )
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(config.LOG_LEVEL)


def _emit(data: Dict[str, Any], lines: List[str], args: argparse.Namespace) -> None:
    if args.json:
        print(render.to_json(data))
    else:
        print(render.to_text(lines))
    sys.stdout.flush()


def main(argv: List[str]) -> int:
    from tg.cli.commands import COMMANDS, Ctx

    args = build_parser().parse_args(argv)
    if args.command == "skill":
        return skill(args)
    _setup_log()
    try:
        session = open_session(args.sync_timeout, interactive=args.command == "login")
        try:
            data, lines = COMMANDS[args.command](Ctx(session, args), args)
            if session.stale:
                data["stale"] = True
                print(
                    "warning: not synced with Telegram, data may be stale",
                    file=sys.stderr,
                )
            _emit(data, lines, args)
        finally:
            session.close()
    except CliError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        logging.exception("cli command failed")
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ERROR
    return 0
