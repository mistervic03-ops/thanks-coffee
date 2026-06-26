import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("FEED_CHANNEL_ID", "C123")
os.environ.setdefault("RECOGNITION_EMOJI", "☕")
os.environ.setdefault("RECOGNITION_UNIT", "커피")

import handlers.home as home_handler  # noqa: E402


class FakeApp:
    def __init__(self):
        self.events = {}

    def event(self, name):
        def decorator(handler):
            self.events[name] = handler
            return handler

        return decorator


class FakeClient:
    def __init__(self, users=None):
        self.published_views = []
        self.users = users or {}

    def views_publish(self, **kwargs):
        self.published_views.append(kwargs)

    def users_info(self, user):
        return {"user": self.users[user]}


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def view_text(view):
    values = []
    for block in view["blocks"]:
        if "text" in block:
            values.append(block["text"]["text"])
        for element in block.get("elements", []):
            values.append(element["text"])
    return "\n".join(values)


def block_texts(view, block_type):
    return [
        block["text"]["text"]
        for block in view["blocks"]
        if block["type"] == block_type and "text" in block
    ]


def field_texts(view):
    return [
        field["text"]
        for block in view["blocks"]
        for field in block.get("fields", [])
    ]


class HomeViewBuilderTest(unittest.TestCase):
    def test_build_home_view_keeps_messages_central(self):
        view = home_handler.build_home_view(
            remaining=3,
            summary={
                "received_week": 2,
                "received_month": 5,
                "received_total": 12,
                "sent_week": 1,
                "sent_month": 4,
                "sent_total": 9,
            },
            received_recognitions=[
                {
                    "sender_name": "민준",
                    "message": "도와줘서 고마워요",
                    "unit_count": 2,
                    "created_at": datetime(2026, 6, 21, 15, 30, tzinfo=timezone.utc),
                }
            ],
            sent_recognitions=[
                {
                    "receiver_name": "서연",
                    "message": "큰 도움을 줘서 고마워요",
                    "unit_count": 3,
                    "created_at": datetime(2026, 6, 20, 1, 0, tzinfo=timezone.utc),
                }
            ],
        )

        text = view_text(view)
        self.assertEqual(view["type"], "home")
        self.assertEqual(
            block_texts(view, "header"),
            ["☕ 모카 Home", "나의 커피 요약", "최근 받은 감사", "최근 보낸 감사"],
        )
        self.assertGreaterEqual(
            sum(1 for block in view["blocks"] if block["type"] == "divider"),
            3,
        )
        self.assertIn("*오늘 남은 커피*", field_texts(view))
        self.assertIn("`3잔`", field_texts(view))
        self.assertIn("*받은 커피*\n이번 주 2잔\n이번 달 5잔\n누적 12잔", field_texts(view))
        self.assertIn("*보낸 커피*\n이번 주 한 잔\n이번 달 4잔\n누적 9잔", field_texts(view))
        self.assertIn("내가 주고받은 감사 흐름을 조용히 돌아보는 용도예요.", text)
        self.assertIn("고마운 순간을 놓치지 않도록 모카가 기록해둘게요.", text)
        self.assertIn("채널에서 `/thanks @user 메시지`로 바로 전할 수 있어요.", text)
        self.assertIn("최근 받은 감사", text)
        self.assertIn("*민준*님이 전했어요", text)
        self.assertIn("2026-06-22", text)
        self.assertIn("도와줘서 고마워요", text)
        self.assertIn("최근 보낸 감사", text)
        self.assertIn("*서연*님에게 보냈어요", text)
        self.assertIn("큰 도움을 줘서 고마워요", text)
        self.assertLess(text.index("최근 받은 감사"), text.index("최근 보낸 감사"))
        self.assertIn("💡 *사용 예시*", text)
        self.assertIn("/thanks @user 빠르게 도와줘서 고마워요", text)
        self.assertIn("/thanks @user 3 큰 도움을 줘서 고마워요", text)
        self.assertNotIn("받은 감사, 보낸 감사, 오늘 남은 수량", text)
        self.assertNotIn("/thanks status", text)
        self.assertNotIn("/thanks received", text)
        self.assertNotIn("leaderboard", text.lower())
        self.assertNotIn("badge", text.lower())
        self.assertNotIn("ranking", text.lower())
        self.assertNotIn("순위", text)
        self.assertNotIn("랭킹", text)

    def test_build_home_view_shows_received_empty_state(self):
        view = home_handler.build_home_view(
            remaining=0,
            summary={
                "received_week": 0,
                "received_month": 0,
                "received_total": 0,
                "sent_week": 0,
                "sent_month": 0,
                "sent_total": 0,
            },
            received_recognitions=[],
            sent_recognitions=[],
        )

        text = view_text(view)
        self.assertIn("*오늘 남은 커피*", field_texts(view))
        self.assertIn("`0잔`", field_texts(view))
        self.assertIn("*받은 커피*\n이번 주 0잔\n이번 달 0잔\n누적 0잔", field_texts(view))
        self.assertIn("*보낸 커피*\n이번 주 0잔\n이번 달 0잔\n누적 0잔", field_texts(view))
        self.assertIn("> 아직 받은 감사가 없어요. 곧 따뜻한 마음이 도착할 거예요.", text)
        self.assertIn("> 아직 보낸 감사가 없어요. 오늘 도움을 준 동료에게 전해보세요.", text)


class HomeEventHandlerTest(unittest.TestCase):
    def test_app_home_opened_publishes_home_view(self):
        app = FakeApp()
        client = FakeClient(
            users={
                "U456": {"profile": {"display_name": "민준"}},
                "U789": {"profile": {"display_name": "서연"}},
            }
        )
        conn = FakeConnection()
        summary = {
            "received_week": 1,
            "received_month": 2,
            "received_total": 5,
            "sent_week": 3,
            "sent_month": 4,
            "sent_total": 7,
        }
        received_recognitions = [
            {
                "sender_id": "U456",
                "message": "빠른 공유 감사합니다",
                "unit_count": 1,
                "created_at": datetime(2026, 6, 20, 1, 0, tzinfo=timezone.utc),
            }
        ]
        sent_recognitions = [
            {
                "receiver_id": "U789",
                "message": "큰 도움을 줘서 고마워요",
                "unit_count": 3,
                "created_at": datetime(2026, 6, 19, 1, 0, tzinfo=timezone.utc),
            }
        ]

        home_handler.register(app)
        with patch.object(home_handler, "get_connection", return_value=conn) as get_connection, \
            patch.object(home_handler, "get_sent_today", return_value=2) as get_sent_today, \
            patch.object(
                home_handler,
                "get_personal_recognition_summary",
                return_value=summary,
            ) as get_personal_recognition_summary, \
            patch.object(
                home_handler,
                "get_recent_received_recognitions",
                return_value=received_recognitions,
            ) as get_recent_received_recognitions, \
            patch.object(
                home_handler,
                "get_recent_sent_recognitions",
                return_value=sent_recognitions,
            ) as get_recent_sent_recognitions, \
            patch.object(home_handler, "release_connection") as release_connection:
            app.events["app_home_opened"](
                {"type": "app_home_opened", "user": "U123", "tab": "home"},
                client,
            )

        get_connection.assert_called_once()
        get_sent_today.assert_called_once_with(conn, "U123")
        get_personal_recognition_summary.assert_called_once_with(conn, "U123")
        get_recent_received_recognitions.assert_called_once_with(conn, "U123", 5)
        get_recent_sent_recognitions.assert_called_once_with(conn, "U123", 5)
        release_connection.assert_called_once_with(conn)
        self.assertEqual(len(client.published_views), 1)
        self.assertEqual(client.published_views[0]["user_id"], "U123")

        text = view_text(client.published_views[0]["view"])
        self.assertIn("*오늘 남은 커피*", field_texts(client.published_views[0]["view"]))
        self.assertIn("`3잔`", field_texts(client.published_views[0]["view"]))
        self.assertIn(
            "*받은 커피*\n이번 주 한 잔\n이번 달 2잔\n누적 5잔",
            field_texts(client.published_views[0]["view"]),
        )
        self.assertIn(
            "*보낸 커피*\n이번 주 3잔\n이번 달 4잔\n누적 7잔",
            field_texts(client.published_views[0]["view"]),
        )
        self.assertIn("*민준*님이 전했어요", text)
        self.assertIn("빠른 공유 감사합니다", text)
        self.assertIn("*서연*님에게 보냈어요", text)
        self.assertIn("큰 도움을 줘서 고마워요", text)

    def test_app_home_opened_ignores_non_home_tab(self):
        app = FakeApp()
        client = FakeClient()

        home_handler.register(app)
        with patch.object(home_handler, "get_connection") as get_connection:
            app.events["app_home_opened"](
                {"type": "app_home_opened", "user": "U123", "tab": "messages"},
                client,
            )

        get_connection.assert_not_called()
        self.assertEqual(client.published_views, [])


if __name__ == "__main__":
    unittest.main()
