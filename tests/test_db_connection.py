import os
import unittest
from unittest.mock import Mock, patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

import db.queries as queries  # noqa: E402


class DbConnectionTest(unittest.TestCase):
    def tearDown(self):
        queries._pool = None

    def test_get_connection_notifies_admins_when_connection_fails(self):
        pool = Mock()
        pool.getconn.side_effect = RuntimeError("db down")

        with patch.object(queries, "_pool", pool), \
            patch.object(queries, "notify_cached_admins") as notify_cached_admins:
            with self.assertRaises(RuntimeError) as ctx:
                queries.get_connection()

        notify_cached_admins.assert_called_once_with(
            "[mocha] DB 연결에 실패했습니다: db down"
        )
        self.assertEqual(
            getattr(ctx.exception, "_admin_notified_event", None),
            "db_connection_failed",
        )

    def test_get_connection_requires_initialized_pool(self):
        with self.assertRaisesRegex(RuntimeError, "pool is not initialized"):
            queries.get_connection()

    def test_release_connection_returns_connection_to_pool(self):
        pool = Mock()
        conn = object()

        with patch.object(queries, "_pool", pool):
            queries.release_connection(conn)

        pool.putconn.assert_called_once_with(conn)

    def test_close_connection_closes_pool(self):
        pool = Mock()

        with patch.object(queries, "_pool", pool):
            queries.close_connection()

        pool.closeall.assert_called_once_with()
        self.assertIsNone(queries._pool)


if __name__ == "__main__":
    unittest.main()
