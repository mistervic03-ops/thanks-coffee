import json
import logging
import sys
from datetime import datetime

from config import LOG_LEVEL


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage() or record.name),
        }

        user_id = getattr(record, "user_id", None)
        if user_id:
            payload["user_id"] = user_id

        detail = getattr(record, "detail", None)
        if detail:
            payload["detail"] = str(detail)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(_log_level(LOG_LEVEL))

    for logger_name in ("slack_sdk", "slack_bolt"):
        external_logger = logging.getLogger(logger_name)
        external_logger.handlers = [logging.NullHandler()]
        external_logger.propagate = False


def get_logger(name=None):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def _log_level(value):
    return logging._nameToLevel.get((value or "INFO").upper(), logging.INFO)
