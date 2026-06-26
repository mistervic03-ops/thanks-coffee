import os
import unittest
from unittest.mock import patch

from slack_sdk.errors import SlackApiError


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

import services.feed_retry as feed_retry  # noqa: E402


class FakeSlackResponse:
    def __init__(self, status_code, error):
        self.status_code = status_code
        self.error = error

    def get(self, key):
        if key == "error":
            return self.error

        return None


class FakeClient:
    def __init__(self, fail=False, error=None):
        self.fail = fail
        self.error = error
        self.messages = []

    def chat_postMessage(self, **kwargs):
        if self.error:
            raise self.error
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
            patch.object(feed_retry, "increment_retry_count") as increment_retry_count, \
            patch.object(feed_retry, "release_connection") as release_connection:
            feed_retry.retry_failed_feeds(app)

        mark_feed_posted.assert_called_once_with(conn, 42)
        increment_retry_count.assert_not_called()
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 0)
        release_connection.assert_called_once_with(conn)
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
            patch.object(feed_retry, "mark_feed_posted") as mark_feed_posted, \
            patch.object(feed_retry, "release_connection") as release_connection:
            feed_retry.retry_failed_feeds(app)

        increment_retry_count.assert_called_once_with(conn, 42)
        mark_feed_posted.assert_not_called()
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 1)
        release_connection.assert_called_once_with(conn)

    def test_retry_rate_limit_logs_slack_rate_limited(self):
        conn = FakeConnection()
        rate_limit_error = SlackApiError(
            "rate limited",
            FakeSlackResponse(status_code=429, error="ratelimited"),
        )
        app = FakeApp(FakeClient(error=rate_limit_error))

        with patch.object(feed_retry, "get_connection", return_value=conn), \
            patch.object(feed_retry, "get_failed_feed_records", return_value=[failed_record()]), \
            patch.object(feed_retry, "get_total_received", return_value=5), \
            patch.object(
                feed_retry,
                "increment_retry_count",
                return_value={"retry_count": 1, "feed_post_status": "failed"},
            ), \
            patch.object(feed_retry.logger, "warning") as warning_log, \
            patch.object(feed_retry, "release_connection"):
            feed_retry.retry_failed_feeds(app)

        warning_log.assert_called_once()
        extra = warning_log.call_args.kwargs["extra"]
        self.assertEqual(extra["event"], "slack_rate_limited")
        self.assertEqual(
            extra["detail"],
            "feed retry rate limited, recognition_id: 42",
        )
        self.assertNotEqual(extra["event"], "feed_retry_failed")

    def test_retry_general_error_logs_feed_retry_failed(self):
        conn = FakeConnection()
        app = FakeApp(FakeClient(fail=True))

        with patch.object(feed_retry, "get_connection", return_value=conn), \
            patch.object(feed_retry, "get_failed_feed_records", return_value=[failed_record()]), \
            patch.object(feed_retry, "get_total_received", return_value=5), \
            patch.object(
                feed_retry,
                "increment_retry_count",
                return_value={"retry_count": 1, "feed_post_status": "failed"},
            ), \
            patch.object(feed_retry.logger, "warning") as warning_log, \
            patch.object(feed_retry, "release_connection"):
            feed_retry.retry_failed_feeds(app)

        warning_log.assert_called_once()
        extra = warning_log.call_args.kwargs["extra"]
        self.assertEqual(extra["event"], "feed_retry_failed")
        self.assertEqual(extra["detail"], "retry_count=1")
        self.assertNotEqual(extra["event"], "slack_rate_limited")

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
            ) as increment_retry_count, \
            patch.object(feed_retry, "notify_admins") as notify_admins, \
            patch.object(feed_retry, "release_connection") as release_connection:
            feed_retry.retry_failed_feeds(app)

        increment_retry_count.assert_called_once_with(conn, 42)
        notify_admins.assert_called_once_with(
            app.client,
            "[mocha] feed 게시가 3회 재시도 후 포기되었습니다. recognition_id: 42",
        )
        self.assertEqual(conn.commits, 1)
        self.assertEqual(conn.rollbacks, 1)
        release_connection.assert_called_once_with(conn)

    def test_no_failed_records_does_nothing(self):
        conn = FakeConnection()
        app = FakeApp(FakeClient())

        with patch.object(feed_retry, "FEED_ENABLED", True), \
            patch.object(feed_retry, "get_connection", return_value=conn), \
            patch.object(feed_retry, "get_failed_feed_records", return_value=[]), \
            patch.object(feed_retry, "get_total_received") as get_total_received, \
            patch.object(feed_retry, "mark_feed_posted") as mark_feed_posted, \
            patch.object(feed_retry, "increment_retry_count") as increment_retry_count, \
            patch.object(feed_retry, "release_connection") as release_connection:
            feed_retry.retry_failed_feeds(app)

        get_total_received.assert_not_called()
        mark_feed_posted.assert_not_called()
        increment_retry_count.assert_not_called()
        self.assertEqual(app.client.messages, [])
        self.assertEqual(conn.commits, 0)
        self.assertEqual(conn.rollbacks, 0)
        release_connection.assert_called_once_with(conn)

    def test_feed_disabled_does_nothing(self):
        app = FakeApp(FakeClient())

        with patch.object(feed_retry, "FEED_ENABLED", False), \
            patch.object(feed_retry, "get_connection") as get_connection:
            feed_retry.retry_failed_feeds(app)

        get_connection.assert_not_called()
        self.assertEqual(app.client.messages, [])


if __name__ == "__main__":
    unittest.main()
