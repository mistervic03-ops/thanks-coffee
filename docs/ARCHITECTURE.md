# ARCHITECTURE.md

## 1. 전체 구조

Slack Bolt, FastAPI health check, PostgreSQL을 단일 프로세스에서 실행한다.

## 2. Slash command 처리 흐름

`handlers/thanks.py`가 `/thanks` command를 받으면 `ack()`를 즉시 호출한 뒤 service layer에 처리를 위임한다.

`/thanks status`는 감사 생성 대신 sender의 오늘 남은 수량과 누적 수신량을 ephemeral message로 응답한다.

처리 순서:

1. `services/recognition.py`에서 command text를 파싱한다.
2. handler가 Slack `users.info`로 receiver가 봇 계정인지 확인하고, 봇이면 ephemeral 에러를 응답한다.
3. sender의 daily limit을 확인한다.
4. `recognition` 테이블에 감사 기록을 저장하고 commit한다.
5. `services/feed.py`에서 feed 채널에 게시한다.
6. feed message `ts`가 있으면 DB에 사후 업데이트한다.
7. sender에게 ephemeral 성공 또는 에러 메시지를 보낸다.

feed 게시 실패 시에도 이미 저장된 recognition 기록은 남는다.

파싱 방식:

- 기본 형식은 `/thanks @팀원 메시지`이며 수량을 생략하면 1로 처리한다.
- 숫자 수량은 `/thanks @팀원 3 메시지` 형식으로 받는다.
- 이모지 수량은 `/thanks ☕☕☕ @팀원 메시지` 형식으로 받으며, 실제 이모지는 `RECOGNITION_EMOJI` 설정값을 사용한다.
- 이모지 수량과 숫자 수량을 동시에 사용하면 파싱 에러로 처리한다.
- receiver가 봇 계정인지 확인하는 Slack API 호출은 `client`를 이미 갖고 있는 handler에서 수행해 parser는 Slack 의존성 없이 유지한다.

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

- `app.py`가 프로세스 시작 시 `start_scheduler(bolt_app.client)`를 호출한다.
- 스케줄러는 `BackgroundScheduler`로 실행되며 Bolt Socket Mode 연결과 독립적으로 동작한다.
- timezone은 명시적으로 `Asia/Seoul`을 사용한다.
- 주간 요약은 매주 월요일 09:00 KST에 실행되며, 직전 월요일부터 직전 일요일까지의 recognition을 집계한다.
- 월간 요약은 매월 1일 09:00 KST에 실행되며, 직전 월의 recognition을 집계한다.
- 요약 집계는 `db/queries.py`, 메시지 생성은 `services/stats.py`, feed 채널 게시는 `services/feed.py`가 담당한다.
- 요약 게시 실패나 Slack API 오류는 로그로 남기고 다음 스케줄 실행을 기다린다. 스케줄러 시작 실패도 Bolt 프로세스를 종료시키지 않는다.
