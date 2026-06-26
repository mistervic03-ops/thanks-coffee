import os
import unittest
from types import SimpleNamespace


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("ANNOUNCEMENT_CHANNEL_ID", "C123")

from services.feed import build_feed_blocks, post_to_feed  # noqa: E402


class FakeClient:
    def __init__(self):
        self.messages = []

    def chat_postMessage(self, **kwargs):
        self.messages.append(kwargs)
        return {"ts": "123.456"}


class FeedPostTest(unittest.TestCase):
    def test_post_to_feed_uses_blocks_with_fallback_text(self):
        client = FakeClient()
        result = SimpleNamespace(
            recognition_id=42,
            receiver_id="U456",
            message="빠른 리뷰 고마워요",
            total_received=7,
        )

        ts = post_to_feed(client, "U123", result)

        self.assertEqual(ts, "123.456")
        self.assertEqual(client.messages[0]["channel"], "C123")
        self.assertEqual(
            client.messages[0]["text"],
            "☕ <@U123>님이 <@U456>님께 감사 커피를 전했어요.",
        )
        self.assertEqual(
            client.messages[0]["blocks"],
            build_feed_blocks("U123", "U456", "빠른 리뷰 고마워요", 7, 42),
        )


class FeedBlockBuilderTest(unittest.TestCase):
    def test_build_feed_blocks_keeps_existing_message_copy(self):
        blocks = build_feed_blocks("U123", "U456", "고마워요", 1, 42)

        self.assertEqual(blocks[0]["type"], "section")
        self.assertEqual(
            blocks[0]["text"]["text"],
            "☕ *<@U123>님이 <@U456>님께 감사 커피를 전했어요.*",
        )
        self.assertEqual(blocks[1]["text"]["text"], "> \"고마워요\"")
        self.assertEqual(
            blocks[2]["elements"][0]["text"],
            "<@U456>님이 지금까지 받은 커피: 한 잔  ·  #42",
        )


if __name__ == "__main__":
    unittest.main()
