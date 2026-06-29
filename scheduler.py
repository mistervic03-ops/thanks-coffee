import random
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from slack_sdk.errors import SlackApiError

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, ANNOUNCEMENT_CHANNEL_ID
from db.queries import (
    get_connection,
    release_connection,
    release_summary_lock,
    try_summary_lock,
)
from logger import get_logger
from services.admin import notify_admins_with_blocks, notify_cached_admins
from services.feed_retry import retry_failed_feeds
from services.feed import post_summary
from services.stats import (
    build_leaderboard_blocks,
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

FALLBACK_REMINDER_TEMPLATES = [
    (
        "이번 주도 서로의 수고를 놓치지 않는 시간이 되면 좋겠어요. "
        "고마운 동료가 떠올랐다면 `/thanks {mention} 고마웠던 점`으로 마음을 전해보세요."
    ),
    (
        "{name}님과 함께 일하며 고마웠던 순간이 있다면 오늘 짧게 남겨보세요. "
        "`/thanks {mention} 덕분에 힘이 났어요`처럼 자연스럽게 보내면 됩니다."
    ),
    (
        "작은 감사도 팀 분위기를 바꿉니다. 오늘은 {name}님에게 고마웠던 일을 떠올리고 "
        "`/thanks {mention} 고마운 내용`으로 전해보세요."
    ),
    (
        "바쁜 한 주 가운데 누군가의 도움이 있었다면 그냥 지나치지 않아도 좋아요. "
        "`/thanks {mention} 도와줘서 고마워요`로 따뜻하게 남겨보세요."
    ),
    (
        "{name}님이 보여준 좋은 협업이나 배려가 떠오른다면 지금 전해보세요. "
        "`/thanks {mention} 함께해줘서 고마워요`"
    ),
    (
        "이번 주 감사 리마인더입니다. 동료의 수고를 발견했다면 "
        "`/thanks {mention} 고마웠던 순간`으로 짧게 표현해보세요."
    ),
]


def start_scheduler(app, summary_jobs_enabled=True, reminder_enabled=False):
    global _scheduler

    if _scheduler and _scheduler.running:
        return _scheduler

    try:
        scheduler = BackgroundScheduler(timezone=KST)
        if summary_jobs_enabled:
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
        if reminder_enabled:
            scheduler.add_job(
                run_weekly_reminder,
                "cron",
                day_of_week="wed",
                hour=10,
                minute=0,
                args=[app.client],
                id="weekly_reminder",
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


def run_weekly_reminder(client):
    users = get_active_workspace_users(client)
    if not users:
        logger.warning("", extra={"event": "weekly_reminder_no_active_users"})
        return

    user = random.choice(users)
    try:
        text = build_claude_reminder_text(user["name"])
    except Exception as exc:
        logger.warning(
            "",
            extra={"event": "weekly_reminder_claude_failed", "detail": str(exc)},
        )
        notify_cached_admins(
            f"[mocha] 주간 리마인더 Claude API 호출에 실패했습니다: {exc}"
        )
        text = build_fallback_reminder_text(user)

    client.chat_postMessage(channel=ANNOUNCEMENT_CHANNEL_ID, text=text)
    logger.info("", extra={"event": "weekly_reminder_posted", "user_id": user["id"]})


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
            release_connection(conn)


def _post_weekly_summary(conn, client):
    start_date, end_date = get_previous_week_range()
    stats = load_weekly_stats(conn, start_date, end_date)
    if post_summary(client, build_weekly_summary(stats)):
        notify_admins_with_blocks(client, build_leaderboard_blocks(stats))


def _post_monthly_summary(conn, client):
    year, month = get_previous_month()
    stats = load_monthly_stats(conn, year, month)
    if post_summary(client, build_monthly_summary(stats)):
        notify_admins_with_blocks(client, build_leaderboard_blocks(stats))


def get_active_workspace_users(client):
    users = []
    cursor = None
    while True:
        if cursor:
            response = client.users_list(cursor=cursor)
        else:
            response = client.users_list()

        for user in response.get("members", []):
            if is_active_human_user(user):
                users.append(
                    {
                        "id": user["id"],
                        "name": get_user_display_name(user),
                    }
                )

        cursor = response.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return users


def is_active_human_user(user):
    return not (
        user.get("deleted")
        or user.get("is_bot")
        or user.get("id") == "USLACKBOT"
    )


def get_user_display_name(user):
    profile = user.get("profile", {})
    return (
        profile.get("display_name")
        or profile.get("real_name")
        or user.get("real_name")
        or user.get("name")
        or user["id"]
    )


def build_claude_reminder_text(name):
    client = create_anthropic_client()
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=400,
        temperature=0.8,
        system=(
            "너는 Slack 칭찬봇의 따뜻한 한국어 리마인더 문구를 작성한다. "
            "출력은 Slack 채널에 바로 게시할 짧은 한국어 텍스트 하나만 작성한다."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"이름: {name}\n\n"
                    "조건:\n"
                    "- 이름으로 삼행시를 만든다. 가능한 경우 이름 한 글자당 한 문장으로 쓴다.\n"
                    "- 삼행시 각 문장은 동료에 대한 감사, 응원, 협업의 가치를 담는다.\n"
                    "- 유머나 농담 없이 진지하고 따뜻한 톤을 유지한다.\n"
                    "- 직장 동료 간 공개 채널에 올라오는 메시지임을 감안해 누가 봐도 불편하지 않은 내용으로 쓴다.\n"
                    "- 이모지 1~2개를 자연스럽게 포함한다.\n"
                    "- 전체 5~6문장 이내로 간결하게 쓴다.\n"
                    "- /thanks 독려 문구는 '오늘 고마운 동료가 있다면 /thanks @이름 메시지 로 마음을 전해보세요' 같은 구체적인 형태로 쓴다.\n"
                    "- 출력은 Slack에 바로 올라갈 메시지 텍스트만 작성한다. 불필요한 설명, 따옴표, 마크다운 없이 쓴다.\n"
                    "- 이름이 한국어가 아니어도 자연스럽게 처리한다.\n"
                    "- 이름이 영어이거나 삼행시로 만들기 어색한 경우, 억지로 삼행시를 만들지 말고 "
                    "이름 없이 자연스러운 칭찬 독려 메시지로 대체해도 된다."
                ),
            }
        ],
    )
    text = extract_anthropic_text(response)
    if not text:
        raise RuntimeError("empty Claude response")

    return text


def create_anthropic_client():
    from anthropic import Anthropic

    return Anthropic(api_key=ANTHROPIC_API_KEY)


def extract_anthropic_text(response):
    content = getattr(response, "content", None)
    if content is None and isinstance(response, dict):
        content = response.get("content")

    texts = []
    for block in content or []:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            texts.append(text)

    return "\n".join(texts).strip()


def build_fallback_reminder_text(user):
    template = random.choice(FALLBACK_REMINDER_TEMPLATES)
    return template.format(name=user["name"], mention=f"<@{user['id']}>")


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
