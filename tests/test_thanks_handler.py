import os
import unittest


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

from handlers.thanks import extract_idempotency_key  # noqa: E402


class IdempotencyKeyExtractionTest(unittest.TestCase):
    def test_prefers_socket_envelope_id_from_context(self):
        key = extract_idempotency_key(
            {"trigger_id": "trigger-1"},
            {"envelope_id": "envelope-1"},
        )

        self.assertEqual(key, "/thanks:socket_envelope:envelope-1")

    def test_uses_trigger_id_when_request_metadata_is_absent(self):
        key = extract_idempotency_key({"trigger_id": "trigger-1"})

        self.assertEqual(key, "/thanks:trigger:trigger-1")

    def test_uses_response_url_when_trigger_id_is_absent(self):
        key = extract_idempotency_key({"response_url": "https://hooks.slack.com/commands/1"})

        self.assertEqual(
            key,
            "/thanks:response_url:https://hooks.slack.com/commands/1",
        )

    def test_returns_none_without_stable_slack_metadata(self):
        key = extract_idempotency_key(
            {
                "team_id": "T123",
                "channel_id": "C123",
                "user_id": "U123",
                "command": "/thanks",
                "text": "<@U456> 감사합니다",
            }
        )

        self.assertIsNone(key)


if __name__ == "__main__":
    unittest.main()
