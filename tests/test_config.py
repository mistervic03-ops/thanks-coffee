import os
import unittest


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

from config import parse_admin_user_ids, parse_enabled_flag, validate_feed_config  # noqa: E402


class ConfigTest(unittest.TestCase):
    def test_parses_admin_user_ids(self):
        self.assertEqual(
            parse_admin_user_ids("U123, U456,,"),
            frozenset({"U123", "U456"}),
        )

    def test_feed_disabled_allows_missing_channel(self):
        validate_feed_config(False, "")

    def test_feed_enabled_requires_channel(self):
        with self.assertRaisesRegex(RuntimeError, "FEED_CHANNEL_ID"):
            validate_feed_config(True, "")

    def test_enabled_flag_only_accepts_true(self):
        self.assertTrue(parse_enabled_flag("true"))
        self.assertFalse(parse_enabled_flag("false"))
        self.assertFalse(parse_enabled_flag(""))


if __name__ == "__main__":
    unittest.main()
