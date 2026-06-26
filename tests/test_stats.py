import os
import unittest
from datetime import date


os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_APP_TOKEN", "xapp-test")
os.environ.setdefault("DATABASE_URL", "postgresql://user:pass@localhost/db")
os.environ.setdefault("ANNOUNCEMENT_CHANNEL_ID", "C123")

from services.feed import build_summary_fallback_text  # noqa: E402
from services.stats import (  # noqa: E402
    build_leaderboard_blocks,
    build_monthly_summary,
    build_weekly_summary,
)


def stats(**overrides):
    data = {
        "start_date": date(2026, 6, 15),
        "end_date": date(2026, 6, 21),
        "year": 2026,
        "month": 6,
        "total_recognitions": 4,
        "total_unit_count": 8,
        "participant_count": 5,
        "top_senders": [
            {"user_id": "U111", "unit_count": 4, "recognition_count": 2},
            {"user_id": "U444", "unit_count": 3, "recognition_count": 1},
            {"user_id": "U555", "unit_count": 1, "recognition_count": 1},
        ],
        "top_receivers": [
            {"user_id": "U111", "unit_count": 4, "recognition_count": 2},
            {"user_id": "U222", "unit_count": 3, "recognition_count": 1},
            {"user_id": "U333", "unit_count": 1, "recognition_count": 1},
        ],
    }
    data.update(overrides)
    return data


class SummaryBlockBuilderTest(unittest.TestCase):
    def test_build_weekly_summary_returns_participant_blocks(self):
        blocks = build_weekly_summary(stats())

        self.assertEqual(blocks[0]["type"], "header")
        self.assertEqual(
            blocks[0]["text"]["text"],
            "📊 직전 주 모카 감사 요약 (6/15 – 6/21)",
        )
        self.assertEqual(
            blocks[1]["text"]["text"],
            "이번 주 팀에서 커피 *8잔*이 오갔어요 ☕\n5명이 감사를 주고받았습니다.",
        )
        self.assertEqual(
            blocks[2]["fields"][0]["text"],
            "*💌 감사를 전한 분들*\n<@U111> <@U444> <@U555>",
        )
        self.assertEqual(
            blocks[2]["fields"][1]["text"],
            "*🎉 감사를 받은 분들*\n<@U111> <@U222> <@U333>",
        )
        self.assertEqual(build_summary_fallback_text(blocks), "📊 직전 주 모카 감사 요약")

    def test_build_monthly_summary_uses_monthly_title(self):
        blocks = build_monthly_summary(stats(year=2026, month=5))

        self.assertEqual(blocks[0]["text"]["text"], "📊 2026년 5월 모카 감사 요약")
        self.assertEqual(build_summary_fallback_text(blocks), "📊 2026년 5월 모카 감사 요약")

    def test_empty_weekly_summary_keeps_empty_message(self):
        blocks = build_weekly_summary(
            stats(
                total_recognitions=0,
                total_unit_count=0,
                participant_count=0,
                top_senders=[],
                top_receivers=[],
            )
        )

        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[1]["text"]["text"], "직전 주에는 아직 첫 감사가 없었어요.")

    def test_build_leaderboard_blocks_shows_top_five(self):
        leaderboard_stats = stats(
            top_receivers=[
                {"user_id": f"UR{index}", "unit_count": index, "recognition_count": 1}
                for index in range(7, 1, -1)
            ],
            top_senders=[
                {"user_id": f"US{index}", "unit_count": index, "recognition_count": 1}
                for index in range(6, 0, -1)
            ],
        )

        blocks = build_leaderboard_blocks(leaderboard_stats)

        self.assertEqual(
            blocks[0]["text"]["text"],
            "📋 관리자용 상세 현황 (나에게만 보여요)",
        )
        self.assertEqual(
            blocks[1]["fields"][0]["text"],
            (
                "*🎉 감사를 많이 받은 분*\n"
                "1. <@UR7> — 7잔\n"
                "2. <@UR6> — 6잔\n"
                "3. <@UR5> — 5잔\n"
                "4. <@UR4> — 4잔\n"
                "5. <@UR3> — 3잔"
            ),
        )
        self.assertEqual(
            blocks[1]["fields"][1]["text"],
            (
                "*💌 감사를 많이 전한 분*\n"
                "1. <@US6> — 6잔\n"
                "2. <@US5> — 5잔\n"
                "3. <@US4> — 4잔\n"
                "4. <@US3> — 3잔\n"
                "5. <@US2> — 2잔"
            ),
        )


if __name__ == "__main__":
    unittest.main()
