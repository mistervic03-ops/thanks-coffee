# OPERATIONS.md

## 1. config 변경 방법

환경변수 변경 후 프로세스를 재시작한다.

## 2. 스케줄 변경

PoC 단계의 기본 운영은 Slack에서 `/mocha summary weekly` 또는 `/mocha summary monthly`를 수동 실행하는 방식이다.

`SCHEDULER_ENABLED=true`이면 주간/월간 요약과 실패한 feed 게시 재시도 스케줄이 자동 실행된다. 자동 스케줄은 `scheduler.py`에서 관리한다.

- 주간 요약: 매주 월요일 09:00 KST
- 월간 요약: 매월 1일 09:00 KST
- 실패한 feed 게시 재시도: 10분마다
- timezone은 `Asia/Seoul`로 고정한다.

Spark PoC에서는 `SCHEDULER_ENABLED=false`로 시작하고, 자동 요약 게시나 10분 간격 feed 재시도가 필요해지면 `true`로 바꾼 뒤 프로세스를 재시작한다. 스케줄 시간을 바꾸려면 `scheduler.py`의 `add_job` 설정을 수정하고 프로세스를 재시작한다.

자동 주간/월간 요약은 PostgreSQL advisory lock으로 보호된다. `SCHEDULER_ENABLED=true`인 프로세스가 2개 이상 떠 있어도 lock을 획득한 프로세스 하나만 게시하고, 나머지는 조용히 skip한다.

## 3. 수동 요약 게시

Slack에서 `ADMIN_USER_IDS`에 포함된 운영자 또는 Slack workspace Admin/Owner가 직접 요약을 게시할 수 있다. workspace Admin/Owner 목록은 앱 시작 시 한 번 조회해 캐싱한다.

- `/mocha` 또는 `/mocha help`: 운영자에게 사용 가능한 관리자 명령어를 보여준다. 운영자가 아니면 관리자 전용임을 안내한다.
- `/mocha summary weekly`: 직전 월요일부터 직전 일요일까지의 요약을 전사 공지 채널에 게시한다. 자동 weekly summary와 같은 기준이며, 실패한 주간 게시를 수동으로 재게시할 때 사용한다.
- `/mocha summary monthly`: 직전 월의 요약을 전사 공지 채널에 게시한다. 자동 monthly summary와 같은 기준이다.
- `/mocha summary weekly` 또는 `/mocha summary monthly`가 전사 공지 채널 게시에 성공하면 실행한 운영자에게 관리자용 상세 현황이 ephemeral message로 추가 전송된다.
- `/mocha summary weekly preview`: 직전 주 요약을 전사 공지 채널에 게시하지 않고 실행한 운영자에게만 보여준다.
- `/mocha summary monthly preview`: 직전 월 요약을 전사 공지 채널에 게시하지 않고 실행한 운영자에게만 보여준다.
- `/mocha summary this-month preview`: 이번 달 1일부터 현재 날짜까지의 요약을 전사 공지 채널에 게시하지 않고 실행한 운영자에게만 보여준다. 테스트/운영 확인용이며 feed 게시 기능은 없다.
- `/mocha pin`: 전사 공지 채널에 모카 소개 메시지를 게시하고 pin한다. Slack 앱에 `pins:write` scope가 필요하다. 게시 실패는 `pin_post_failed`, pin 실패는 `pin_failed` 로그로 구분된다.
- `/mocha delete {recognition_id}`: 잘못 입력된 단일 recognition을 삭제한다. 전사 공지 채널 feed 메시지 하단의 `#123` 형태가 recognition ID다. DB에 `feed_channel_id`와 `feed_message_ts`가 저장된 feed 메시지가 있으면 함께 삭제를 시도한다. feed 삭제 실패 시에도 DB 삭제는 유지되며 앱 로그에 `feed_delete_failed`가 남는다.

Slack command를 쓰기 어려운 상황에서는 Python shell에서 `scheduler.run_weekly_summary(client)` 또는 `scheduler.run_monthly_summary(client)`를 직접 호출해 같은 경로를 실행한다. 자동 summary 경로는 게시 성공 후 관리자 전체에게 상세 현황 DM도 보낸다.

## 4. 테스트 운영

반복 테스트가 필요하면 dev/test 환경에서 `DAILY_LIMIT`를 크게 둘 수 있다. 실제 운영에서는 팀 정책이 명확히 보이도록 낮고 이해하기 쉬운 값으로 유지한다.

테스트 데이터 초기화는 Slack command로 제공하지 않는다. dev/test DB를 초기화해야 할 때만 아래 SQL을 직접 실행한다.

**주의: 운영 DB에서 실행하지 않는다. 이 SQL은 `recognition` 테이블 데이터를 삭제한다.**

```sql
TRUNCATE TABLE recognition RESTART IDENTITY;
```

## 5. 장애 시 확인 순서

Slack 토큰, DB 연결, 앱 로그, Slack command 동작 여부 순서로 확인한다. `HEALTH_CHECK_ENABLED=true`이면 health check도 함께 확인한다.

`HEALTH_CHECK_ENABLED=false`이면 HTTP health check 서버가 실행되지 않으므로, `/thanks status` 같은 Slack command 응답과 앱 로그를 기준으로 확인한다.

`HEALTH_CHECK_ENABLED=true`이면 `/health`는 프로세스 생존 확인, `/ready`는 PostgreSQL 연결 확인에 사용한다. 기본 포트는 `HEALTH_CHECK_PORT=8000`이다. Spark에서는 기존 서비스와 birthday-bot 포트를 피하기 위해 `HEALTH_CHECK_PORT=8020`을 사용한다. systemd 배포 후에는 `/ready`가 200을 반환하는지 확인한다.

설정 문제를 의심할 때는 아래를 먼저 확인한다.

- `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `DATABASE_URL`이 설정되어 있는지
- `FEED_ENABLED=true`이면 `ANNOUNCEMENT_CHANNEL_ID`가 설정되어 있고, 봇이 전사 공지 채널에 초대되어 있는지
- `/mocha`를 사용할 운영자가 `ADMIN_USER_IDS`에 포함되어 있거나 Slack workspace Admin/Owner인지
- 자동 요약을 기대한다면 `SCHEDULER_ENABLED=true`인지
- HTTP health check를 기대한다면 `HEALTH_CHECK_ENABLED=true`인지
- Spark에서 health check를 켠다면 `HEALTH_CHECK_PORT=8020`인지
- 환경변수 변경 후 프로세스를 재시작했는지

요약 게시 실패 시에는 아래를 확인한다.

- 앱 로그의 `feed_post_failed`, `slack_rate_limited`, `summary_lock_release_failed`
- `FEED_ENABLED` 값과 `ANNOUNCEMENT_CHANNEL_ID`
- 전사 공지 채널에 봇이 초대되어 있는지
- Slack `chat:write` scope와 bot token
- DB 연결과 `recognition.created_at` 데이터

요약 게시 실패는 로그만 남기며 Bolt 프로세스는 유지된다. `SCHEDULER_ENABLED=true`이면 다음 스케줄 실행도 유지된다.

feed 게시 실패는 `feed_post_status='failed'`로 남고 앱 시작 시 한 번 자동 재시도된다. `SCHEDULER_ENABLED=true`이면 이후 10분마다 자동 재시도된다. 재시도 3회에 도달하면 `feed_post_status='abandoned'`로 바뀌며 더 이상 자동 재시도하지 않는다.

feed 재시도 게시도 메시지 하단에 `#recognition_id`를 표시한다. 단, 현재 retry 성공 경로는 `feed_post_status='posted'`와 `feed_posted_at`만 갱신하며 새 Slack message `ts`를 `feed_message_ts`에 다시 저장하지 않는다.

운영자가 `/mocha delete {recognition_id}`를 실행했는데 feed 메시지 삭제만 실패하면 DB 삭제는 되돌리지 않는다. 필요한 경우 `feed_delete_failed` 로그의 recognition ID와 오류를 확인한 뒤 Slack에서 feed 메시지를 수동 삭제한다. DB에 feed message `ts`가 없는 retry 게시 메시지는 `/mocha delete`가 자동 삭제하지 못하므로 Slack에서 수동 삭제한다.

## 6. 운영자용 조회 쿼리

오늘 특정 유저가 보낸 수량을 확인한다. 하루 기준은 KST다.

```sql
SELECT COALESCE(SUM(unit_count), 0) AS sent_today
FROM recognition
WHERE sender_id = 'U123'
  AND (created_at AT TIME ZONE 'Asia/Seoul')::date =
      (now() AT TIME ZONE 'Asia/Seoul')::date;
```

특정 유저가 받은 누적 수량을 확인한다.

```sql
SELECT COALESCE(SUM(unit_count), 0) AS total_received
FROM recognition
WHERE receiver_id = 'U123';
```

feed 게시 실패나 중간 상태를 확인한다.

```sql
SELECT id, sender_id, receiver_id, feed_post_status, retry_count, feed_channel_id, feed_message_ts, created_at
FROM recognition
WHERE feed_post_status IN ('failed', 'pending', 'abandoned')
ORDER BY created_at DESC;
```

## 7. DB 백업 / 초기화

PostgreSQL 표준 백업과 마이그레이션 재실행 절차를 따른다.
