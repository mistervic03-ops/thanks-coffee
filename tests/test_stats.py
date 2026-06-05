import os
import unittest
from datetime import date


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

from services.stats import get_current_week_range, get_previous_week_range  # noqa: E402


class WeeklyRangeTest(unittest.TestCase):
    def test_previous_week_range_for_monday_automation(self):
        start_date, end_date = get_previous_week_range(date(2026, 6, 1))

        self.assertEqual(start_date, date(2026, 5, 25))
        self.assertEqual(end_date, date(2026, 5, 31))

    def test_current_week_range_for_manual_trigger(self):
        start_date, end_date = get_current_week_range(date(2026, 6, 5))

        self.assertEqual(start_date, date(2026, 6, 1))
        self.assertEqual(end_date, date(2026, 6, 5))

    def test_current_week_range_on_monday(self):
        start_date, end_date = get_current_week_range(date(2026, 6, 1))

        self.assertEqual(start_date, date(2026, 6, 1))
        self.assertEqual(end_date, date(2026, 6, 1))


if __name__ == "__main__":
    unittest.main()
