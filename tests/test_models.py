import unittest

from tg.models import ChatModel


class Result:
    def __init__(self, update):
        self.update = update
        self.error = False
        self.error_info = None

    def wait(self):
        return self


class Telegram:
    def __init__(self):
        self.limits = []

    def get_chats(self, limit=100):
        self.limits.append(limit)
        return Result({"chat_ids": [1, 2]})

    def get_chat(self, chat_id):
        return Result(
            {
                "id": chat_id,
                "positions": [{"order": str(100 - chat_id)}],
            }
        )


class ChatModelTest(unittest.TestCase):
    def test_loads_new_chats_with_growing_limit(self):
        telegram = Telegram()
        model = ChatModel(telegram)

        model._load_next_chats()
        model._load_next_chats()

        self.assertEqual([chat["id"] for chat in model.chats], [1, 2])
        self.assertEqual(telegram.limits, [100, 102])
        self.assertTrue(model.have_full_chat_list)


if __name__ == "__main__":
    unittest.main()
