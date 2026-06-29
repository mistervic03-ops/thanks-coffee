import os
from dotenv import load_dotenv

load_dotenv()

# Slack
SLACK_BOT_TOKEN: str = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN: str = os.environ["SLACK_APP_TOKEN"]

# DB
DATABASE_URL: str = os.environ["DATABASE_URL"]
DB_POOL_MIN: int = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX: int = int(os.getenv("DB_POOL_MAX", "5"))


def parse_admin_user_ids(value: str) -> frozenset[str]:
    return frozenset(user_id.strip() for user_id in value.split(",") if user_id.strip())


def parse_enabled_flag(value: str) -> bool:
    return value.lower() == "true"


def validate_feed_config(feed_enabled: bool, announcement_channel_id: str) -> None:
    if feed_enabled and not announcement_channel_id:
        raise RuntimeError("ANNOUNCEMENT_CHANNEL_ID is required when FEED_ENABLED=true")


def validate_reminder_config(
    reminder_enabled: bool,
    announcement_channel_id: str,
    anthropic_api_key: str,
) -> None:
    if not reminder_enabled:
        return

    if not announcement_channel_id:
        raise RuntimeError("ANNOUNCEMENT_CHANNEL_ID is required when REMINDER_ENABLED=true")
    if not anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when REMINDER_ENABLED=true")


# Recognition 정책
DAILY_LIMIT: int = int(os.getenv("DAILY_LIMIT", "5"))
FEED_ENABLED: bool = parse_enabled_flag(os.getenv("FEED_ENABLED", "true"))
ANNOUNCEMENT_CHANNEL_ID: str = os.getenv("ANNOUNCEMENT_CHANNEL_ID", "")
ADMIN_USER_IDS: frozenset[str] = parse_admin_user_ids(os.getenv("ADMIN_USER_IDS", ""))
SCHEDULER_ENABLED: bool = parse_enabled_flag(os.getenv("SCHEDULER_ENABLED", "false"))
REMINDER_ENABLED: bool = parse_enabled_flag(os.getenv("REMINDER_ENABLED", "false"))
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
HEALTH_CHECK_ENABLED: bool = parse_enabled_flag(os.getenv("HEALTH_CHECK_ENABLED", "false"))
HEALTH_CHECK_PORT: int = int(os.getenv("HEALTH_CHECK_PORT", "8000"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

validate_feed_config(FEED_ENABLED, ANNOUNCEMENT_CHANNEL_ID)
validate_reminder_config(REMINDER_ENABLED, ANNOUNCEMENT_CHANNEL_ID, ANTHROPIC_API_KEY)

# 표현 레이어 (코드에 하드코딩 금지, 항상 이 변수 사용)
RECOGNITION_EMOJI: str = os.getenv("RECOGNITION_EMOJI", "☕")
RECOGNITION_UNIT: str = os.getenv("RECOGNITION_UNIT", "커피")
