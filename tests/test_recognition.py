import os
import unittest
from unittest.mock import patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")
os.environ.setdefault("RECOGNITION_EMOJI", "☕")
os.environ.setdefault("RECOGNITION_UNIT", "커피")

from services.recognition import (  # noqa: E402
    INVALID_FORMAT,
    LimitError,
    MULTIPLE_QUANTITY_METHODS,
    ParseError,
    RecognitionRequest,
    create_recognition,
    parse_thanks_text,
)
import services.recognition as recognition_service  # noqa: E402
from db.queries import _daily_limit_lock_key  # noqa: E402


class RecognitionParsingTest(unittest.TestCase):
    def test_counts_emoji_after_mention(self):
        request = parse_thanks_text("<@U1234> ☕☕ 감사합니다", "U9999")

        self.assertEqual(request.receiver_id, "U1234")
        self.assertEqual(request.unit_count, 2)
        self.assertEqual(request.message, "감사합니다")

    def test_counts_emoji_with_variation_selector_after_mention(self):
        request = parse_thanks_text("<@U1234> ☕️☕️ 감사합니다", "U9999")

        self.assertEqual(request.receiver_id, "U1234")
        self.assertEqual(request.unit_count, 2)
        self.assertEqual(request.message, "감사합니다")

    def test_counts_coffee_alias_after_mention(self):
        request = parse_thanks_text("<@U1234> :coffee::coffee: 감사합니다", "U9999")

        self.assertEqual(request.receiver_id, "U1234")
        self.assertEqual(request.unit_count, 2)
        self.assertEqual(request.message, "감사합니다")

    def test_counts_emoji_before_mention(self):
        request = parse_thanks_text("☕☕ <@U1234> 감사합니다", "U9999")

        self.assertEqual(request.receiver_id, "U1234")
        self.assertEqual(request.unit_count, 2)
        self.assertEqual(request.message, "감사합니다")

    def test_counts_coffee_alias_before_mention(self):
        request = parse_thanks_text(":coffee::coffee: <@U1234> 감사합니다", "U9999")

        self.assertEqual(request.receiver_id, "U1234")
        self.assertEqual(request.unit_count, 2)
        self.assertEqual(request.message, "감사합니다")

    def test_counts_emoji_with_variation_selector_before_mention(self):
        request = parse_thanks_text("☕️☕️ <@U1234> 감사합니다", "U9999")

        self.assertEqual(request.receiver_id, "U1234")
        self.assertEqual(request.unit_count, 2)
        self.assertEqual(request.message, "감사합니다")

    def test_defaults_to_one_without_quantity(self):
        request = parse_thanks_text("<@U1234> 감사합니다", "U9999")

        self.assertEqual(request.receiver_id, "U1234")
        self.assertEqual(request.unit_count, 1)
        self.assertEqual(request.message, "감사합니다")

    def test_counts_numeric_quantity_after_mention(self):
        request = parse_thanks_text("<@U1234> 2 감사합니다", "U9999")

        self.assertEqual(request.receiver_id, "U1234")
        self.assertEqual(request.unit_count, 2)
        self.assertEqual(request.message, "감사합니다")

    def test_rejects_numeric_quantity_before_mention(self):
        with self.assertRaises(ParseError) as ctx:
            parse_thanks_text("2 <@U1234> 감사합니다", "U9999")

        self.assertEqual(ctx.exception.reason, INVALID_FORMAT)

    def test_counts_three_joined_emoji_after_mention(self):
        request = parse_thanks_text("<@U1234> ☕☕☕ 감사합니다", "U9999")

        self.assertEqual(request.unit_count, 3)
        self.assertEqual(request.message, "감사합니다")

    def test_counts_three_joined_emoji_with_variation_selector_after_mention(self):
        request = parse_thanks_text("<@U1234> ☕️☕️☕️ 감사합니다", "U9999")

        self.assertEqual(request.unit_count, 3)
        self.assertEqual(request.message, "감사합니다")

    def test_counts_three_joined_coffee_alias_after_mention(self):
        request = parse_thanks_text("<@U1234> :coffee::coffee::coffee: 감사합니다", "U9999")

        self.assertEqual(request.unit_count, 3)
        self.assertEqual(request.message, "감사합니다")

    def test_parser_counts_quantity_above_daily_limit(self):
        request = parse_thanks_text("<@U1234> ☕☕☕☕☕☕ 감사합니다", "U9999")

        self.assertEqual(request.unit_count, 6)
        self.assertEqual(request.message, "감사합니다")

    def test_counts_only_joined_leading_emoji_as_quantity(self):
        request = parse_thanks_text("<@U1234> ☕ ☕ 감사합니다", "U9999")

        self.assertEqual(request.unit_count, 1)
        self.assertEqual(request.message, "☕ 감사합니다")

    def test_counts_only_joined_leading_coffee_alias_as_quantity(self):
        request = parse_thanks_text("<@U1234> :coffee: :coffee: 감사합니다", "U9999")

        self.assertEqual(request.unit_count, 1)
        self.assertEqual(request.message, ":coffee: 감사합니다")

    def test_keeps_emoji_after_numeric_quantity_in_message(self):
        request = parse_thanks_text("<@U1234> 2 ☕ 감사합니다", "U9999")

        self.assertEqual(request.unit_count, 2)
        self.assertEqual(request.message, "☕ 감사합니다")

    def test_rejects_emoji_and_numeric_quantity(self):
        with self.assertRaises(ParseError) as ctx:
            parse_thanks_text("<@U1234> ☕☕ 3 감사합니다", "U9999")

        self.assertEqual(ctx.exception.reason, MULTIPLE_QUANTITY_METHODS)


class RecognitionCreationTest(unittest.TestCase):
    def test_locks_daily_limit_before_checking_sent_today(self):
        call_order = []
        request = RecognitionRequest(
            receiver_id="U1234",
            unit_count=1,
            message="감사합니다",
        )

        def lock_daily_limit(conn, sender_id):
            call_order.append("lock")

        def get_sent_today(conn, sender_id):
            call_order.append("get_sent_today")
            return 0

        with patch.object(recognition_service, "lock_daily_limit", side_effect=lock_daily_limit), \
            patch.object(recognition_service, "get_sent_today", side_effect=get_sent_today), \
            patch.object(recognition_service, "insert_recognition", return_value=42), \
            patch.object(recognition_service, "get_total_received", return_value=1):
            create_recognition(
                conn=object(),
                sender_id="U9999",
                request=request,
                source_channel_id="C123",
            )

        self.assertEqual(call_order, ["lock", "get_sent_today"])

    def test_does_not_insert_when_daily_limit_is_exceeded(self):
        request = RecognitionRequest(
            receiver_id="U1234",
            unit_count=2,
            message="감사합니다",
        )

        with patch.object(recognition_service, "lock_daily_limit"), \
            patch.object(recognition_service, "get_sent_today", return_value=4), \
            patch.object(recognition_service, "insert_recognition") as insert_recognition:
            with self.assertRaises(LimitError) as ctx:
                create_recognition(
                    conn=object(),
                    sender_id="U9999",
                    request=request,
                    source_channel_id="C123",
                )

        self.assertEqual(ctx.exception.remaining, 1)
        self.assertEqual(ctx.exception.requested, 2)
        insert_recognition.assert_not_called()

    def test_returns_result_when_daily_limit_allows_insert(self):
        request = RecognitionRequest(
            receiver_id="U1234",
            unit_count=2,
            message="감사합니다",
        )

        with patch.object(recognition_service, "lock_daily_limit"), \
            patch.object(recognition_service, "get_sent_today", return_value=1), \
            patch.object(recognition_service, "insert_recognition", return_value=42) as insert_recognition, \
            patch.object(recognition_service, "get_total_received", return_value=7):
            result = create_recognition(
                conn=object(),
                sender_id="U9999",
                request=request,
                source_channel_id="C123",
            )

        insert_recognition.assert_called_once()
        self.assertEqual(result.recognition_id, 42)
        self.assertEqual(result.receiver_id, "U1234")
        self.assertEqual(result.unit_count, 2)
        self.assertEqual(result.message, "감사합니다")
        self.assertEqual(result.remaining, 2)
        self.assertEqual(result.total_received, 7)


class DailyLimitLockKeyTest(unittest.TestCase):
    def test_same_sender_and_date_returns_same_key(self):
        self.assertEqual(
            _daily_limit_lock_key("U1234", "2026-06-17"),
            _daily_limit_lock_key("U1234", "2026-06-17"),
        )

    def test_different_sender_returns_different_key(self):
        self.assertNotEqual(
            _daily_limit_lock_key("U1234", "2026-06-17"),
            _daily_limit_lock_key("U5678", "2026-06-17"),
        )

    def test_different_date_returns_different_key(self):
        self.assertNotEqual(
            _daily_limit_lock_key("U1234", "2026-06-17"),
            _daily_limit_lock_key("U1234", "2026-06-18"),
        )

    def test_key_is_signed_64_bit_integer(self):
        key = _daily_limit_lock_key("U1234", "2026-06-17")

        self.assertIsInstance(key, int)
        self.assertGreaterEqual(key, -(2**63))
        self.assertLessEqual(key, 2**63 - 1)


if __name__ == "__main__":
    unittest.main()
