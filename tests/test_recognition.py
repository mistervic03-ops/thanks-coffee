import os
import unittest


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")
os.environ.setdefault("RECOGNITION_EMOJI", "☕")
os.environ.setdefault("RECOGNITION_UNIT", "커피")

from services.recognition import (  # noqa: E402
    MULTIPLE_QUANTITY_METHODS,
    ParseError,
    parse_thanks_text,
)


class RecognitionParsingTest(unittest.TestCase):
    def test_counts_emoji_after_mention(self):
        request = parse_thanks_text("<@U1234> ☕☕ 감사합니다", "U9999")

        self.assertEqual(request.receiver_id, "U1234")
        self.assertEqual(request.unit_count, 2)
        self.assertEqual(request.message, "감사합니다")

    def test_counts_emoji_before_mention(self):
        request = parse_thanks_text("☕☕ <@U1234> 감사합니다", "U9999")

        self.assertEqual(request.receiver_id, "U1234")
        self.assertEqual(request.unit_count, 2)
        self.assertEqual(request.message, "감사합니다")

    def test_rejects_emoji_and_numeric_quantity(self):
        with self.assertRaises(ParseError) as ctx:
            parse_thanks_text("<@U1234> ☕☕ 3 감사합니다", "U9999")

        self.assertEqual(ctx.exception.reason, MULTIPLE_QUANTITY_METHODS)


if __name__ == "__main__":
    unittest.main()
