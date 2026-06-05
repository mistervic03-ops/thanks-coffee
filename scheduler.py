import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from db.queries import get_connection
from services.feed import post_summary
from services.stats import (
    build_monthly_summary,
    build_weekly_summary,
    get_previous_month,
    get_previous_week_range,
    load_monthly_stats,
    load_weekly_stats,
)


logger = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
_scheduler = None


def start_scheduler(client):
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
            args=[client],
            id="weekly_summary",
            replace_existing=True,
        )
        scheduler.add_job(
            run_monthly_summary,
            "cron",
            day=1,
            hour=9,
            minute=0,
            args=[client],
            id="monthly_summary",
            replace_existing=True,
        )
        scheduler.start()
    except Exception:
        logger.exception("Failed to start summary scheduler")
        return None

    _scheduler = scheduler
    logger.info(
        "Summary scheduler started: %s",
        ", ".join(job.id for job in scheduler.get_jobs()),
    )
    return scheduler


def run_weekly_summary(client):
    conn = None
    try:
        conn = get_connection()
        start_date, end_date = get_previous_week_range()
        stats = load_weekly_stats(conn, start_date, end_date)
        post_summary(client, build_weekly_summary(stats))
        logger.info("Weekly summary posted")
    except Exception:
        logger.exception("Failed to post weekly summary")
    finally:
        if conn:
            conn.close()


def run_monthly_summary(client):
    conn = None
    try:
        conn = get_connection()
        year, month = get_previous_month()
        stats = load_monthly_stats(conn, year, month)
        post_summary(client, build_monthly_summary(stats))
        logger.info("Monthly summary posted")
    except Exception:
        logger.exception("Failed to post monthly summary")
    finally:
        if conn:
            conn.close()
