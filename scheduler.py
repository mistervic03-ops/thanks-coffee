from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from slack_sdk.errors import SlackApiError

from db.queries import get_connection, release_summary_lock, try_summary_lock
from logger import get_logger
from services.feed_retry import retry_failed_feeds
from services.feed import post_summary
from services.stats import (
    build_monthly_summary,
    build_weekly_summary,
    get_previous_month,
    get_previous_week_range,
    load_monthly_stats,
    load_weekly_stats,
)


logger = get_logger(__name__)
KST = ZoneInfo("Asia/Seoul")
_scheduler = None


def start_scheduler(app):
    global _scheduler

    if _scheduler and _scheduler.running:
        return _scheduler

    try:
        scheduler = BackgroundScheduler(timezone=KST)
        scheduler.add_job(
            run_weekly_summary,
            "cron",
            day_of_week="mon",
            hour=9,
            minute=0,
            args=[app.client],
            id="weekly_summary",
            replace_existing=True,
        )
        scheduler.add_job(
            run_monthly_summary,
            "cron",
            day=1,
            hour=9,
            minute=0,
            args=[app.client],
            id="monthly_summary",
            replace_existing=True,
        )
        scheduler.add_job(
            retry_failed_feeds,
            "interval",
            minutes=10,
            args=[app],
            id="feed_retry",
            replace_existing=True,
        )
        scheduler.start()
    except Exception:
        return None

    _scheduler = scheduler
    return scheduler


def run_weekly_summary(client):
    _run_locked_summary(client, "weekly", _post_weekly_summary)


def run_monthly_summary(client):
    _run_locked_summary(client, "monthly", _post_monthly_summary)


def _run_locked_summary(client, summary_type, post_summary_func):
    conn = None
    lock_acquired = False
    try:
        conn = get_connection()
        lock_acquired = try_summary_lock(conn, summary_type)
        if not lock_acquired:
            return

        post_summary_func(conn, client)
        logger.info("", extra={"event": "summary_posted", "detail": summary_type})
    except Exception as exc:
        logger.warning("", extra={"event": _feed_failure_event(exc), "detail": _exception_detail(exc)})
    finally:
        if conn and lock_acquired:
            try:
                release_summary_lock(conn, summary_type)
            except Exception:
                logger.warning(
                    "",
                    extra={
                        "event": "summary_lock_release_failed",
                        "detail": summary_type,
                    },
                )
        if conn:
            conn.close()


def _post_weekly_summary(conn, client):
    start_date, end_date = get_previous_week_range()
    stats = load_weekly_stats(conn, start_date, end_date)
    post_summary(client, build_weekly_summary(stats))


def _post_monthly_summary(conn, client):
    year, month = get_previous_month()
    stats = load_monthly_stats(conn, year, month)
    post_summary(client, build_monthly_summary(stats))


def _feed_failure_event(exc):
    if _is_slack_rate_limited(exc):
        return "slack_rate_limited"

    return "feed_post_failed"


def _is_slack_rate_limited(exc):
    if not isinstance(exc, SlackApiError):
        return False

    return exc.response.status_code == 429 or exc.response.get("error") == "ratelimited"


def _exception_detail(exc):
    if isinstance(exc, SlackApiError):
        return exc.response.get("error") or str(exc)

    return str(exc)
