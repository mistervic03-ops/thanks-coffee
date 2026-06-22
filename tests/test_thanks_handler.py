import os
import unittest
from unittest.mock import Mock, patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

import handlers.thanks as thanks_handler  # noqa: E402
from handlers.thanks import extract_idempotency_key  # noqa: E402


class FakeApp:
    def __init__(self):
        self.commands = {}

    def command(self, name):
        def decorator(handler):
            self.commands[name] = handler
            return handler

        return decorator


class FakeClient:
    def __init__(self):
        self.ephemeral_messages = []

    def chat_postEphemeral(self, **kwargs):
        self.ephemeral_messages.append(kwargs)


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


class ThanksCommandHelpTest(unittest.TestCase):
    def run_thanks(self, text):
        app = FakeApp()
        client = FakeClient()
        ack = Mock()
        body = {
            "user_id": "U123",
            "channel_id": "C123",
            "text": text,
            "trigger_id": "trigger-1",
        }

        thanks_handler.register(app)
        with patch.object(thanks_handler, "get_connection") as get_connection:
            app.commands["/thanks"](ack, body, client)

        ack.assert_called_once()
        get_connection.assert_not_called()
        self.assertEqual(len(client.ephemeral_messages), 1)
        return client.ephemeral_messages[0]["text"]

    def test_thanks_without_arguments_shows_help(self):
        text = self.run_thanks("")

        self.assertIn("/thanks @user message", text)
        self.assertIn("/thanks @user 3 message", text)
        self.assertIn("/thanks ☕☕☕ @user message", text)
        self.assertIn("/thanks status", text)
        self.assertIn("하루", text)
        self.assertIn("나에게만", text)

    def test_thanks_help_shows_help(self):
        text = self.run_thanks("help")

        self.assertIn("/thanks @user message", text)
        self.assertIn("나에게만", text)

    def test_unknown_thanks_usage_shows_help(self):
        text = self.run_thanks("not a valid command")

        self.assertIn("형식을 다시 확인해주세요", text)
        self.assertIn("/thanks @user message", text)
        self.assertNotIn("invalid_format", text)


if __name__ == "__main__":
    unittest.main()
