# ARCHITECTURE.md

## 1. 전체 구조

Slack Bolt, FastAPI health check, PostgreSQL을 단일 프로세스에서 실행한다.

## 2. Slash command 처리 흐름

`handlers/thanks.py`가 `/thanks` command를 받으면 `ack()`를 즉시 호출한 뒤 service layer에 처리를 위임한다.

처리 순서:

1. `services/recognition.py`에서 command text를 파싱한다.
2. sender의 daily limit을 확인한다.
3. `recognition` 테이블에 감사 기록을 저장하고 commit한다.
4. `services/feed.py`에서 feed 채널에 게시한다.
5. feed message `ts`가 있으면 DB에 사후 업데이트한다.
6. sender에게 ephemeral 성공 또는 에러 메시지를 보낸다.

feed 게시 실패 시에도 이미 저장된 recognition 기록은 남는다.

## 3. Service layer 역할

`services/`는 recognition 저장, feed 게시, 통계 생성을 담당한다.

## 4. DB 스키마

`recognition` 테이블에 감사 기록과 feed 게시 메타데이터를 저장한다.

## 5. Daily limit 계산 방식

- `recognition.unit_count` 합산 기준으로 계산한다.
- 별도 daily limit 테이블은 두지 않는다.
- sender별로 오늘 보낸 `unit_count` 합계를 조회한다.
- **KST (UTC+9) 기준으로 하루를 계산한다.**
- 요청 `unit_count`가 남은 수량을 초과하면 저장하지 않고 ephemeral 에러를 보낸다.

## 6. Feed posting 방식

`services/feed.py`가 Slack feed 채널 게시를 전담한다.

- feed 채널은 `FEED_CHANNEL_ID`를 사용한다.
- feed 메시지의 이모지와 단위 명칭은 `RECOGNITION_EMOJI`, `RECOGNITION_UNIT`을 사용한다.
- `FEED_ENABLED=false`이면 feed 채널에는 게시하지 않고 recognition 저장만 수행한다.
- feed 게시에 성공하면 Slack message `ts`를 `recognition.feed_message_ts`에 저장한다.

## 7. Scheduler 동작 방식

APScheduler로 주간/월간 요약 게시를 예약한다.
