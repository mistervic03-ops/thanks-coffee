import os
import unittest
from datetime import date
from unittest.mock import patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("ANNOUNCEMENT_CHANNEL_ID", "C123")

from services.stats import (  # noqa: E402
    get_current_month_range,
    get_current_week_range,
    get_previous_week_range,
)
import scheduler  # noqa: E402


class FakeConnection:
    pass


class FakeApp:
    def __init__(self):
        self.client = object()


class FakeBackgroundScheduler:
    instances = []

    def __init__(self, timezone):
        self.timezone = timezone
        self.jobs = []
        self.running = False
        FakeBackgroundScheduler.instances.append(self)

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append({"func": func, "trigger": trigger, **kwargs})

    def start(self):
        self.running = True


class FakeReminderClient:
    def __init__(self, users_responses=None):
        self.users_responses = users_responses or []
        self.users_list_calls = []
        self.posted_messages = []

    def users_list(self, **kwargs):
        self.users_list_calls.append(kwargs)
        return self.users_responses.pop(0)

    def chat_postMessage(self, **kwargs):
        self.posted_messages.append(kwargs)
        return {"ts": "123.456"}


class FakeAnthropicMessages:
    def __init__(self, response):
        self.response = response
        self.create_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.response


class FakeAnthropicClient:
    def __init__(self, response):
        self.messages = FakeAnthropicMessages(response)


class SchedulerRegistrationTest(unittest.TestCase):
    def setUp(self):
        scheduler._scheduler = None
        FakeBackgroundScheduler.instances = []

    def tearDown(self):
        scheduler._scheduler = None

    def test_start_scheduler_registers_existing_jobs_when_enabled(self):
        with patch.object(scheduler, "BackgroundScheduler", FakeBackgroundScheduler):
            scheduler_instance = scheduler.start_scheduler(
                FakeApp(),
                summary_jobs_enabled=True,
                reminder_enabled=False,
            )

        self.assertEqual(
            [job["id"] for job in scheduler_instance.jobs],
            ["weekly_summary", "monthly_summary", "feed_retry"],
        )

    def test_start_scheduler_registers_reminder_only_when_only_reminder_enabled(self):
        with patch.object(scheduler, "BackgroundScheduler", FakeBackgroundScheduler):
            scheduler_instance = scheduler.start_scheduler(
                FakeApp(),
                summary_jobs_enabled=False,
                reminder_enabled=True,
            )

        self.assertEqual([job["id"] for job in scheduler_instance.jobs], ["weekly_reminder"])
        reminder_job = scheduler_instance.jobs[0]
        self.assertEqual(reminder_job["trigger"], "cron")
        self.assertEqual(reminder_job["day_of_week"], "wed")
        self.assertEqual(reminder_job["hour"], 10)
        self.assertEqual(reminder_job["minute"], 0)


class ScheduledSummaryLockTest(unittest.TestCase):
    def test_lock_success_posts_summary_and_releases_lock(self):
        conn = FakeConnection()
        client = object()
        summary_blocks = [{"type": "header", "text": {"type": "plain_text", "text": "weekly"}}]
        leaderboard_blocks = [{"type": "header", "text": {"type": "plain_text", "text": "leaderboard"}}]

        with patch.object(scheduler, "get_connection", return_value=conn), \
            patch.object(scheduler, "try_summary_lock", return_value=True) as try_summary_lock, \
            patch.object(scheduler, "release_summary_lock") as release_summary_lock, \
            patch.object(scheduler, "get_previous_week_range", return_value=("start", "end")), \
            patch.object(scheduler, "load_weekly_stats", return_value={"total_recognitions": 0}) as load_weekly_stats, \
            patch.object(scheduler, "build_weekly_summary", return_value=summary_blocks), \
            patch.object(scheduler, "build_leaderboard_blocks", return_value=leaderboard_blocks) as build_leaderboard_blocks, \
            patch.object(scheduler, "post_summary", return_value="123.456") as post_summary, \
            patch.object(scheduler, "notify_admins_with_blocks") as notify_admins_with_blocks, \
            patch.object(scheduler, "release_connection") as release_connection:
            scheduler.run_weekly_summary(client)

        try_summary_lock.assert_called_once_with(conn, "weekly")
        load_weekly_stats.assert_called_once_with(conn, "start", "end")
        post_summary.assert_called_once_with(client, summary_blocks)
        build_leaderboard_blocks.assert_called_once_with({"total_recognitions": 0})
        notify_admins_with_blocks.assert_called_once_with(client, leaderboard_blocks)
        release_summary_lock.assert_called_once_with(conn, "weekly")
        release_connection.assert_called_once_with(conn)

    def test_lock_failure_skips_summary_without_logging_or_posting(self):
        conn = FakeConnection()
        client = object()

        with patch.object(scheduler, "get_connection", return_value=conn), \
            patch.object(scheduler, "try_summary_lock", return_value=False) as try_summary_lock, \
            patch.object(scheduler, "release_summary_lock") as release_summary_lock, \
            patch.object(scheduler, "load_weekly_stats") as load_weekly_stats, \
            patch.object(scheduler, "post_summary") as post_summary, \
            patch.object(scheduler.logger, "info") as info_log, \
            patch.object(scheduler.logger, "warning") as warning_log, \
            patch.object(scheduler, "release_connection") as release_connection:
            scheduler.run_weekly_summary(client)

        try_summary_lock.assert_called_once_with(conn, "weekly")
        load_weekly_stats.assert_not_called()
        post_summary.assert_not_called()
        release_summary_lock.assert_not_called()
        info_log.assert_not_called()
        warning_log.assert_not_called()
        release_connection.assert_called_once_with(conn)

    def test_summary_failure_still_releases_lock(self):
        conn = FakeConnection()
        client = object()

        with patch.object(scheduler, "get_connection", return_value=conn), \
            patch.object(scheduler, "try_summary_lock", return_value=True), \
            patch.object(scheduler, "release_summary_lock") as release_summary_lock, \
            patch.object(scheduler, "get_previous_month", return_value=(2026, 6)), \
            patch.object(scheduler, "load_monthly_stats", return_value={"total_recognitions": 0}), \
            patch.object(scheduler, "build_monthly_summary", return_value="monthly summary"), \
            patch.object(scheduler, "post_summary", side_effect=RuntimeError("slack failed")), \
            patch.object(scheduler, "release_connection") as release_connection:
            scheduler.run_monthly_summary(client)

        release_summary_lock.assert_called_once_with(conn, "monthly")
        release_connection.assert_called_once_with(conn)


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

    def test_current_month_range_returns_month_to_date(self):
        start_date, end_date = get_current_month_range(date(2026, 6, 18))

        self.assertEqual(start_date, date(2026, 6, 1))
        self.assertEqual(end_date, date(2026, 6, 18))


class WeeklyReminderTest(unittest.TestCase):
    def test_get_active_workspace_users_filters_deleted_and_bots(self):
        client = FakeReminderClient(
            users_responses=[
                {
                    "members": [
                        {
                            "id": "UACTIVE",
                            "deleted": False,
                            "is_bot": False,
                            "profile": {"display_name": "민수"},
                        },
                        {
                            "id": "UDELETED",
                            "deleted": True,
                            "is_bot": False,
                            "profile": {"display_name": "퇴사자"},
                        },
                    ],
                    "response_metadata": {"next_cursor": "NEXT"},
                },
                {
                    "members": [
                        {
                            "id": "UBOT",
                            "deleted": False,
                            "is_bot": True,
                            "profile": {"display_name": "bot"},
                        },
                        {
                            "id": "USLACKBOT",
                            "deleted": False,
                            "is_bot": False,
                            "profile": {"display_name": "Slackbot"},
                        },
                        {
                            "id": "USECOND",
                            "deleted": False,
                            "is_bot": False,
                            "profile": {"real_name": "지윤"},
                        },
                    ],
                    "response_metadata": {"next_cursor": ""},
                },
            ]
        )

        users = scheduler.get_active_workspace_users(client)

        self.assertEqual(
            users,
            [
                {"id": "UACTIVE", "name": "민수"},
                {"id": "USECOND", "name": "지윤"},
            ],
        )
        self.assertEqual(client.users_list_calls, [{}, {"cursor": "NEXT"}])

    def test_run_weekly_reminder_posts_claude_text(self):
        client = FakeReminderClient(
            users_responses=[
                {
                    "members": [
                        {
                            "id": "UACTIVE",
                            "deleted": False,
                            "is_bot": False,
                            "profile": {"display_name": "민수"},
                        }
                    ]
                }
            ]
        )
        anthropic_client = FakeAnthropicClient(
            {"content": [{"text": "민: 믿음직한 협업 고마워요.\n/thanks @민수 고마운 내용"}]}
        )

        with patch.object(scheduler, "create_anthropic_client", return_value=anthropic_client), \
            patch.object(scheduler, "notify_cached_admins") as notify_cached_admins:
            scheduler.run_weekly_reminder(client)

        self.assertEqual(
            client.posted_messages,
            [
                {
                    "channel": "C123",
                    "text": "민: 믿음직한 협업 고마워요.\n/thanks @민수 고마운 내용",
                }
            ],
        )
        notify_cached_admins.assert_not_called()
        self.assertEqual(
            anthropic_client.messages.create_calls[0]["model"],
            scheduler.ANTHROPIC_MODEL,
        )

    def test_run_weekly_reminder_uses_fallback_and_notifies_admins_on_claude_failure(self):
        client = FakeReminderClient()
        user = {"id": "UACTIVE", "name": "민수"}
        template = "오늘은 {name}님에게 `/thanks {mention} 고마워요`를 보내보세요."

        with patch.object(scheduler, "get_active_workspace_users", return_value=[user]), \
            patch.object(
                scheduler,
                "build_claude_reminder_text",
                side_effect=RuntimeError("claude down"),
            ), \
            patch.object(scheduler.random, "choice", side_effect=[user, template]), \
            patch.object(scheduler, "notify_cached_admins") as notify_cached_admins:
            scheduler.run_weekly_reminder(client)

        self.assertEqual(
            client.posted_messages,
            [
                {
                    "channel": "C123",
                    "text": "오늘은 민수님에게 `/thanks <@UACTIVE> 고마워요`를 보내보세요.",
                }
            ],
        )
        notify_cached_admins.assert_called_once_with(
            "[mocha] 주간 리마인더 Claude API 호출에 실패했습니다: claude down"
        )

    def test_build_fallback_reminder_text_uses_random_template(self):
        user = {"id": "UACTIVE", "name": "민수"}
        template = "{name}님에게 `/thanks {mention} 고마워요`를 남겨보세요."

        with patch.object(scheduler.random, "choice", return_value=template) as choice:
            text = scheduler.build_fallback_reminder_text(user)

        choice.assert_called_once_with(scheduler.FALLBACK_REMINDER_TEMPLATES)
        self.assertEqual(text, "민수님에게 `/thanks <@UACTIVE> 고마워요`를 남겨보세요.")


if __name__ == "__main__":
    unittest.main()
