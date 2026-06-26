# PRODUCT.md

## 1. 왜 이 봇을 만드는가

모카는 SME 팀이 Slack 안에서 가볍게 감사를 표현하고 기록하기 위한 작은 Slack-native 도구다.

## 2. HeyTaco와의 차이

복잡한 보상 플랫폼이 아니라 감사 문화 중심의 작은 Slack-native 제품이다.

## 3. Recognition First, Reward Second

보상보다 감사 표현과 팀 문화 기록을 우선한다.

## 4. MVP 기능 목록

- `/thanks` slash command 방식으로 감사를 전달하며, 기본 메시지와 수량 지정 예시를 함께 안내한다.
- 수량은 이모지 반복(`☕☕☕`) 또는 숫자로 지정할 수 있다.
- Slack App Home에서 오늘 남은 수량, 나의 받은/보낸 감사 요약, 최근 받은 감사 메시지, 최근 보낸 감사 메시지, 핵심 사용 예시를 읽기 전용으로 확인한다.
- `/thanks status`와 `/thanks received`는 직접 입력 가능한 보조 조회 명령어로 유지하지만 일반 사용자 안내에서는 숨긴다.
- `/thanks help`와 `/mocha help`로 Slack 안에서 사용법을 확인할 수 있다.
- feed 게시, 주간/월간 요약 게시, 관리자용 상세 현황 전달, 기본 집계를 MVP 범위로 둔다.
- 운영자는 잘못 입력된 단일 recognition을 `/mocha delete {recognition_id}`로 삭제할 수 있다.
- 운영자는 `/mocha pin`으로 전사 공지 채널에 봇 소개 메시지를 게시하고 pin할 수 있다.

## 5. V2 후순위 기능

- Message event 기반 recognition 감지 (HeyTaco 방식)
  - 일반 채널 메시지에서 `@팀원 메시지 ☕` 형식을 감지한다.
  - 구현 시 `message.channels` 권한 추가와 팀 공지가 필요하다.
  - service layer는 이미 command와 분리되어 있어 handler 추가만으로 확장 가능하다.
- 상세 리포트, 추가 정책, 고급 자동화는 V2 이후에 검토한다.

## 6. 성공 지표

주간 사용량, 참여자 수, 감사 기록 수를 기준으로 본다.
