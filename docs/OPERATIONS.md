# OPERATIONS.md

## 1. config 변경 방법

환경변수 변경 후 프로세스를 재시작한다.

## 2. 스케줄 변경

PoC 단계의 기본 운영은 Slack에서 `/summary weekly` 또는 `/summary monthly`를 수동 실행하는 방식이다.

`SCHEDULER_ENABLED=true`이면 주간/월간 요약 스케줄이 자동 실행된다. 자동 스케줄은 `scheduler.py`에서 관리한다.

- 주간 요약: 매주 월요일 09:00 KST
- 월간 요약: 매월 1일 09:00 KST
- timezone은 `Asia/Seoul`로 고정한다.

PoC에서는 `SCHEDULER_ENABLED=false`로 시작하고, 자동 게시가 필요해지면 `true`로 바꾼 뒤 프로세스를 재시작한다. 스케줄 시간을 바꾸려면 `scheduler.py`의 `add_job` 설정을 수정하고 프로세스를 재시작한다.

## 3. 수동 요약 게시

Slack에서 `ADMIN_USER_IDS`에 포함된 운영자가 직접 요약을 게시할 수 있다.

- `/summary weekly`: 직전 월요일부터 직전 일요일까지의 요약을 feed 채널에 게시한다. 자동 weekly summary와 같은 기준이며, 실패한 주간 게시를 수동으로 재게시할 때 사용한다.
- `/summary monthly`: 직전 월의 요약을 feed 채널에 게시한다.
- `/summary weekly preview`: 직전 주 요약을 feed 채널에 게시하지 않고 실행한 운영자에게만 보여준다.
- `/summary monthly preview`: 직전 월 요약을 feed 채널에 게시하지 않고 실행한 운영자에게만 보여준다.

Slack command를 쓰기 어려운 상황에서는 Python shell에서 `scheduler.run_weekly_summary(client)` 또는 `scheduler.run_monthly_summary(client)`를 직접 호출해 같은 경로를 실행한다.

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

설정 문제를 의심할 때는 아래를 먼저 확인한다.

- `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `DATABASE_URL`이 설정되어 있는지
- `FEED_ENABLED=true`이면 `FEED_CHANNEL_ID`가 설정되어 있고, 봇이 feed 채널에 초대되어 있는지
- `/summary`를 사용할 운영자가 `ADMIN_USER_IDS`에 포함되어 있는지
- 자동 요약을 기대한다면 `SCHEDULER_ENABLED=true`인지
- HTTP health check를 기대한다면 `HEALTH_CHECK_ENABLED=true`인지
- 환경변수 변경 후 프로세스를 재시작했는지

요약 게시 실패 시에는 아래를 확인한다.

- 앱 로그의 `Failed to post weekly summary` 또는 `Failed to post monthly summary`
- `FEED_ENABLED` 값과 `FEED_CHANNEL_ID`
- feed 채널에 봇이 초대되어 있는지
- Slack `chat:write` scope와 bot token
- DB 연결과 `recognition.created_at` 데이터

요약 게시 실패는 로그만 남기며 Bolt 프로세스는 유지된다. `SCHEDULER_ENABLED=true`이면 다음 스케줄 실행도 유지된다.

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

## 7. DB 백업 / 초기화

PostgreSQL 표준 백업과 마이그레이션 재실행 절차를 따른다.
