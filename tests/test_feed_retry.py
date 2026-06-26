import os
import unittest
from unittest.mock import patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

import services.feed_retry as feed_retry  # noqa: E402


class FakeClient:
    def __init__(self, fail=False):
        self.fail = fail
        self.messages = []

    def chat_postMessage(self, **kwargs):
        if self.fail:
            raise RuntimeError("slack_failed")

        self.messages.append(kwargs)
        return {"ts": "123.456"}


class FakeApp:
    def __init__(self, client):
        self.client = client


class FakeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def failed_record(retry_count=0):
    return {
        "id": 42,
        "sender_id": "U123",
        "receiver_id": "U456",
        "message": "고마워요",
        "unit_count": 1,
        "retry_count": retry_count,
    }


class FeedRetryTest(unittest.TestCase):
    def test_retry_success_marks_feed_posted(self):
        conn = FakeConnection()
        app = FakeApp(FakeClient())

        with patch.object(feed_retry, "get_connection", return_value=conn), \
            patch.object(feed_retry, "get_failed_feed_records", return_value=[failed_record()]), \
            patch.object(feed_retry, "get_total_received", return_value=5), \
            patch.object(feed_retry, "mark_feed_posted") as mark_feed_posted, \
            patch.object(feed_retry, "increment_retry_count") as increment_retry_count:
            feed_retry.retry_failed_feeds(app)

        mark_feed_posted.assert_called_once_with(conn, 42)
        increment_retry_count.assert_not_called()
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 0)
        self.assertTrue(conn.closed)
        self.assertEqual(len(app.client.messages), 1)
        self.assertEqual(app.client.messages[0]["channel"], "C123")
        self.assertIn("<@U123>", app.client.messages[0]["text"])
        self.assertIn("<@U456>", app.client.messages[0]["text"])

    def test_retry_failure_increments_retry_count(self):
        conn = FakeConnection()
        app = FakeApp(FakeClient(fail=True))

        with patch.object(feed_retry, "get_connection", return_value=conn), \
            patch.object(feed_retry, "get_failed_feed_records", return_value=[failed_record()]), \
            patch.object(feed_retry, "get_total_received", return_value=5), \
            patch.object(
                feed_retry,
                "increment_retry_count",
                return_value={"retry_count": 1, "feed_post_status": "failed"},
            ) as increment_retry_count, \
            patch.object(feed_retry, "mark_feed_posted") as mark_feed_posted:
            feed_retry.retry_failed_feeds(app)

        increment_retry_count.assert_called_once_with(conn, 42)
        mark_feed_posted.assert_not_called()
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 1)
        self.assertTrue(conn.closed)

    def test_retry_count_three_abandons_feed(self):
        conn = FakeConnection()
        app = FakeApp(FakeClient(fail=True))

        with patch.object(feed_retry, "get_connection", return_value=conn), \
            patch.object(feed_retry, "get_failed_feed_records", return_value=[failed_record(2)]), \
            patch.object(feed_retry, "get_total_received", return_value=5), \
            patch.object(
                feed_retry,
                "increment_retry_count",
                return_value={"retry_count": 3, "feed_post_status": "abandoned"},
            ) as increment_retry_count:
            feed_retry.retry_failed_feeds(app)

        increment_retry_count.assert_called_once_with(conn, 42)
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 1)
        self.assertTrue(conn.closed)

    def test_no_failed_records_does_nothing(self):
        conn = FakeConnection()
        app = FakeApp(FakeClient())

        with patch.object(feed_retry, "FEED_ENABLED", True), \
            patch.object(feed_retry, "get_connection", return_value=conn), \
            patch.object(feed_retry, "get_failed_feed_records", return_value=[]), \
            patch.object(feed_retry, "get_total_received") as get_total_received, \
            patch.object(feed_retry, "mark_feed_posted") as mark_feed_posted, \
            patch.object(feed_retry, "increment_retry_count") as increment_retry_count:
            feed_retry.retry_failed_feeds(app)

        get_total_received.assert_not_called()
        mark_feed_posted.assert_not_called()
        increment_retry_count.assert_not_called()
        self.assertEqual(app.client.messages, [])
        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.rollbacks, 0)
        self.assertTrue(conn.closed)

    def test_feed_disabled_does_nothing(self):
        app = FakeApp(FakeClient())

        with patch.object(feed_retry, "FEED_ENABLED", False), \
            patch.object(feed_retry, "get_connection") as get_connection:
            feed_retry.retry_failed_feeds(app)

        get_connection.assert_not_called()
        self.assertEqual(app.client.messages, [])


if __name__ == "__main__":
    unittest.main()
