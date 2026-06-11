"""Unit tests for ChatMessage and ChatContext."""

import unittest
from services.chat_engine import ChatMessage, ChatContext


class TestChatMessage(unittest.TestCase):
    """Tests for ChatMessage.formatted_content."""

    def test_user_with_timestamp(self):
        msg = ChatMessage(
            role="user", content="hello", name="Alice", timestamp="14:30"
        )
        self.assertEqual(msg.formatted_content, "[14:30] Alice: hello")

    def test_user_without_timestamp(self):
        msg = ChatMessage(role="user", content="hi", name="Bob")
        self.assertEqual(msg.formatted_content, "Bob: hi")

    def test_assistant_no_prefix(self):
        msg = ChatMessage(role="assistant", content="Sure thing!")
        self.assertEqual(msg.formatted_content, "Sure thing!")


class TestChatContext(unittest.TestCase):
    """Tests for ChatContext add, extend, and serialization."""

    def setUp(self):
        self.ctx = ChatContext()

    def test_empty_initial_state(self):
        self.assertEqual(len(self.ctx), 0)

    def test_add_and_len(self):
        self.ctx.add(ChatMessage(role="user", content="hi"))
        self.assertEqual(len(self.ctx), 1)

    def test_extend(self):
        msgs = [
            ChatMessage(role="user", content="a"),
            ChatMessage(role="assistant", content="b"),
        ]
        self.ctx.extend(msgs)
        self.assertEqual(len(self.ctx), 2)

    def test_to_api_format(self):
        self.ctx.add(
            ChatMessage(role="user", content="hello", name="Alice")
        )
        self.ctx.add(
            ChatMessage(role="assistant", content="Hi Alice!")
        )
        result = self.ctx.to_api_format()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], {"role": "user", "content": "Alice: hello"})
        self.assertEqual(result[1], {"role": "assistant", "content": "Hi Alice!"})

    def test_clear(self):
        self.ctx.add(ChatMessage(role="user", content="x"))
        self.ctx.clear()
        self.assertEqual(len(self.ctx), 0)

    def test_reverse(self):
        self.ctx.add(ChatMessage(role="user", content="first"))
        self.ctx.add(ChatMessage(role="user", content="second"))
        self.ctx.reverse()
        msgs = list(self.ctx)
        self.assertEqual(msgs[0].content, "second")
        self.assertEqual(msgs[1].content, "first")

    def test_iter(self):
        m1 = ChatMessage(role="user", content="a")
        m2 = ChatMessage(role="assistant", content="b")
        self.ctx.add(m1)
        self.ctx.add(m2)
        items = list(self.ctx)
        self.assertIs(items[0], m1)
        self.assertIs(items[1], m2)


if __name__ == "__main__":
    unittest.main()
