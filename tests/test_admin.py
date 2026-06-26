import os
import unittest
from unittest.mock import patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")

import services.admin as admin  # noqa: E402


class FakeClient:
    def __init__(self, users_responses=None, fail_users_list=False):
        self.users_responses = list(users_responses or [])
        self.fail_users_list = fail_users_list
        self.users_list_calls = []
        self.messages = []

    def users_list(self, **kwargs):
        self.users_list_calls.append(kwargs)
        if self.fail_users_list:
            raise RuntimeError("slack_failed")
        return self.users_responses.pop(0)

    def chat_postMessage(self, **kwargs):
        self.messages.append(kwargs)


class AdminServiceTest(unittest.TestCase):
    def tearDown(self):
        admin._admin_user_ids = frozenset()
        admin._admin_client = None

    def test_get_admin_user_ids_merges_allowlist_and_slack_admins(self):
        client = FakeClient(
            [
                {
                    "members": [
                        {"id": "USLACKADMIN", "is_admin": True},
                        {"id": "USLACKOWNER", "is_owner": True},
                        {"id": "UNORMAL", "is_admin": False, "is_owner": False},
                    ],
                    "response_metadata": {"next_cursor": "NEXT"},
                },
                {
                    "members": [
                        {"id": "USECOND", "is_admin": True},
                    ],
                    "response_metadata": {},
                },
            ]
        )

        with patch.object(admin, "ADMIN_USER_IDS", frozenset({"UALLOW"})):
            admin_ids = admin.get_admin_user_ids(client)

        self.assertEqual(
            admin_ids,
            frozenset({"UALLOW", "USLACKADMIN", "USLACKOWNER", "USECOND"}),
        )
        self.assertEqual(client.users_list_calls, [{}, {"cursor": "NEXT"}])

    def test_get_admin_user_ids_returns_allowlist_when_users_list_fails(self):
        client = FakeClient(fail_users_list=True)

        with patch.object(admin, "ADMIN_USER_IDS", frozenset({"UALLOW"})), \
            self.assertLogs("services.admin", level="WARNING") as logs:
            admin_ids = admin.get_admin_user_ids(client)

        self.assertEqual(admin_ids, frozenset({"UALLOW"}))
        self.assertTrue(
            any(
                getattr(record, "event", None) == "admin_list_fetch_failed"
                for record in logs.records
            )
        )

    def test_notify_admins_sends_dm_to_each_cached_admin(self):
        client = FakeClient()
        admin._admin_user_ids = frozenset({"U1", "U2"})

        admin.notify_admins(client, "hello")

        self.assertEqual(
            {message["channel"] for message in client.messages},
            {"U1", "U2"},
        )
        self.assertEqual({message["text"] for message in client.messages}, {"hello"})

    def test_notify_admins_logs_when_no_admins_configured(self):
        client = FakeClient()
        admin._admin_user_ids = frozenset()

        with self.assertLogs("services.admin", level="WARNING") as logs:
            admin.notify_admins(client, "hello")

        self.assertEqual(client.messages, [])
        self.assertTrue(
            any(
                getattr(record, "event", None) == "no_admins_configured"
                for record in logs.records
            )
        )


if __name__ == "__main__":
    unittest.main()
