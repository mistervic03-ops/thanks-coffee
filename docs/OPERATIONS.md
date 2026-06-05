# OPERATIONS.md

## 1. config 변경 방법

환경변수 변경 후 프로세스를 재시작한다.

## 2. 스케줄 변경

주간/월간 요약 스케줄은 `scheduler.py`에서 관리한다.

## 3. 장애 시 확인 순서

Slack 토큰, DB 연결, health check, 앱 로그 순서로 확인한다.

## 4. 운영자용 조회 쿼리

운영 조회 쿼리는 추후 `db/queries.py` 또는 문서에 추가한다.

## 5. DB 백업 / 초기화

PostgreSQL 표준 백업과 마이그레이션 재실행 절차를 따른다.
