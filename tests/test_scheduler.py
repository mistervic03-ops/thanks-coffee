import os
import unittest
from datetime import date
from unittest.mock import patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

from services.stats import (  # noqa: E402
    get_current_month_range,
    get_current_week_range,
    get_previous_week_range,
)
import scheduler  # noqa: E402


class FakeConnection:
    pass


class ScheduledSummaryLockTest(unittest.TestCase):
    def test_lock_success_posts_summary_and_releases_lock(self):
        conn = FakeConnection()
        client = object()

        with patch.object(scheduler, "get_connection", return_value=conn), \
            patch.object(scheduler, "try_summary_lock", return_value=True) as try_summary_lock, \
            patch.object(scheduler, "release_summary_lock") as release_summary_lock, \
            patch.object(scheduler, "get_previous_week_range", return_value=("start", "end")), \
            patch.object(scheduler, "load_weekly_stats", return_value={"total_recognitions": 0}) as load_weekly_stats, \
            patch.object(scheduler, "build_weekly_summary", return_value="weekly summary"), \
            patch.object(scheduler, "post_summary") as post_summary, \
            patch.object(scheduler, "release_connection") as release_connection:
            scheduler.run_weekly_summary(client)

        try_summary_lock.assert_called_once_with(conn, "weekly")
        load_weekly_stats.assert_called_once_with(conn, "start", "end")
        post_summary.assert_called_once_with(client, "weekly summary")
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


if __name__ == "__main__":
    unittest.main()
