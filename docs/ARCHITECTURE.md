# ARCHITECTURE.md

## 1. 전체 구조

기본 실행 경로는 Slack Bolt Socket Mode와 PostgreSQL 중심이다. FastAPI health check는 optional component이며, `HEALTH_CHECK_ENABLED=true`일 때만 같은 프로세스 안에서 HTTP 서버를 함께 실행한다. health check 서버 포트는 `HEALTH_CHECK_PORT`로 설정하며 기본값은 `8000`이다.

## 2. Slash command 처리 흐름

`handlers/thanks.py`가 `/thanks` command를 받으면 `ack()`를 즉시 호출한 뒤 service layer에 처리를 위임한다.

`/thanks` 또는 `/thanks help`는 DB나 service layer를 호출하지 않고 일반 사용자용 도움말을 ephemeral message로 응답한다. 일반 help는 `/thanks` 중심의 감사 메시지 예시, 수량 지정 예시, App Home 안내를 보여주며 조회성 보조 명령어는 노출하지 않는다. 파싱할 수 없는 `/thanks` 입력도 raw parser 에러 대신 같은 도움말을 짧은 안내와 함께 보여준다.

`/thanks status`는 감사 생성 대신 sender의 오늘 남은 수량과 누적 수신량을 ephemeral message로 응답한다.

`/thanks received`는 감사 생성 대신 현재 사용자가 최근 받은 감사 기록 10건을 ephemeral message로 응답한다. sender 표시 이름은 Slack `users.info`로 가능한 경우에만 가져오며, 실패하면 mention으로 표시한다.

`/thanks status`와 `/thanks received`는 직접 입력 가능한 보조 조회 명령어로 유지하지만 PoC 일반 사용자 안내에서는 숨긴다.

처리 순서:

1. 도움말, status, received 요청이면 해당 ephemeral message로 바로 응답한다.
2. `services/recognition.py`에서 command text를 파싱한다.
3. handler가 Slack `users.info`로 receiver가 봇 계정인지 확인하고, 봇이면 ephemeral 에러를 응답한다.
4. Slack 요청에서 추출한 idempotency key로 중복 요청인지 먼저 확인한다.
5. 중복이 아니면 sender의 daily limit을 확인한다.
6. `recognition` 테이블에 감사 기록을 저장하고 commit한다.
7. 중복 요청이 아니면 `services/feed.py`에서 feed 채널에 게시한다.
8. feed 게시 결과를 `feed_post_status`와 feed message `ts`로 DB에 사후 업데이트한다.
9. sender에게 ephemeral 성공 또는 에러 메시지를 보낸다.

feed 게시 실패 시에도 이미 저장된 recognition 기록은 남는다.
같은 idempotency key가 다시 들어오면 새 recognition을 만들지 않고 기존 결과를 반환하므로 daily limit도 추가 차감하지 않는다.

Idempotency key 후보는 Socket Mode envelope id, Slack request id, `trigger_id`, `response_url` 순서로 사용한다. 현재 Bolt `SocketModeHandler` 실행 경로에서는 envelope id가 command body에 직접 전달되지 않으므로, 실제 Spark PoC에서는 Slack slash command payload의 `trigger_id` 또는 `response_url`이 주 fallback이 된다. 이 값들도 없으면 false duplicate를 피하기 위해 요청을 저장하지 않고 ephemeral 에러를 응답한다.

파싱 방식:

- 기본 형식은 `/thanks @팀원 메시지`이며 수량을 생략하면 1로 처리한다.
- 숫자 수량은 `/thanks @팀원 3 메시지` 형식으로 받는다.
- 이모지 수량은 `/thanks ☕☕☕ @팀원 메시지` 또는 `/thanks @팀원 ☕☕☕ 메시지` 형식으로 받으며, 실제 이모지는 `RECOGNITION_EMOJI` 설정값을 사용한다.
- 이모지 수량과 숫자 수량을 동시에 사용하면 파싱 에러로 처리한다.
- 사용자가 보는 입력은 `@팀원`이지만, 앱 내부 parser는 Slack이 변환한 `<@USER_ID>` payload를 처리한다. 따라서 Slack manifest의 slash command `should_escape`는 `true`여야 한다.
- receiver가 봇 계정인지 확인하는 Slack API 호출은 `client`를 이미 갖고 있는 handler에서 수행해 parser는 Slack 의존성 없이 유지한다.

## 3. Service layer 역할

`services/`는 recognition 저장, feed 게시, 통계 생성을 담당한다.

## 4. App Home 처리 흐름

`handlers/home.py`가 Slack `app_home_opened` event를 받으면 현재 사용자의 Home tab을 `views_publish`로 갱신한다.

Home tab은 읽기 전용이며 다음 정보만 보여준다.

- 오늘 보낼 수 있는 남은 수량
- 최근 받은 감사 메시지
- 최근 보낸 감사 메시지
- 핵심 `/thanks` 사용 예시

App Home은 `/thanks status`의 `get_sent_today`, `/thanks received`의 `get_recent_received_recognitions`, 최근 보낸 감사 조회용 `get_recent_sent_recognitions` query를 사용한다. leaderboard, badge, streak, reward, ranking 섹션은 만들지 않는다.

## 5. DB 스키마

`recognition` 테이블에 감사 기록과 feed 게시 메타데이터를 저장한다.

- `idempotency_key`: Slack retry나 중복 delivery를 같은 요청으로 식별하기 위한 key다. nullable이지만 새 `/thanks` 요청은 항상 값을 넣는다.
- `feed_post_status`: `pending`, `posted`, `failed`, `skipped` 중 하나로 feed 게시 상태를 추적한다.
- `feed_posted_at`: feed 게시 성공 시각이다.

## 6. Daily limit 계산 방식

- `recognition.unit_count` 합산 기준으로 계산한다.
- 별도 daily limit 테이블은 두지 않는다.
- sender별로 오늘 보낸 `unit_count` 합계를 조회한다.
- **KST (UTC+9) 기준으로 하루를 계산한다.**
- daily limit 확인과 insert 사이에는 sender/KST-day 단위 transaction advisory lock을 잡아 같은 사용자의 같은 날짜 요청을 직렬화한다.
- 이 lock은 새 counter table 없이 PoC 범위에서 limit race를 줄이기 위한 최소 보강이다.
- 요청 `unit_count`가 남은 수량을 초과하면 저장하지 않고 ephemeral 에러를 보낸다.

## 7. Feed posting 방식

`services/feed.py`가 Slack feed 채널 게시를 전담한다.

- feed 채널은 `FEED_CHANNEL_ID`를 사용한다.
- feed 메시지의 이모지와 단위 명칭은 `RECOGNITION_EMOJI`, `RECOGNITION_UNIT`을 사용한다.
- `FEED_ENABLED=false`이면 feed 채널에는 게시하지 않고 recognition 저장만 수행한다.
- feed 게시에 성공하면 Slack message `ts`를 `recognition.feed_message_ts`에 저장하고 `feed_post_status`를 `posted`로 바꾼다.
- feed 게시 실패는 `failed`, feed 비활성화는 `skipped`로 기록한다.

## 8. Scheduler 동작 방식

Scheduler는 optional component다. `SCHEDULER_ENABLED=true`일 때만 APScheduler로 주간/월간 요약 게시를 예약한다. Scheduler가 꺼져 있어도 slash command 기반 `/summary weekly`, `/summary monthly` 흐름은 유지된다.

- `app.py`가 프로세스 시작 시 `SCHEDULER_ENABLED`를 확인하고, true이면 `start_scheduler(bolt_app.client)`를 호출한다.
- 스케줄러는 `BackgroundScheduler`로 실행되며 Bolt Socket Mode 연결과 독립적으로 동작한다.
- timezone은 명시적으로 `Asia/Seoul`을 사용한다.
- 주간 요약은 매주 월요일 09:00 KST에 실행되며, 직전 월요일부터 직전 일요일까지의 recognition을 집계한다.
- 월간 요약은 매월 1일 09:00 KST에 실행되며, 직전 월의 recognition을 집계한다.
- 요약 집계는 `db/queries.py`, 메시지 생성은 `services/stats.py`, feed 채널 게시는 `services/feed.py`가 담당한다.
- 요약 게시 실패나 Slack API 오류는 로그로 남기고 다음 스케줄 실행을 기다린다. 스케줄러 시작 실패도 Bolt 프로세스를 종료시키지 않는다.
- Spark PoC에서는 기본값을 `SCHEDULER_ENABLED=false`로 둔다. 여러 프로세스에서 scheduler를 켜면 summary가 중복 게시될 수 있으며, 이번 PoC 범위에는 summary 분산락을 포함하지 않는다.

## 9. 수동 요약 게시

`/summary weekly`, `/summary monthly`, `/summary weekly preview`, `/summary monthly preview`, `/summary this-month preview`는 `ADMIN_USER_IDS`에 포함된 Slack user만 실행할 수 있다.

- `/summary` 또는 `/summary help`는 권한에 따라 ephemeral 도움말을 보여준다. 운영자는 실행 가능한 summary 명령어를 보고, 운영자가 아닌 사용자는 summary 명령어가 운영자 전용이라는 안내를 받는다.
- 수동 주간 요약은 자동 weekly summary와 동일하게 직전 월요일부터 직전 일요일까지의 recognition을 집계한다.
- 수동 월간 요약은 자동 monthly summary와 동일하게 직전 월의 recognition을 집계한다.
- `preview`가 붙으면 feed 채널에 게시하지 않고 실행한 운영자에게 ephemeral message로만 보여준다.
- `/summary this-month preview`는 이번 달 1일부터 현재 날짜까지 집계하며 feed 게시 기능은 없다.
