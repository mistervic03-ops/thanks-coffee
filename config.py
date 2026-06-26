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


def validate_feed_config(feed_enabled: bool, feed_channel_id: str) -> None:
    if feed_enabled and not feed_channel_id:
        raise RuntimeError("FEED_CHANNEL_ID is required when FEED_ENABLED=true")


# Recognition 정책
DAILY_LIMIT: int = int(os.getenv("DAILY_LIMIT", "5"))
FEED_ENABLED: bool = parse_enabled_flag(os.getenv("FEED_ENABLED", "true"))
FEED_CHANNEL_ID: str = os.getenv("FEED_CHANNEL_ID", "")
ADMIN_USER_IDS: frozenset[str] = parse_admin_user_ids(os.getenv("ADMIN_USER_IDS", ""))
SCHEDULER_ENABLED: bool = parse_enabled_flag(os.getenv("SCHEDULER_ENABLED", "false"))
HEALTH_CHECK_ENABLED: bool = parse_enabled_flag(os.getenv("HEALTH_CHECK_ENABLED", "false"))
HEALTH_CHECK_PORT: int = int(os.getenv("HEALTH_CHECK_PORT", "8000"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

validate_feed_config(FEED_ENABLED, FEED_CHANNEL_ID)

# 표현 레이어 (코드에 하드코딩 금지, 항상 이 변수 사용)
RECOGNITION_EMOJI: str = os.getenv("RECOGNITION_EMOJI", "☕")
RECOGNITION_UNIT: str = os.getenv("RECOGNITION_UNIT", "커피")
