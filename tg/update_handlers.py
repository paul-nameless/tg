import logging
from functools import wraps
from typing import Any, Callable, Dict, Optional

from tg import config
from tg.controllers import Controller
from tg.msg import MsgProxy

log = logging.getLogger(__name__)

_update_handler_type = Callable[[Controller, Dict[str, Any]], None]

handlers: Dict[str, _update_handler_type] = {}


def update_handler(update_type):
    def decorator(fun):
        global handlers
        assert (
            update_type not in handlers
        ), f"Update type <{update_type}> already has handler: {handlers[update_type]}"

        handlers[update_type] = fun

        @wraps(fun)
        def wrapper(*args, **kwargs):
            try:
                return fun(*args, **kwargs)
            except Exception:
                log.exception("Error happened in %s handler", fun.__name__)

        return wrapper

    return decorator


@update_handler("updateMessageContent")
def update_msg_content(controller: Controller, update: Dict[str, Any]):
    chat_id = update["chat_id"]
    message_id = update["message_id"]
    controller.model.msgs.update_msg_content(
        chat_id, message_id, update["new_content"]
    )
    current_chat_id = controller.model.chats.id_by_index(
        controller.model.current_chat
    )
    if current_chat_id == chat_id:
        controller.refresh_msgs()


@update_handler("updateNewMessage")
def update_new_msg(controller: Controller, update: Dict[str, Any]):
    msg = MsgProxy(update["message"])
    controller.model.msgs.add_message(msg.chat_id, msg.msg)
    current_chat_id = controller.model.chats.id_by_index(
        controller.model.current_chat
    )
    if current_chat_id == msg.chat_id:
        controller.refresh_msgs()
    if msg.file_id and msg.size <= config.MAX_DOWNLOAD_SIZE:
        controller.download(msg.file_id, msg.chat_id, msg["id"])

    controller._notify_for_message(msg.chat_id, msg)


@update_handler("updateChatOrder")
def update_chat_order(controller: Controller, update: Dict[str, Any]):
    log.info("Proccessing updateChatOrder")
    current_chat_id = controller.model.chats.id_by_index(
        controller.model.current_chat
    )
    chat_id = update["chat_id"]
    order = update["order"]

    controller.model.chats.update_chat(chat_id, order=order)
    controller._refresh_current_chat(current_chat_id)


@update_handler("updateChatTitle")
def update_chat_title(controller: Controller, update: Dict[str, Any]):
    log.info("Proccessing updateChatTitle")
    chat_id = update["chat_id"]
    title = update["title"]
    current_chat_id = controller.model.chats.id_by_index(
        controller.model.current_chat
    )
    controller.model.chats.update_chat(chat_id, title=title)
    controller._refresh_current_chat(current_chat_id)


@update_handler("updateChatIsMarkedAsUnread")
def update_chat_marked_as_unread(
    controller: Controller, update: Dict[str, Any]
):
    log.info("Proccessing updateChatIsMarkedAsUnread")
    chat_id = update["chat_id"]
    is_marked_as_unread = update["is_marked_as_unread"]
    current_chat_id = controller.model.chats.id_by_index(
        controller.model.current_chat
    )
    controller.model.chats.update_chat(
        chat_id, is_marked_as_unread=is_marked_as_unread
    )
    controller._refresh_current_chat(current_chat_id)


@update_handler("updateChatIsPinned")
def update_chat_is_pinned(controller: Controller, update: Dict[str, Any]):
    log.info("Proccessing updateChatIsPinned")
    chat_id = update["chat_id"]
    is_pinned = update["is_pinned"]
    order = update["order"]
    current_chat_id = controller.model.chats.id_by_index(
        controller.model.current_chat
    )
    controller.model.chats.update_chat(
        chat_id, is_pinned=is_pinned, order=order
    )
    controller._refresh_current_chat(current_chat_id)


@update_handler("updateChatReadOutbox")
def update_chat_read_outbox(controller: Controller, update: Dict[str, Any]):
    log.info("Proccessing updateChatReadOutbox")
    chat_id = update["chat_id"]
    last_read_outbox_message_id = update["last_read_outbox_message_id"]
    current_chat_id = controller.model.chats.id_by_index(
        controller.model.current_chat
    )
    controller.model.chats.update_chat(
        chat_id, last_read_outbox_message_id=last_read_outbox_message_id,
    )
    controller._refresh_current_chat(current_chat_id)


@update_handler("updateChatReadInbox")
def update_chat_read_inbox(controller: Controller, update: Dict[str, Any]):
    log.info("Proccessing updateChatReadInbox")
    chat_id = update["chat_id"]
    last_read_inbox_message_id = update["last_read_inbox_message_id"]
    unread_count = update["unread_count"]
    current_chat_id = controller.model.chats.id_by_index(
        controller.model.current_chat
    )
    controller.model.chats.update_chat(
        chat_id,
        last_read_inbox_message_id=last_read_inbox_message_id,
        unread_count=unread_count,
    )
    controller._refresh_current_chat(current_chat_id)


@update_handler("updateChatDraftMessage")
def update_chat_draft_msg(controller: Controller, update: Dict[str, Any]):
    log.info("Proccessing updateChatDraftMessage")
    chat_id = update["chat_id"]
    # FIXME: ignoring draft message itself for now because UI can't show it
    # draft_message = update["draft_message"]
    order = update["order"]
    current_chat_id = controller.model.chats.id_by_index(
        controller.model.current_chat
    )
    controller.model.chats.update_chat(chat_id, order=order)
    controller._refresh_current_chat(current_chat_id)


@update_handler("updateChatLastMessage")
def update_chat_last_msg(controller: Controller, update: Dict[str, Any]):
    log.info("Proccessing updateChatLastMessage")
    chat_id = update["chat_id"]
    message = update["last_message"]
    order = update["order"]
    current_chat_id = controller.model.chats.id_by_index(
        controller.model.current_chat
    )
    controller.model.chats.update_chat(
        chat_id, last_message=message, order=order
    )
    controller._refresh_current_chat(current_chat_id)


@update_handler("updateChatNotificationSettings")
def update_chat_notification_settings(controller: Controller, update):
    log.info("Proccessing update_chat_notification_settings")
    chat_id = update["chat_id"]
    notification_settings = update["notification_settings"]
    controller.model.chats.update_chat(
        chat_id, notification_settings=notification_settings
    )
    controller.render()


@update_handler("updateMessageSendSucceeded")
def update_msg_send_succeeded(controller: Controller, update):
    chat_id = update["message"]["chat_id"]
    msg_id = update["old_message_id"]
    controller.model.msgs.add_message(chat_id, update["message"])
    controller.model.msgs.remove_message(chat_id, msg_id)
    current_chat_id = controller.model.chats.id_by_index(
        controller.model.current_chat
    )
    if current_chat_id == chat_id:
        controller.refresh_msgs()


@update_handler("updateFile")
def update_file(controller: Controller, update):
    log.info("update_file: %s", update)
    file_id = update["file"]["id"]
    local = update["file"]["local"]
    chat_id, msg_id = controller.model.downloads.get(file_id, (None, None))
    if chat_id is None:
        log.warning(
            "Can't find information about file with file_id=%s", file_id
        )
        return
    msgs = controller.model.msgs.msgs[chat_id]
    for msg in msgs:
        if msg["id"] == msg_id:
            proxy = MsgProxy(msg)
            proxy.local = local
            controller.refresh_msgs()
            if proxy.is_downloaded:
                controller.model.downloads.pop(file_id)
            break


@update_handler("updateMessageContentOpened")
def update_message_content_opened(
    controller: Controller, update: Dict[str, Any]
):
    chat_id = update["chat_id"]
    message_id = update["message_id"]
    controller.model.msgs.update_msg_content_opened(chat_id, message_id)
    controller.refresh_msgs()
