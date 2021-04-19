import logging
from functools import wraps
from typing import Any, Callable, Dict

from tg import config, utils
from tg.controllers import Controller
from tg.msg import MsgProxy

log = logging.getLogger(__name__)

UpdateHandler = Callable[[Controller, Dict[str, Any]], None]

handlers: Dict[str, UpdateHandler] = {}

max_download_size: int = utils.parse_size(config.MAX_DOWNLOAD_SIZE)


def update_handler(
    update_type: str,
) -> Callable[[UpdateHandler], UpdateHandler]:
    def decorator(fun: UpdateHandler) -> UpdateHandler:
        global handlers
        assert (
            update_type not in handlers
        ), f"Update type <{update_type}> already has handler: {handlers[update_type]}"

        @wraps(fun)
        def wrapper(controller: Controller, update: Dict[str, Any]) -> None:
            try:
                fun(controller, update)
            except Exception:
                log.exception("Error happened in handler: %s", update_type)

        handlers[update_type] = wrapper
        return wrapper

    return decorator


@update_handler("updateMessageContent")
def update_message_content(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["chat_id"]
    message_id = update["message_id"]
    controller.model.msgs.update_msg(
        chat_id, message_id, content=update["new_content"]
    )

    current_chat_id = controller.model.current_chat_id
    if current_chat_id == chat_id:
        controller.render_msgs()


@update_handler("updateMessageEdited")
def update_message_edited(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["chat_id"]
    message_id = update["message_id"]
    edit_date = update["edit_date"]
    controller.model.msgs.update_msg(chat_id, message_id, edit_date=edit_date)

    current_chat_id = controller.model.current_chat_id
    if current_chat_id == chat_id:
        controller.render_msgs()


@update_handler("updateNewMessage")
def update_new_message(controller: Controller, update: Dict[str, Any]) -> None:
    msg = MsgProxy(update["message"])
    controller.model.msgs.add_message(msg.chat_id, msg.msg)
    current_chat_id = controller.model.current_chat_id
    if current_chat_id == msg.chat_id:
        controller.render_msgs()
    if msg.file_id and msg.size and msg.size <= max_download_size:
        controller.download(msg.file_id, msg.chat_id, msg["id"])

    controller.notify_for_message(msg.chat_id, msg)


# outdated
@update_handler("updateChatOrder")
def update_chat_order(controller: Controller, update: Dict[str, Any]) -> None:
    current_chat_id = controller.model.current_chat_id
    chat_id = update["chat_id"]
    order = update["order"]

    if controller.model.chats.update_chat(chat_id, order=order):
        controller.refresh_current_chat(current_chat_id)


@update_handler("updateChatPosition")
def update_chat_position(
    controller: Controller, update: Dict[str, Any]
) -> None:
    current_chat_id = controller.model.current_chat_id
    chat_id = update["chat_id"]
    info = {}
    info["order"] = update["position"]["order"]
    if "is_pinned" in update:
        info["is_pinned"] = update["is_pinned"]
    if controller.model.chats.update_chat(chat_id, **info):
        controller.refresh_current_chat(current_chat_id)


@update_handler("updateChatTitle")
def update_chat_title(controller: Controller, update: Dict[str, Any]) -> None:
    chat_id = update["chat_id"]
    title = update["title"]

    current_chat_id = controller.model.current_chat_id
    if controller.model.chats.update_chat(chat_id, title=title):
        controller.refresh_current_chat(current_chat_id)


@update_handler("updateChatIsMarkedAsUnread")
def update_chat_is_marked_as_unread(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["chat_id"]
    is_marked_as_unread = update["is_marked_as_unread"]

    current_chat_id = controller.model.current_chat_id
    if controller.model.chats.update_chat(
        chat_id, is_marked_as_unread=is_marked_as_unread
    ):
        controller.refresh_current_chat(current_chat_id)


@update_handler("updateNewChat")
def update_new_chat(controller: Controller, update: Dict[str, Any]) -> None:
    chat = update["chat"]
    controller.model.chats.add_chat(chat)


@update_handler("updateChatIsPinned")
def update_chat_is_pinned(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["chat_id"]
    is_pinned = update["is_pinned"]
    order = update["order"]

    current_chat_id = controller.model.current_chat_id
    if controller.model.chats.update_chat(
        chat_id, is_pinned=is_pinned, order=order
    ):
        controller.refresh_current_chat(current_chat_id)


@update_handler("updateChatReadOutbox")
def update_chat_read_outbox(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["chat_id"]
    last_read_outbox_message_id = update["last_read_outbox_message_id"]

    current_chat_id = controller.model.current_chat_id
    if controller.model.chats.update_chat(
        chat_id, last_read_outbox_message_id=last_read_outbox_message_id
    ):
        controller.refresh_current_chat(current_chat_id)


@update_handler("updateChatReadInbox")
def update_chat_read_inbox(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["chat_id"]
    last_read_inbox_message_id = update["last_read_inbox_message_id"]
    unread_count = update["unread_count"]

    current_chat_id = controller.model.current_chat_id
    if controller.model.chats.update_chat(
        chat_id,
        last_read_inbox_message_id=last_read_inbox_message_id,
        unread_count=unread_count,
    ):
        controller.refresh_current_chat(current_chat_id)


@update_handler("updateChatDraftMessage")
def update_chat_draft_message(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["chat_id"]
    # FIXME: ignoring draft message itself for now because UI can't show it
    # draft_message = update["draft_message"]
    order = update["order"]

    current_chat_id = controller.model.current_chat_id
    if controller.model.chats.update_chat(chat_id, order=order):
        controller.refresh_current_chat(current_chat_id)


@update_handler("updateChatLastMessage")
def update_chat_last_message(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["chat_id"]
    last_message = update.get("last_message")
    if not last_message:
        # according to documentation it can be null
        log.warning("last_message is null: %s", update)
        return

    info = {}
    info["last_message"] = last_message
    if len(update["positions"]) > 0:
        info["order"] = update["positions"][0]["order"]

    current_chat_id = controller.model.current_chat_id
    if controller.model.chats.update_chat(chat_id, **info):
        controller.refresh_current_chat(current_chat_id)


@update_handler("updateChatNotificationSettings")
def update_chat_notification_settings(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["chat_id"]
    notification_settings = update["notification_settings"]
    if controller.model.chats.update_chat(
        chat_id, notification_settings=notification_settings
    ):
        controller.render()


@update_handler("updateMessageSendSucceeded")
def update_message_send_succeeded(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["message"]["chat_id"]
    msg_id = update["old_message_id"]
    controller.model.msgs.add_message(chat_id, update["message"])
    controller.model.msgs.remove_messages(chat_id, [msg_id])

    current_chat_id = controller.model.current_chat_id
    if current_chat_id == chat_id:
        controller.render_msgs()


@update_handler("updateFile")
def update_file(controller: Controller, update: Dict[str, Any]) -> None:
    file_id = update["file"]["id"]
    local = update["file"]["local"]
    chat_id, msg_id = controller.model.downloads.get(file_id, (None, None))
    if chat_id is None or msg_id is None:
        log.warning(
            "Can't find information about file with file_id=%s", file_id
        )
        return
    msg = controller.model.msgs.msgs[chat_id].get(msg_id)
    if not msg:
        return
    proxy = MsgProxy(msg)
    proxy.local = local
    controller.render_msgs()
    if proxy.is_downloaded:
        controller.model.downloads.pop(file_id)


@update_handler("updateMessageContentOpened")
def update_message_content_opened(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["chat_id"]
    message_id = update["message_id"]
    controller.model.msgs.update_msg_content_opened(chat_id, message_id)
    controller.render_msgs()


@update_handler("updateDeleteMessages")
def update_delete_messages(
    controller: Controller, update: Dict[str, Any]
) -> None:
    if not update["is_permanent"]:
        log.debug("Ignoring deletiong becuase not permanent: %s", update)
        return
    chat_id = update["chat_id"]
    msg_ids = update["message_ids"]
    controller.model.msgs.remove_messages(chat_id, msg_ids)
    controller.render_msgs()


@update_handler("updateConnectionState")
def update_connection_state(
    controller: Controller, update: Dict[str, Any]
) -> None:
    state = update["state"]["@type"]
    states = {
        "connectionStateWaitingForNetwork": "Waiting for network...",
        "connectionStateConnectingToProxy": "Connecting to proxy...",
        "connectionStateConnecting": "Connecting...",
        "connectionStateUpdating": "Updating...",
        # state exists, but when it's "Ready" we want to show "Chats"
        # "connectionStateReady": "Ready",
    }
    controller.model.chats.title = states.get(state, "Chats")
    controller.render_chats()


@update_handler("updateUserStatus")
def update_user_status(controller: Controller, update: Dict[str, Any]) -> None:
    controller.model.users.set_status(update["user_id"], update["status"])
    controller.render()


@update_handler("updateBasicGroup")
def update_basic_group(controller: Controller, update: Dict[str, Any]) -> None:
    basic_group = update["basic_group"]
    controller.model.users.groups[basic_group["id"]] = basic_group
    controller.render_msgs()


@update_handler("updateSupergroup")
def update_supergroup(controller: Controller, update: Dict[str, Any]) -> None:
    supergroup = update["supergroup"]
    controller.model.users.supergroups[supergroup["id"]] = supergroup
    controller.render_msgs()


@update_handler("updateUserChatAction")
def update_user_chat_action(
    controller: Controller, update: Dict[str, Any]
) -> None:
    chat_id = update["chat_id"]
    if update["action"]["@type"] == "chatActionCancel":
        controller.model.users.actions.pop(chat_id, None)
    else:
        controller.model.users.actions[chat_id] = update
    controller.render()
