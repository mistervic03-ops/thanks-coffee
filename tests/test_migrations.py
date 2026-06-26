import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

import db.queries as queries  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last_fetchone = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        if normalized.startswith("CREATE TABLE IF NOT EXISTS schema_migrations"):
            return

        if normalized.startswith("SELECT 1 FROM schema_migrations"):
            filename = params[0]
            self.last_fetchone = (1,) if filename in self.conn.applied else None
            return

        if normalized.startswith("INSERT INTO schema_migrations"):
            self.conn.applied.add(params[0])
            return

        self.conn.executed_migrations.append(normalized)

    def fetchone(self):
        return self.last_fetchone


class FakeConnection:
    def __init__(self):
        self.applied = set()
        self.executed_migrations = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class MigrationRunnerTest(unittest.TestCase):
    def test_init_db_does_not_rerun_applied_migrations(self):
        conn = FakeConnection()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir = Path(tmpdir)
            migration_dir = db_dir / "migrations"
            migration_dir.mkdir()
            (migration_dir / "001_init.sql").write_text("CREATE TABLE one (id INT);")
            (migration_dir / "002_second.sql").write_text("CREATE TABLE two (id INT);")

            with patch.object(queries, "__file__", str(db_dir / "queries.py")), \
                patch.object(queries, "get_connection", return_value=conn):
                queries.init_db()
                queries.init_db()

        self.assertEqual(
            conn.executed_migrations,
            [
                "CREATE TABLE one (id INT);",
                "CREATE TABLE two (id INT);",
            ],
        )
        self.assertEqual(conn.applied, {"001_init.sql", "002_second.sql"})
        self.assertEqual(conn.commits, 2)
        self.assertEqual(conn.rollbacks, 0)
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()
