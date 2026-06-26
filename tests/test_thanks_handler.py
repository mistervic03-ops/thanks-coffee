import os
import unittest
from datetime import datetime, timezone
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
    def __init__(self, users=None):
        self.ephemeral_messages = []
        self.users = users or {}

    def chat_postEphemeral(self, **kwargs):
        self.ephemeral_messages.append(kwargs)

    def users_info(self, user):
        return {"user": self.users[user]}


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


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

        self.assertIn("/thanks @user 빠르게 도와줘서 고마워요", text)
        self.assertIn("/thanks @user 3 큰 도움을 줘서 고마워요", text)
        self.assertIn("/thanks ☕☕☕ @user 정말 고마워요", text)
        self.assertIn("App Home", text)
        self.assertIn("받은 감사", text)
        self.assertIn("오늘 남은 수량", text)
        self.assertNotIn("/thanks status", text)
        self.assertNotIn("/thanks received", text)
        self.assertIn("나에게만", text)

    def test_thanks_help_shows_help(self):
        text = self.run_thanks("help")

        self.assertIn("/thanks @user 빠르게 도와줘서 고마워요", text)
        self.assertIn("/thanks @user 3 큰 도움을 줘서 고마워요", text)
        self.assertIn("App Home", text)
        self.assertNotIn("/thanks status", text)
        self.assertNotIn("/thanks received", text)
        self.assertIn("나에게만", text)

    def test_unknown_thanks_usage_shows_help(self):
        text = self.run_thanks("not a valid command")

        self.assertIn("형식을 다시 확인해주세요", text)
        self.assertIn("/thanks @user 빠르게 도와줘서 고마워요", text)
        self.assertNotIn("/thanks status", text)
        self.assertNotIn("/thanks received", text)
        self.assertNotIn("invalid_format", text)


class ThanksReceivedCommandTest(unittest.TestCase):
    def run_thanks_received(self, recognitions, users=None):
        app = FakeApp()
        client = FakeClient(users=users)
        ack = Mock()
        conn = FakeConnection()
        body = {
            "user_id": "U123",
            "channel_id": "C123",
            "text": "received",
            "trigger_id": "trigger-1",
        }

        thanks_handler.register(app)
        with patch.object(thanks_handler, "get_connection", return_value=conn) as get_connection, \
            patch.object(
                thanks_handler,
                "get_recent_received_recognitions",
                return_value=recognitions,
            ) as get_recent_received_recognitions, \
            patch.object(thanks_handler, "create_recognition") as create_recognition, \
            patch.object(thanks_handler, "release_connection") as release_connection:
            app.commands["/thanks"](ack, body, client)

        ack.assert_called_once()
        get_connection.assert_called_once()
        get_recent_received_recognitions.assert_called_once_with(conn, "U123", 10)
        create_recognition.assert_not_called()
        release_connection.assert_called_once_with(conn)
        self.assertEqual(len(client.ephemeral_messages), 1)
        self.assertEqual(client.ephemeral_messages[0]["user"], "U123")
        return client.ephemeral_messages[0]["text"]

    def test_thanks_received_shows_recent_received_recognitions(self):
        text = self.run_thanks_received(
            [
                {
                    "sender_id": "U456",
                    "message": "도와줘서 고마워요",
                    "unit_count": 2,
                    "created_at": datetime(2026, 6, 21, 15, 30, tzinfo=timezone.utc),
                },
                {
                    "sender_id": "U789",
                    "message": "빠른 리뷰 감사합니다",
                    "unit_count": 1,
                    "created_at": datetime(2026, 6, 20, 1, 0, tzinfo=timezone.utc),
                },
            ],
            users={
                "U456": {"profile": {"display_name": "민준"}},
                "U789": {"profile": {"display_name": "", "real_name": "서연"}},
            },
        )

        self.assertIn("최근 받은 감사 2건", text)
        self.assertIn("2026-06-22 · 민준 · 커피 2잔", text)
        self.assertIn("\"도와줘서 고마워요\"", text)
        self.assertIn("2026-06-20 · 서연 · 커피 한 잔", text)
        self.assertIn("\"빠른 리뷰 감사합니다\"", text)

    def test_thanks_received_empty_state_is_warm(self):
        text = self.run_thanks_received([])

        self.assertIn("아직 받은 감사 커피가 없어요", text)
        self.assertIn("따뜻한 마음", text)


if __name__ == "__main__":
    unittest.main()
