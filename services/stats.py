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
        "📊 직전 주 Recognition 요약 "
        f"({_format_date(stats['start_date'])} – {_format_date(stats['end_date'])})"
    )
    return _build_summary(title, stats, "직전 주에는 첫 감사가 없었습니다.")


def build_monthly_summary(stats):
    title = f"📊 {stats['year']}년 {stats['month']}월 Recognition 요약"
    return _build_summary(title, stats, "이번 달에는 첫 감사를 남겨보세요.")


def _build_summary(title, stats, empty_message):
    lines = [
        title,
        "",
        (
            f"{RECOGNITION_EMOJI} 총 감사: {stats['total_recognitions']}건 "
            f"| 참여자: {stats['participant_count']}명"
        ),
        "",
    ]

    if stats["total_recognitions"] == 0:
        lines.append(empty_message)
        return "\n".join(lines)

    lines.extend(
        [
            "많이 받은 분",
            *_format_rankings(stats["top_receivers"]),
            "",
            "많이 보낸 분",
            *_format_rankings(stats["top_senders"]),
        ]
    )
    return "\n".join(lines)


def _format_rankings(rankings):
    if not rankings:
        return ["  기록 없음"]

    return [
        f"  {index}. <@{row['user_id']}> — {_format_unit_count(row['unit_count'])}"
        for index, row in enumerate(rankings, start=1)
    ]


def _format_unit_count(unit_count):
    return f"{unit_count}잔의 {RECOGNITION_UNIT}"


def _format_date(value):
    return f"{value.month}/{value.day}"
