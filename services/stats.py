from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from config import RECOGNITION_EMOJI, RECOGNITION_UNIT
from db.queries import get_monthly_stats, get_weekly_stats


KST = ZoneInfo("Asia/Seoul")


def get_previous_week_range(today=None):
    today = today or datetime.now(KST).date()
    current_week_monday = today - timedelta(days=today.weekday())
    end_date = current_week_monday - timedelta(days=1)
    start_date = end_date - timedelta(days=6)
    return start_date, end_date


def get_current_week_range(today=None):
    today = today or datetime.now(KST).date()
    start_date = today - timedelta(days=today.weekday())
    return start_date, today


def get_current_month_range(today=None):
    today = today or datetime.now(KST).date()
    return date(today.year, today.month, 1), today


def get_previous_month(today=None):
    today = today or datetime.now(KST).date()
    first_day_this_month = date(today.year, today.month, 1)
    last_day_previous_month = first_day_this_month - timedelta(days=1)
    return last_day_previous_month.year, last_day_previous_month.month


def load_weekly_stats(conn, start_date, end_date):
    return get_weekly_stats(conn, start_date, end_date)


def load_monthly_stats(conn, year, month):
    return get_monthly_stats(conn, year, month)


def build_weekly_summary(stats):
    title = (
        "📊 직전 주 모카 감사 요약 "
        f"({_format_date(stats['start_date'])} – {_format_date(stats['end_date'])})"
    )
    return _build_summary(title, stats, "직전 주에는 아직 첫 감사가 없었어요.")


def build_monthly_summary(stats):
    title = f"📊 {stats['year']}년 {stats['month']}월 모카 감사 요약"
    return _build_summary(title, stats, "이번 달에는 첫 감사를 남겨보세요.")


def build_current_month_summary(stats):
    title = (
        f"📊 {stats['end_date'].year}년 {stats['end_date'].month}월 "
        "현재까지 모카 감사 요약"
    )
    return _build_summary(title, stats, "이번 달에는 아직 첫 감사가 없었어요.")


def build_leaderboard_blocks(stats):
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📋 관리자용 상세 현황 (나에게만 보여요)",
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "*🎉 감사를 많이 받은 분*\n"
                        f"{_format_leaderboard(stats['top_receivers'])}"
                    ),
                },
                {
                    "type": "mrkdwn",
                    "text": (
                        "*💌 감사를 많이 전한 분*\n"
                        f"{_format_leaderboard(stats['top_senders'])}"
                    ),
                },
            ],
        },
    ]


def _build_summary(title, stats, empty_message):
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title},
        }
    ]

    if stats["total_recognitions"] == 0:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": empty_message},
            }
        )
        return blocks

    blocks.extend(
        [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": _format_summary_intro(stats)},
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "*💌 감사를 전한 분들*\n"
                            f"{_format_participants(stats['top_senders'])}"
                        ),
                    },
                    {
                        "type": "mrkdwn",
                        "text": (
                            "*🎉 감사를 받은 분들*\n"
                            f"{_format_participants(stats['top_receivers'])}"
                        ),
                    },
                ],
            },
        ]
    )
    return blocks


def _format_summary_intro(stats):
    unit_count = stats.get("total_unit_count", stats["total_recognitions"])
    return (
        f"이번 주 팀에서 {RECOGNITION_UNIT} *{_format_count(unit_count)}*이 오갔어요 "
        f"{RECOGNITION_EMOJI}\n"
        f"{stats['participant_count']}명이 감사를 주고받았습니다."
    )


def _format_participants(rows):
    if not rows:
        return "기록 없음"

    return " ".join(f"<@{row['user_id']}>" for row in rows)


def _format_leaderboard(rows):
    if not rows:
        return "기록 없음"

    return "\n".join(
        f"{index}. <@{row['user_id']}> — {_format_count(row['unit_count'])}"
        for index, row in enumerate(rows[:5], start=1)
    )


def _format_count(unit_count):
    if unit_count == 1:
        return "한 잔"

    return f"{unit_count}잔"


def _format_date(value):
    return f"{value.month}/{value.day}"
