# OPERATIONS.md

## 1. config 변경 방법

환경변수 변경 후 프로세스를 재시작한다.

## 2. 스케줄 변경

주간/월간 요약 스케줄은 `scheduler.py`에서 관리한다.

## 3. 장애 시 확인 순서

Slack 토큰, DB 연결, health check, 앱 로그 순서로 확인한다.

## 4. 운영자용 조회 쿼리

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

## 5. DB 백업 / 초기화

PostgreSQL 표준 백업과 마이그레이션 재실행 절차를 따른다.
