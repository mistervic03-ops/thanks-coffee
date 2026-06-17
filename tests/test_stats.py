import os
import unittest
from datetime import date
from unittest.mock import Mock, patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

from services.stats import get_current_week_range, get_previous_week_range  # noqa: E402
import handlers.stats as summary_handler  # noqa: E402


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


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class WeeklyRangeTest(unittest.TestCase):
    def test_previous_week_range_for_monday_automation(self):
        start_date, end_date = get_previous_week_range(date(2026, 6, 1))

        self.assertEqual(start_date, date(2026, 5, 25))
        self.assertEqual(end_date, date(2026, 5, 31))

    def test_current_week_range_returns_this_week(self):
        start_date, end_date = get_current_week_range(date(2026, 6, 5))

        self.assertEqual(start_date, date(2026, 6, 1))
        self.assertEqual(end_date, date(2026, 6, 5))

    def test_current_week_range_on_monday(self):
        start_date, end_date = get_current_week_range(date(2026, 6, 1))

        self.assertEqual(start_date, date(2026, 6, 1))
        self.assertEqual(end_date, date(2026, 6, 1))


class SummaryCommandTest(unittest.TestCase):
    def test_summary_admin_helper_uses_allowlist(self):
        with patch.object(summary_handler, "ADMIN_USER_IDS", frozenset({"UADMIN"})):
            self.assertTrue(summary_handler.is_summary_admin("UADMIN"))
            self.assertFalse(summary_handler.is_summary_admin("UOTHER"))

    def test_summary_rejects_unauthorized_user(self):
        app = FakeApp()
        client = FakeClient()
        ack = Mock()
        body = {"user_id": "UOTHER", "channel_id": "C123", "text": "weekly"}

        summary_handler.register(app)
        with patch.object(summary_handler, "ADMIN_USER_IDS", frozenset({"UADMIN"})), \
            patch.object(summary_handler, "_build_summary_text") as build_summary_text, \
            patch.object(summary_handler, "post_summary") as post_summary:
            app.commands["/summary"](ack, body, client)

        ack.assert_called_once()
        build_summary_text.assert_not_called()
        post_summary.assert_not_called()
        self.assertEqual(len(client.ephemeral_messages), 1)
        self.assertEqual(client.ephemeral_messages[0]["user"], "UOTHER")
        self.assertIn("권한", client.ephemeral_messages[0]["text"])

    def test_summary_preview_rejects_unauthorized_user(self):
        app = FakeApp()
        client = FakeClient()
        ack = Mock()
        body = {"user_id": "UOTHER", "channel_id": "C123", "text": "weekly preview"}

        summary_handler.register(app)
        with patch.object(summary_handler, "ADMIN_USER_IDS", frozenset({"UADMIN"})), \
            patch.object(summary_handler, "_build_summary_text") as build_summary_text, \
            patch.object(summary_handler, "post_summary") as post_summary:
            app.commands["/summary"](ack, body, client)

        ack.assert_called_once()
        build_summary_text.assert_not_called()
        post_summary.assert_not_called()
        self.assertEqual(len(client.ephemeral_messages), 1)
        self.assertIn("권한", client.ephemeral_messages[0]["text"])

    def test_summary_weekly_preview_sends_ephemeral_without_posting_feed(self):
        app = FakeApp()
        client = FakeClient()
        ack = Mock()
        body = {"user_id": "UADMIN", "channel_id": "C123", "text": "weekly preview"}

        summary_handler.register(app)
        with patch.object(summary_handler, "ADMIN_USER_IDS", frozenset({"UADMIN"})), \
            patch.object(summary_handler, "_build_summary_text", return_value="weekly summary") as build_summary_text, \
            patch.object(summary_handler, "post_summary") as post_summary:
            app.commands["/summary"](ack, body, client)

        ack.assert_called_once()
        build_summary_text.assert_called_once_with("weekly")
        post_summary.assert_not_called()
        self.assertEqual(len(client.ephemeral_messages), 1)
        self.assertEqual(client.ephemeral_messages[0]["user"], "UADMIN")
        self.assertEqual(client.ephemeral_messages[0]["text"], "weekly summary")

    def test_manual_weekly_summary_uses_previous_week_range(self):
        conn = FakeConnection()
        stats = {"start_date": date(2026, 5, 25), "end_date": date(2026, 5, 31)}

        with patch.object(summary_handler, "get_connection", return_value=conn), \
            patch.object(
                summary_handler,
                "get_previous_week_range",
                return_value=(date(2026, 5, 25), date(2026, 5, 31)),
            ) as get_previous_week_range_mock, \
            patch.object(summary_handler, "load_weekly_stats", return_value=stats) as load_weekly_stats, \
            patch.object(summary_handler, "build_weekly_summary", return_value="weekly summary"):
            summary_text = summary_handler._build_summary_text("weekly")

        self.assertEqual(summary_text, "weekly summary")
        get_previous_week_range_mock.assert_called_once_with()
        load_weekly_stats.assert_called_once_with(
            conn,
            date(2026, 5, 25),
            date(2026, 5, 31),
        )
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()
