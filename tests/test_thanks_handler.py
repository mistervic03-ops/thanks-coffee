import os
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, call, patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("ANNOUNCEMENT_CHANNEL_ID", "C123")

import handlers.thanks as thanks_handler  # noqa: E402
import handlers.home as home_handler  # noqa: E402
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
    def __init__(self, users=None, users_info_error=None):
        self.ephemeral_messages = []
        self.events = []
        self.users = users or {}
        self.users_info_calls = []
        self.users_info_error = users_info_error

    def chat_postEphemeral(self, **kwargs):
        self.ephemeral_messages.append(kwargs)
        self.events.append(("ephemeral", kwargs["text"]))

    def users_info(self, user):
        self.users_info_calls.append(user)
        if self.users_info_error:
            raise self.users_info_error

        return {"user": self.users[user]}


class FakeConnection:
    def __init__(self):
        self.closed = False
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

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


class ThanksReceiverStatusTest(unittest.TestCase):
    def run_thanks(self, client, refresh_home_side_effect=None, patch_refresh_home=True):
        app = FakeApp()
        ack = Mock()
        conn = FakeConnection()
        body = {
            "user_id": "U123",
            "channel_id": "C123",
            "text": "<@U456> 감사합니다",
            "trigger_id": "trigger-1",
        }
        result = SimpleNamespace(
            recognition_id=1,
            receiver_id="U456",
            unit_count=1,
            message="감사합니다",
            remaining=4,
            total_received=10,
            is_duplicate=True,
        )

        thanks_handler.register(app)
        with ExitStack() as stack:
            get_connection = stack.enter_context(
                patch.object(thanks_handler, "get_connection", return_value=conn)
            )
            create_recognition = stack.enter_context(
                patch.object(thanks_handler, "create_recognition", return_value=result)
            )
            release_connection = stack.enter_context(
                patch.object(thanks_handler, "release_connection")
            )
            refresh_home = None
            if patch_refresh_home:
                refresh_home = stack.enter_context(
                    patch("handlers.home.refresh_home", side_effect=refresh_home_side_effect)
                )

            app.commands["/thanks"](ack, body, client)

        return ack, get_connection, create_recognition, release_connection, refresh_home, body

    def test_blocks_deactivated_receiver_before_creating_recognition(self):
        client = FakeClient(users={"U456": {"deleted": True}})

        ack, get_connection, create_recognition, release_connection, refresh_home, _ = self.run_thanks(client)

        ack.assert_called_once()
        get_connection.assert_not_called()
        create_recognition.assert_not_called()
        release_connection.assert_not_called()
        refresh_home.assert_not_called()
        self.assertEqual(client.users_info_calls, ["U456"])
        self.assertEqual(len(client.ephemeral_messages), 1)
        self.assertIn("비활성화된 사용자에게는 감사를 보낼 수 없어요.", client.ephemeral_messages[0]["text"])

    def test_allows_recognition_when_receiver_status_check_fails(self):
        client = FakeClient(users_info_error=Exception("slack unavailable"))

        with self.assertLogs(thanks_handler.logger, level="WARNING") as logs:
            ack, get_connection, create_recognition, release_connection, _, body = self.run_thanks(client)

        ack.assert_called_once()
        get_connection.assert_called_once()
        create_recognition.assert_called_once()
        release_connection.assert_called_once()
        self.assertEqual(client.users_info_calls, ["U456"])
        self.assertEqual(logs.records[0].event, "receiver_status_check_failed")
        self.assertEqual(logs.records[0].detail, "U456")
        self.assertIn("모카가 <@U456>님께", client.ephemeral_messages[0]["text"])
        self.assertEqual(create_recognition.call_args.kwargs["source_channel_id"], body["channel_id"])

    def test_bot_and_active_checks_share_one_users_info_call(self):
        client = FakeClient(users={"U456": {"is_bot": False, "deleted": False}})

        ack, get_connection, create_recognition, release_connection, _, _ = self.run_thanks(client)

        ack.assert_called_once()
        get_connection.assert_called_once()
        create_recognition.assert_called_once()
        release_connection.assert_called_once()
        self.assertEqual(client.users_info_calls, ["U456"])
        self.assertIn("모카가 <@U456>님께", client.ephemeral_messages[0]["text"])

    def test_refreshes_sender_and_receiver_home_after_recognition_response(self):
        client = FakeClient(users={"U456": {"is_bot": False, "deleted": False}})

        def refresh_home(client_arg, user_id):
            client_arg.events.append(("refresh_home", user_id))

        ack, _, _, _, refresh_home_mock, _ = self.run_thanks(
            client,
            refresh_home_side_effect=refresh_home,
        )

        ack.assert_called_once()
        refresh_home_mock.assert_has_calls([call(client, "U123"), call(client, "U456")])
        self.assertEqual(
            client.events,
            [
                ("ephemeral", client.ephemeral_messages[0]["text"]),
                ("refresh_home", "U123"),
                ("refresh_home", "U456"),
            ],
        )

    def test_home_refresh_failure_does_not_affect_recognition_response(self):
        client = FakeClient(users={"U456": {"is_bot": False, "deleted": False}})

        with patch.object(
            home_handler,
            "build_home_view_for_user",
            side_effect=Exception("home unavailable"),
        ), self.assertLogs(home_handler.logger, level="WARNING") as logs:
            ack, get_connection, create_recognition, release_connection, _, _ = self.run_thanks(
                client,
                patch_refresh_home=False,
            )

        ack.assert_called_once()
        get_connection.assert_called_once()
        create_recognition.assert_called_once()
        release_connection.assert_called_once()
        self.assertIn("모카가 <@U456>님께", client.ephemeral_messages[0]["text"])
        self.assertEqual([record.event for record in logs.records], ["home_refresh_failed", "home_refresh_failed"])
        self.assertEqual([record.detail for record in logs.records], ["U123", "U456"])


class ThanksDailyLimitTest(unittest.TestCase):
    def run_thanks_with_limit_error(self, remaining, requested):
        app = FakeApp()
        client = FakeClient(users={"U456": {"is_bot": False, "deleted": False}})
        ack = Mock()
        conn = FakeConnection()
        body = {
            "user_id": "U123",
            "channel_id": "C123",
            "text": "<@U456> 감사합니다",
            "trigger_id": "trigger-1",
        }

        thanks_handler.register(app)
        with patch.object(thanks_handler, "get_connection", return_value=conn), \
            patch.object(
                thanks_handler,
                "create_recognition",
                side_effect=thanks_handler.LimitError(remaining=remaining, requested=requested),
            ) as create_recognition, \
            patch.object(thanks_handler, "release_connection") as release_connection:
            app.commands["/thanks"](ack, body, client)

        ack.assert_called_once()
        create_recognition.assert_called_once()
        release_connection.assert_called_once_with(conn)
        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.rollbacks, 1)
        self.assertEqual(len(client.ephemeral_messages), 1)
        return client.ephemeral_messages[0]["text"]

    def test_limit_error_uses_all_used_message_when_remaining_is_zero(self):
        text = self.run_thanks_with_limit_error(remaining=0, requested=1)

        self.assertEqual(text, "❌ 오늘의 감사 한도를 모두 사용했어요. (요청: 커피 한 잔)")

    def test_limit_error_keeps_existing_message_when_remaining_is_positive(self):
        text = self.run_thanks_with_limit_error(remaining=2, requested=3)

        self.assertEqual(text, "❌ 오늘은 커피 2잔만 더 보낼 수 있어요. (요청: 커피 3잔)")


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
