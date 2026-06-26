import os
import unittest
from datetime import date
from unittest.mock import Mock, patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

import handlers.mocha as mocha_handler  # noqa: E402
import app as app_module  # noqa: E402


class FakeApp:
    def __init__(self):
        self.commands = {}
        self.events = {}

    def command(self, name):
        def decorator(handler):
            self.commands[name] = handler
            return handler

        return decorator

    def event(self, name):
        def decorator(handler):
            self.events[name] = handler
            return handler

        return decorator


class FakeClient:
    def __init__(self, delete_error=None):
        self.ephemeral_messages = []
        self.deleted_messages = []
        self.delete_error = delete_error

    def chat_postEphemeral(self, **kwargs):
        self.ephemeral_messages.append(kwargs)

    def chat_delete(self, **kwargs):
        if self.delete_error:
            raise self.delete_error

        self.deleted_messages.append(kwargs)


class FakeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class MochaCommandTest(unittest.TestCase):
    def run_mocha(
        self,
        text,
        *,
        is_admin=True,
        recognition=None,
        delete_error=None,
    ):
        app = FakeApp()
        client = FakeClient(delete_error=delete_error)
        ack = Mock()
        conn = FakeConnection()
        body = {
            "user_id": "UADMIN" if is_admin else "UOTHER",
            "channel_id": "C123",
            "text": text,
        }

        mocha_handler.register(app)
        with patch.object(mocha_handler, "is_admin", return_value=is_admin), \
            patch.object(mocha_handler, "get_connection", return_value=conn) as get_connection, \
            patch.object(
                mocha_handler,
                "get_recognition_by_id",
                return_value=recognition,
            ) as get_recognition_by_id, \
            patch.object(mocha_handler, "delete_recognition") as delete_recognition, \
            patch.object(mocha_handler, "release_connection") as release_connection, \
            patch.object(mocha_handler.logger, "info") as info_log, \
            patch.object(mocha_handler.logger, "warning") as warning_log:
            app.commands["/mocha"](ack, body, client)

        return {
            "ack": ack,
            "client": client,
            "conn": conn,
            "get_connection": get_connection,
            "get_recognition_by_id": get_recognition_by_id,
            "delete_recognition": delete_recognition,
            "release_connection": release_connection,
            "info_log": info_log,
            "warning_log": warning_log,
        }

    def run_mocha_summary(
        self,
        text,
        *,
        summary_text="summary text",
        feed_message_ts="123.456",
    ):
        app = FakeApp()
        client = FakeClient()
        ack = Mock()
        body = {
            "user_id": "UADMIN",
            "channel_id": "C123",
            "text": text,
        }

        mocha_handler.register(app)
        with patch.object(mocha_handler, "is_admin", return_value=True), \
            patch.object(
                mocha_handler,
                "_build_summary_text",
                return_value=summary_text,
            ) as build_summary_text, \
            patch.object(
                mocha_handler,
                "post_summary",
                return_value=feed_message_ts,
            ) as post_summary, \
            patch.object(mocha_handler.logger, "info") as info_log, \
            patch.object(mocha_handler.logger, "warning") as warning_log:
            app.commands["/mocha"](ack, body, client)

        return {
            "ack": ack,
            "client": client,
            "build_summary_text": build_summary_text,
            "post_summary": post_summary,
            "info_log": info_log,
            "warning_log": warning_log,
        }

    def test_create_bolt_app_registers_mocha_without_summary(self):
        app = FakeApp()

        with patch.object(app_module, "App", return_value=app):
            result = app_module.create_bolt_app()

        self.assertIs(result, app)
        self.assertIn("/mocha", app.commands)
        self.assertIn("/thanks", app.commands)
        self.assertNotIn("/summary", app.commands)

    def test_mocha_empty_input_shows_help(self):
        result = self.run_mocha("")

        result["get_connection"].assert_not_called()
        result["delete_recognition"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            mocha_handler.build_mocha_help(),
        )

    def test_mocha_help_shows_help(self):
        result = self.run_mocha("help")

        result["get_connection"].assert_not_called()
        result["delete_recognition"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            mocha_handler.build_mocha_help(),
        )

    def test_mocha_delete_removes_db_record_and_feed_message(self):
        recognition = {
            "id": 42,
            "sender_id": "U123",
            "receiver_id": "U456",
            "message": "잘못 입력",
            "feed_channel_id": "CFEED",
            "feed_message_ts": "123.456",
        }

        result = self.run_mocha("delete 42", recognition=recognition)

        result["ack"].assert_called_once()
        result["get_recognition_by_id"].assert_called_once_with(result["conn"], 42)
        result["delete_recognition"].assert_called_once_with(result["conn"], 42)
        self.assertEqual(result["conn"].commits, 1)
        self.assertEqual(result["conn"].rollbacks, 0)
        result["release_connection"].assert_called_once_with(result["conn"])
        self.assertEqual(
            result["client"].deleted_messages,
            [{"channel": "CFEED", "ts": "123.456"}],
        )
        result["info_log"].assert_called_once_with(
            "",
            extra={"event": "recognition_deleted", "detail": "42"},
        )
        result["warning_log"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "recognition #42와 feed 메시지를 삭제했습니다.",
        )

    def test_mocha_delete_without_feed_message(self):
        recognition = {
            "id": 42,
            "sender_id": "U123",
            "receiver_id": "U456",
            "message": "잘못 입력",
            "feed_channel_id": "CFEED",
            "feed_message_ts": None,
        }

        result = self.run_mocha("delete 42", recognition=recognition)

        result["delete_recognition"].assert_called_once_with(result["conn"], 42)
        self.assertEqual(result["conn"].commits, 1)
        self.assertEqual(result["conn"].rollbacks, 0)
        self.assertEqual(result["client"].deleted_messages, [])
        result["warning_log"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "recognition #42를 삭제했습니다. (feed 메시지 삭제 실패)",
        )

    def test_mocha_delete_keeps_db_when_feed_delete_fails(self):
        recognition = {
            "id": 42,
            "sender_id": "U123",
            "receiver_id": "U456",
            "message": "잘못 입력",
            "feed_channel_id": "CFEED",
            "feed_message_ts": "123.456",
        }

        result = self.run_mocha(
            "delete 42",
            recognition=recognition,
            delete_error=RuntimeError("slack failed"),
        )

        result["delete_recognition"].assert_called_once_with(result["conn"], 42)
        self.assertEqual(result["conn"].commits, 1)
        self.assertEqual(result["conn"].rollbacks, 0)
        result["warning_log"].assert_called_once()
        self.assertEqual(
            result["warning_log"].call_args.kwargs["extra"]["event"],
            "feed_delete_failed",
        )
        self.assertIn(
            "42: slack failed",
            result["warning_log"].call_args.kwargs["extra"]["detail"],
        )
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "recognition #42를 삭제했습니다. (feed 메시지 삭제 실패)",
        )

    def test_mocha_delete_shows_not_found_when_recognition_is_missing(self):
        result = self.run_mocha("delete 404", recognition=None)

        result["get_recognition_by_id"].assert_called_once_with(result["conn"], 404)
        result["delete_recognition"].assert_not_called()
        self.assertEqual(result["conn"].commits, 0)
        result["release_connection"].assert_called_once_with(result["conn"])
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "해당 recognition을 찾을 수 없습니다.",
        )

    def test_mocha_delete_requires_numeric_recognition_id(self):
        result = self.run_mocha("delete abc")

        result["get_connection"].assert_not_called()
        result["get_recognition_by_id"].assert_not_called()
        result["delete_recognition"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "올바른 recognition ID를 입력해주세요.",
        )

    def test_mocha_delete_missing_id(self):
        result = self.run_mocha("delete")

        result["get_connection"].assert_not_called()
        result["get_recognition_by_id"].assert_not_called()
        result["delete_recognition"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "올바른 recognition ID를 입력해주세요.",
        )

    def test_mocha_summary_weekly_posts_to_feed(self):
        result = self.run_mocha_summary("summary weekly", summary_text="weekly summary")

        result["ack"].assert_called_once()
        result["build_summary_text"].assert_called_once_with("weekly")
        result["post_summary"].assert_called_once_with(
            result["client"],
            "weekly summary",
        )
        result["info_log"].assert_called_once_with(
            "",
            extra={
                "event": "summary_posted",
                "user_id": "UADMIN",
                "detail": "weekly",
            },
        )
        result["warning_log"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "✅ 모카 감사 요약을 feed 채널에 올렸어요.",
        )

    def test_mocha_summary_weekly_preview_sends_ephemeral(self):
        result = self.run_mocha_summary(
            "summary weekly preview",
            summary_text="weekly summary",
        )

        result["build_summary_text"].assert_called_once_with("weekly")
        result["post_summary"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "weekly summary",
        )

    def test_mocha_summary_monthly_posts_to_feed(self):
        result = self.run_mocha_summary(
            "summary monthly",
            summary_text="monthly summary",
        )

        result["build_summary_text"].assert_called_once_with("monthly")
        result["post_summary"].assert_called_once_with(
            result["client"],
            "monthly summary",
        )
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "✅ 모카 감사 요약을 feed 채널에 올렸어요.",
        )

    def test_mocha_summary_monthly_preview_sends_ephemeral(self):
        result = self.run_mocha_summary(
            "summary monthly preview",
            summary_text="monthly summary",
        )

        result["build_summary_text"].assert_called_once_with("monthly")
        result["post_summary"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "monthly summary",
        )

    def test_mocha_summary_this_month_preview_sends_ephemeral(self):
        result = self.run_mocha_summary(
            "summary this-month preview",
            summary_text="this month summary",
        )

        result["build_summary_text"].assert_called_once_with("this-month")
        result["post_summary"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "this month summary",
        )

    def test_mocha_summary_this_month_without_preview_shows_help(self):
        result = self.run_mocha_summary("summary this-month")

        result["build_summary_text"].assert_not_called()
        result["post_summary"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            mocha_handler.build_mocha_help(),
        )

    def test_mocha_summary_unknown_subcommand_shows_help(self):
        result = self.run_mocha_summary("summary yesterday")

        result["build_summary_text"].assert_not_called()
        result["post_summary"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            mocha_handler.build_mocha_help(),
        )

    def test_mocha_summary_rejects_non_admin(self):
        result = self.run_mocha("summary weekly", is_admin=False)

        result["get_connection"].assert_not_called()
        result["delete_recognition"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "이 커맨드는 관리자만 사용할 수 있습니다.",
        )

    def test_mocha_summary_weekly_uses_previous_week_range(self):
        conn = FakeConnection()
        stats = {"start_date": date(2026, 5, 25), "end_date": date(2026, 5, 31)}

        with patch.object(mocha_handler, "get_connection", return_value=conn), \
            patch.object(
                mocha_handler,
                "get_previous_week_range",
                return_value=(date(2026, 5, 25), date(2026, 5, 31)),
            ) as get_previous_week_range_mock, \
            patch.object(mocha_handler, "load_weekly_stats", return_value=stats) as load_weekly_stats, \
            patch.object(mocha_handler, "build_weekly_summary", return_value="weekly summary"), \
            patch.object(mocha_handler, "release_connection") as release_connection:
            summary_text = mocha_handler._build_summary_text("weekly")

        self.assertEqual(summary_text, "weekly summary")
        get_previous_week_range_mock.assert_called_once_with()
        load_weekly_stats.assert_called_once_with(
            conn,
            date(2026, 5, 25),
            date(2026, 5, 31),
        )
        release_connection.assert_called_once_with(conn)

    def test_mocha_summary_this_month_uses_current_month_range(self):
        conn = FakeConnection()
        stats = {"start_date": date(2026, 6, 1), "end_date": date(2026, 6, 18)}

        with patch.object(mocha_handler, "get_connection", return_value=conn), \
            patch.object(
                mocha_handler,
                "get_current_month_range",
                return_value=(date(2026, 6, 1), date(2026, 6, 18)),
            ) as get_current_month_range_mock, \
            patch.object(mocha_handler, "load_weekly_stats", return_value=stats) as load_weekly_stats, \
            patch.object(mocha_handler, "build_current_month_summary", return_value="this month summary"), \
            patch.object(mocha_handler, "release_connection") as release_connection:
            summary_text = mocha_handler._build_summary_text("this-month")

        self.assertEqual(summary_text, "this month summary")
        get_current_month_range_mock.assert_called_once_with()
        load_weekly_stats.assert_called_once_with(
            conn,
            date(2026, 6, 1),
            date(2026, 6, 18),
        )
        release_connection.assert_called_once_with(conn)

    def test_mocha_rejects_unauthorized_user(self):
        result = self.run_mocha("delete 42", is_admin=False)

        result["get_connection"].assert_not_called()
        result["delete_recognition"].assert_not_called()
        self.assertEqual(result["client"].deleted_messages, [])
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            "이 커맨드는 관리자만 사용할 수 있습니다.",
        )

    def test_mocha_unknown_subcommand_shows_help(self):
        result = self.run_mocha("unknown")

        result["get_connection"].assert_not_called()
        result["delete_recognition"].assert_not_called()
        self.assertEqual(
            result["client"].ephemeral_messages[0]["text"],
            mocha_handler.build_mocha_help(),
        )


if __name__ == "__main__":
    unittest.main()
