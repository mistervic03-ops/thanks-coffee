import os
import unittest


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("ANNOUNCEMENT_CHANNEL_ID", "C123")

from config import (  # noqa: E402
    ANTHROPIC_MODEL,
    HEALTH_CHECK_PORT,
    REMINDER_ENABLED,
    parse_admin_user_ids,
    parse_enabled_flag,
    validate_feed_config,
    validate_reminder_config,
)


class ConfigTest(unittest.TestCase):
    def test_parses_admin_user_ids(self):
        self.assertEqual(
            parse_admin_user_ids("U123, U456,,"),
            frozenset({"U123", "U456"}),
        )

    def test_feed_disabled_allows_missing_channel(self):
        validate_feed_config(False, "")

    def test_feed_enabled_requires_channel(self):
        with self.assertRaisesRegex(RuntimeError, "ANNOUNCEMENT_CHANNEL_ID"):
            validate_feed_config(True, "")

    def test_enabled_flag_only_accepts_true(self):
        self.assertTrue(parse_enabled_flag("true"))
        self.assertFalse(parse_enabled_flag("false"))
        self.assertFalse(parse_enabled_flag(""))

    def test_health_check_port_defaults_to_8000(self):
        self.assertEqual(HEALTH_CHECK_PORT, 8000)

    def test_reminder_enabled_defaults_to_false(self):
        self.assertFalse(REMINDER_ENABLED)

    def test_anthropic_model_defaults_to_latest_haiku(self):
        self.assertEqual(ANTHROPIC_MODEL, "claude-haiku-4-5-20251001")

    def test_reminder_disabled_allows_missing_anthropic_config(self):
        validate_reminder_config(False, "", "")

    def test_reminder_enabled_requires_announcement_channel(self):
        with self.assertRaisesRegex(RuntimeError, "ANNOUNCEMENT_CHANNEL_ID"):
            validate_reminder_config(True, "", "sk-ant-test")

    def test_reminder_enabled_requires_anthropic_api_key(self):
        with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY"):
            validate_reminder_config(True, "C123", "")


if __name__ == "__main__":
    unittest.main()
