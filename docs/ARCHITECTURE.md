# ARCHITECTURE.md

## 1. 전체 구조

Slack Bolt, FastAPI health check, PostgreSQL을 단일 프로세스에서 실행한다.

## 2. Slash command 처리 흐름

`handlers/`가 Slack command를 ack하고 service layer에 처리를 위임한다.

## 3. Service layer 역할

`services/`는 recognition 저장, feed 게시, 통계 생성을 담당한다.

## 4. DB 스키마

`recognition` 테이블에 감사 기록과 feed 게시 메타데이터를 저장한다.

## 5. Daily limit 계산 방식

- unit_count 합산 기준
- **KST (UTC+9) 기준으로 하루를 계산한다**

## 6. Feed posting 방식

`services/feed.py`가 Slack feed 채널 게시를 전담한다.

## 7. Scheduler 동작 방식

APScheduler로 주간/월간 요약 게시를 예약한다.
