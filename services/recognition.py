import re
from dataclasses import dataclass

from config import DAILY_LIMIT, RECOGNITION_EMOJI
from db.queries import (
    get_recognition_by_idempotency_key,
    get_sent_today,
    get_total_received,
    insert_recognition,
    lock_daily_limit,
)


INVALID_FORMAT = "invalid_format"
MISSING_MESSAGE = "missing_message"
MULTIPLE_QUANTITY_METHODS = "수량은 이모지 또는 숫자 중 하나만 사용해주세요."
BOT_RECEIVER = "봇에게는 보낼 수 없어요."
VARIATION_SELECTOR_16 = "\ufe0f"
COFFEE_EMOJI = "☕"
COFFEE_ALIAS = ":coffee:"


class ParseError(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class SelfRecognitionError(Exception):
    pass


class LimitError(Exception):
    def __init__(self, remaining, requested):
        self.remaining = remaining
        self.requested = requested
        super().__init__("daily limit exceeded")


@dataclass(frozen=True)
class RecognitionRequest:
    receiver_id: str
    unit_count: int
    message: str


@dataclass(frozen=True)
class RecognitionResult:
    recognition_id: int
    receiver_id: str
    unit_count: int
    message: str
    remaining: int
    total_received: int
    is_duplicate: bool = False


MENTION_RE = re.compile(r"^\s*<@([A-Z0-9]+)(?:\|[^>]+)?>\s*(.*)$")


def split_leading_emoji_count(text):
    rest = (text or "").strip()
    if not RECOGNITION_EMOJI:
        return 0, rest

    count = 0
    while True:
        if rest.startswith(RECOGNITION_EMOJI):
            rest = rest[len(RECOGNITION_EMOJI):]
            if rest.startswith(VARIATION_SELECTOR_16):
                rest = rest[len(VARIATION_SELECTOR_16):]
        elif RECOGNITION_EMOJI == COFFEE_EMOJI and rest.startswith(COFFEE_ALIAS):
            rest = rest[len(COFFEE_ALIAS):]
        else:
            break
        count += 1

    return count, rest.strip()


def parse_thanks_text(text, sender_id):
    emoji_count, text_without_emoji_count = split_leading_emoji_count(text)
    match = MENTION_RE.match(text_without_emoji_count)
    if not match:
        raise ParseError(INVALID_FORMAT)

    receiver_id = match.group(1)
    if receiver_id == sender_id:
        raise SelfRecognitionError()

    rest_emoji_count, rest = split_leading_emoji_count(match.group(2))
    emoji_count += rest_emoji_count
    if not rest:
        raise ParseError(MISSING_MESSAGE)

    parts = rest.split(maxsplit=1)
    if parts[0].isdigit():
        if emoji_count:
            raise ParseError(MULTIPLE_QUANTITY_METHODS)
        unit_count = int(parts[0])
        if unit_count <= 0:
            raise ParseError(INVALID_FORMAT)
        if len(parts) == 1 or not parts[1].strip():
            raise ParseError(MISSING_MESSAGE)
        message = parts[1].strip()
    elif emoji_count:
        unit_count = emoji_count
        message = rest
    else:
        unit_count = 1
        message = rest

    return RecognitionRequest(
        receiver_id=receiver_id,
        unit_count=unit_count,
        message=message,
    )


parse_thanks = parse_thanks_text


def create_recognition(conn, sender_id, request, source_channel_id, idempotency_key):
    existing = get_recognition_by_idempotency_key(conn, idempotency_key)
    if existing:
        return _build_duplicate_result(conn, sender_id, existing)

    lock_daily_limit(conn, sender_id)
    existing = get_recognition_by_idempotency_key(conn, idempotency_key)
    if existing:
        return _build_duplicate_result(conn, sender_id, existing)

    sent_today = get_sent_today(conn, sender_id)
    remaining = max(DAILY_LIMIT - sent_today, 0)
    if request.unit_count > remaining:
        raise LimitError(remaining=remaining, requested=request.unit_count)

    recognition_id = insert_recognition(
        conn=conn,
        sender_id=sender_id,
        receiver_id=request.receiver_id,
        message=request.message,
        unit_count=request.unit_count,
        source_channel_id=source_channel_id,
        idempotency_key=idempotency_key,
    )
    if recognition_id is None:
        existing = get_recognition_by_idempotency_key(conn, idempotency_key)
        return _build_duplicate_result(conn, sender_id, existing)

    total_received = get_total_received(conn, request.receiver_id)

    return RecognitionResult(
        recognition_id=recognition_id,
        receiver_id=request.receiver_id,
        unit_count=request.unit_count,
        message=request.message,
        remaining=remaining - request.unit_count,
        total_received=total_received,
    )


def _build_duplicate_result(conn, sender_id, existing):
    sent_today = get_sent_today(conn, sender_id)
    total_received = get_total_received(conn, existing["receiver_id"])
    return RecognitionResult(
        recognition_id=existing["id"],
        receiver_id=existing["receiver_id"],
        unit_count=existing["unit_count"],
        message=existing["message"],
        remaining=max(DAILY_LIMIT - sent_today, 0),
        total_received=total_received,
        is_duplicate=True,
    )
