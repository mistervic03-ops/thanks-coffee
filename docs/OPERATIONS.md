# OPERATIONS.md

## 1. config 변경 방법

환경변수 변경 후 프로세스를 재시작한다.

## 2. 스케줄 변경

주간/월간 요약 스케줄은 `scheduler.py`에서 관리한다.

- 주간 요약: 매주 월요일 09:00 KST
- 월간 요약: 매월 1일 09:00 KST
- timezone은 `Asia/Seoul`로 고정한다.

스케줄을 바꾸려면 `scheduler.py`의 `add_job` 설정을 수정하고 프로세스를 재시작한다.

## 3. 수동 요약 게시

Slack에서 운영자가 직접 요약을 게시할 수 있다.

- `/summary weekly`: 직전 월요일부터 직전 일요일까지의 요약을 feed 채널에 게시한다.
- `/summary monthly`: 직전 월의 요약을 feed 채널에 게시한다.

Slack command를 쓰기 어려운 상황에서는 Python shell에서 `scheduler.run_weekly_summary(client)` 또는 `scheduler.run_monthly_summary(client)`를 직접 호출해 같은 경로를 실행한다.

## 4. 장애 시 확인 순서

Slack 토큰, DB 연결, health check, 앱 로그 순서로 확인한다.

요약 게시 실패 시에는 아래를 확인한다.

- 앱 로그의 `Failed to post weekly summary` 또는 `Failed to post monthly summary`
- `FEED_ENABLED` 값과 `FEED_CHANNEL_ID`
- feed 채널에 봇이 초대되어 있는지
- Slack `chat:write` scope와 bot token
- DB 연결과 `recognition.created_at` 데이터

요약 게시 실패는 로그만 남기며 Bolt 프로세스와 다음 스케줄 실행은 유지된다.

## 5. 운영자용 조회 쿼리

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

## 6. DB 백업 / 초기화

PostgreSQL 표준 백업과 마이그레이션 재실행 절차를 따른다.
