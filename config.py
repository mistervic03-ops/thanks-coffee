import os
from dotenv import load_dotenv

load_dotenv()

# Slack
SLACK_BOT_TOKEN: str = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN: str = os.environ["SLACK_APP_TOKEN"]

# DB
DATABASE_URL: str = os.environ["DATABASE_URL"]

# Recognition 정책
DAILY_LIMIT: int = int(os.getenv("DAILY_LIMIT", "5"))
FEED_ENABLED: bool = os.getenv("FEED_ENABLED", "true").lower() == "true"
FEED_CHANNEL_ID: str = os.environ["FEED_CHANNEL_ID"]

# 표현 레이어 (코드에 하드코딩 금지, 항상 이 변수 사용)
RECOGNITION_EMOJI: str = os.getenv("RECOGNITION_EMOJI", "☕")
RECOGNITION_UNIT: str = os.getenv("RECOGNITION_UNIT", "커피")
