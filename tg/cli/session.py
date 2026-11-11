import ctypes
import fcntl
import os
import threading
import time
from typing import IO, Any, Callable, Dict, Optional

from telegram.client import AsyncResult, AuthorizationState

from tg import config
from tg.tdlib import Tdlib

EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_CHAT = 4
EXIT_SEND = 5
EXIT_BUSY = 6
EXIT_TIMEOUT = 7

CALL_TIMEOUT = 30.0
LOCK_TIMEOUT = 30.0
NOT_LOGGED_IN = 'not logged in: run "tg login" in a terminal'
TUI_RUNNING = "session busy: tg TUI is running, close it first"


class CliError(Exception):
    def __init__(self, message: str, code: int = EXIT_ERROR) -> None:
        super().__init__(message)
        self.code = code


class Session:
    def __init__(self, tg: Tdlib, lock_file: IO[str]) -> None:
        self.tg = tg
        self.stale = False
        self._lock_file = lock_file

    def call(
        self, method: str, timeout: float = CALL_TIMEOUT, **params: Any
    ) -> Dict[str, Any]:
        result = self.tg.call_method(method, params)
        try:
            result.wait(timeout=timeout)
        except TimeoutError:
            raise CliError(f"{method}: no response in {timeout:.0f}s")
        if result.error:
            info = result.error_info or {}
            raise CliError(f"{method}: {info.get('message', info)}")
        return result.update or {}

    def on(self, update_type: str, func: Callable[[Dict[str, Any]], None]) -> None:
        self.tg.add_update_handler(update_type, func)

    def close(self) -> None:
        try:
            self.tg.stop()
        finally:
            self._lock_file.close()


def _acquire_lock() -> IO[str]:
    os.makedirs(config.FILES_DIR, exist_ok=True)
    lock_file = open(os.path.join(config.FILES_DIR, "cli.lock"), "w")
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_file
        except BlockingIOError:
            if time.monotonic() > deadline:
                lock_file.close()
                raise CliError("session busy: another tg command is running", EXIT_BUSY)
            time.sleep(0.2)


def _quiet_tdlib() -> None:
    if not config.TDLIB_PATH:
        return
    try:
        lib = ctypes.CDLL(config.TDLIB_PATH)
        lib.td_set_log_verbosity_level(ctypes.c_int(config.TDLIB_VERBOSITY))
    except (OSError, AttributeError):
        pass


def _authorize(tg: Tdlib) -> None:
    actions: Dict[AuthorizationState, Callable[[], AsyncResult]] = {
        AuthorizationState.NONE: tg.get_authorization_state,
        AuthorizationState.WAIT_TDLIB_PARAMETERS: tg._set_initial_params,
        AuthorizationState.WAIT_ENCRYPTION_KEY: tg._send_encryption_key,
    }
    state = AuthorizationState.NONE
    while state != AuthorizationState.READY:
        action = actions.get(state)
        if action is None:
            raise CliError(NOT_LOGGED_IN, EXIT_AUTH)
        try:
            state = tg._wait_authorization_result(action(), timeout=CALL_TIMEOUT)
        except TimeoutError:
            raise CliError("TDLib did not respond while opening the session")
        except RuntimeError as e:
            if "lock" in str(e).lower():
                raise CliError(TUI_RUNNING, EXIT_BUSY)
            raise CliError(f"TDLib: {e}")
    tg.authorization_state = state


def open_session(sync_timeout: float, interactive: bool = False) -> Session:
    lock_file = _acquire_lock()
    try:
        phone: Optional[str] = (
            config.ensure_phone() if interactive else config.PHONE or "+0"
        )
        _quiet_tdlib()
        tg = Tdlib(
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            phone=phone,
            database_encryption_key=config.ENC_KEY,
            files_directory=config.FILES_DIR,
            tdlib_verbosity=config.TDLIB_VERBOSITY,
            library_path=config.TDLIB_PATH,
        )
    except BaseException:
        lock_file.close()
        raise

    session = Session(tg, lock_file)
    connected = threading.Event()

    def on_connection(update: Dict[str, Any]) -> None:
        if update.get("state", {}).get("@type") == "connectionStateReady":
            connected.set()

    session.on("updateConnectionState", on_connection)
    try:
        try:
            _authorize(tg)
        except CliError as e:
            if not interactive or e.code != EXIT_AUTH:
                raise
            tg.login_interactive()
        session.call(
            "setOption",
            name="online",
            value={"@type": "optionValueBoolean", "value": False},
        )
        session.stale = not connected.wait(sync_timeout)
    except BaseException:
        session.close()
        raise
    return session
