import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class Model:

    def __init__(self, tg):
        self.chats = ChatModel(tg)
        self.msgs = MsgModel(tg)
        self.users = UserModel(tg)
        self.current_chat = 0

    def get_me(self):
        return self.users.get_me()

    def get_user(self, user_id):
        return self.users.get_user(user_id)

    def get_current_chat_id(self):
        return self.chats.chat_ids[self.current_chat]

    def get_current_msg(self):
        return self.msgs.current_msgs[self.get_current_chat_id()]

    def jump_bottom(self):
        chat_id = self.chats.chat_ids[self.current_chat]
        return self.msgs.jump_bottom(chat_id)

    def next_chat(self):
        if self.current_chat < len(self.chats.chats):
            self.current_chat += 1
            return True
        return False

    def prev_chat(self):
        if self.current_chat > 0:
            self.current_chat -= 1
            return True
        return False

    def next_msg(self):
        chat_id = self.chats.chat_ids[self.current_chat]
        return self.msgs.next_msg(chat_id)

    def prev_msg(self):
        chat_id = self.chats.chat_ids[self.current_chat]
        return self.msgs.prev_msg(chat_id)

    def jump_next_msg(self):
        chat_id = self.chats.chat_ids[self.current_chat]
        return self.msgs.jump_next_msg(chat_id)

    def jump_prev_msg(self):
        chat_id = self.chats.chat_ids[self.current_chat]
        return self.msgs.jump_prev_msg(chat_id)

    def get_chats(self, offset=0, limit=10):
        return self.chats.get_chats(offset=offset, limit=limit)

    def get_current_msgs(self, offset=0, limit=10):
        chat_id = self.chats.chat_ids[self.current_chat]
        return self.msgs.get_msgs(
            chat_id, offset=offset, limit=limit
        )

    def send_msg(self, chat_id, msg):
        result = self.users.tg.send_message(
            chat_id=chat_id,
            text=msg,
        )

        result.wait()
        if result.error:
            logger.info(f'send message error: {result.error_info}')
        else:
            logger.info(f'message has been sent: {result.update}')


class ChatModel:

    def __init__(self, tg):
        self.tg = tg
        self.chats = []  # Dict[int, list]
        self.chat_ids = []

    def get_chats(self, offset=0, limit=10):
        if offset + limit < len(self.chats):
            # return data from cache
            return self.chats[offset:limit]

        self.get_chat_ids(
            offset=len(self.chats),
            limit=len(self.chats) + limit
        )
        for i in range(3):
            for chat_id in self.chat_ids:
                chat = self.get_chat(chat_id)
                self.chats.append(chat)
                logger.debug(
                    '#### %s: %s, %s', chat_id, chat, i)
            if len(self.chats) >= offset + limit:
                break

        return self.chats[offset:limit]

    def get_chat_ids(self, offset=0, limit=10):
        for i in range(3):
            if len(self.chats):
                result = self.tg.get_chats(
                    offset_chat_id=self.chats[-1]['id'],
                    limit=limit
                )
            else:
                result = self.tg.get_chats(
                    offset_order=2 ** 63 - 1,
                    offset_chat_id=offset,
                    limit=limit
                )

            result.wait()
            if result.error:
                logger.error(f'get chat ids error: {result.error_info}')
                return {}

            for chat_id in result.update['chat_ids']:
                self.chat_ids.append(chat_id)

            if len(self.chat_ids) >= offset + limit:
                break

        return self.chat_ids[offset:limit]

    def get_chat(self, chat_id):
        result = self.tg.get_chat(chat_id)
        result.wait()

        if result.error:
            logger.error(f'get chat error: {result.error_info}')
            return {}
        return result.update


class MsgModel:

    def __init__(self, tg):
        self.tg = tg
        self.msgs = defaultdict(list)  # Dict[int, list]
        self.current_msgs = defaultdict(int)

    def next_msg(self, chat_id):
        if self.current_msgs[chat_id] > 0:
            self.current_msgs[chat_id] -= 1
            return True
        return False

    def jump_bottom(self, chat_id):
        if self.current_msgs[chat_id] == 0:
            return False
        self.current_msgs[chat_id] = 0
        return True

    def jump_next_msg(self, chat_id):
        if self.current_msgs[chat_id] - 10 > 0:
            self.current_msgs[chat_id] -= 10
        else:
            self.current_msgs[chat_id] = 0
        return True

    def jump_prev_msg(self, chat_id):
        if self.current_msgs[chat_id] + 10 < len(self.msgs[chat_id]):
            self.current_msgs[chat_id] += 10
            return True
        return False

    def prev_msg(self, chat_id):
        if self.current_msgs[chat_id] < len(self.msgs[chat_id]):
            self.current_msgs[chat_id] += 1
            return True
        return False

    def get_msgs(self, chat_id, offset=0, limit=10):
        if offset + limit < len(self.msgs[chat_id]):
            return sorted(self.msgs[chat_id], key=lambda d: d['id'])[::-1][offset:limit]

        for i in range(3):
            if len(self.msgs[chat_id]):
                result = self.tg.get_chat_history(
                    chat_id,
                    from_message_id=self.msgs[chat_id][-1]['id'],
                    limit=len(self.msgs[chat_id]) + limit
                )
            else:
                result = self.tg.get_chat_history(
                    chat_id,
                    offset=len(self.msgs[chat_id]),
                    limit=len(self.msgs[chat_id]) + limit
                )

            result.wait()
            for msg in result.update['messages']:
                self.msgs[chat_id].append(msg)
            if len(self.msgs[chat_id]) >= offset + limit:
                break

        return sorted(self.msgs[chat_id], key=lambda d: d['id'])[::-1][offset:limit]


class UserModel:

    def __init__(self, tg):
        self.tg = tg
        self.me = None
        self.users = {}

    def get_me(self):
        if self.me:
            return self.me
        result = self.tg.get_me()
        result.wait()
        if result.error:
            logger.error(f'get chat ids error: {result.error_info}')
            return {}
        self.me = result.update
        return self.me

    def get_user(self, user_id):
        if user_id in self.users:
            return self.users[user_id]
        result = self.tg.call_method('getUser', {'user_id': user_id})
        result.wait()
        if result.error:
            logger.error(f'get chat ids error: {result.error_info}')
            return {}
        self.users[user_id] = result.update
        return result.update
