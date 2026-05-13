## #️⃣ 연관된 이슈 / Related Issue
<!-- PR merge 시 이슈 자동 close: Closes #N (또는 Fixes/Resolves #N) -->
<!-- 참조만 (close 안 함): Refs #N 또는 Related to #N -->
<!-- 여러 이슈는 줄바꿈으로 분리 — `Closes #1, #2`는 인식되지 않음 -->
<!-- 이슈와 무관한 PR(긴급 typo·문서 수정 등)이면 아래 줄을 삭제하세요 -->

Closes #

## 📝 해결하려는 문제가 무엇인가요?
<!-- 이번 PR에서 작업한 내용을 간략히 설명해주세요(이미지 첨부 가능) -->

*

## 📝 어떻게 해결했나요?
<!-- 해결 과정을 상세하게 설명해주세요. -->

*

## Attachment

<!-- 이번 PR 의 동작 이해를 돕기 위한 GIF / 스크린샷 첨부 -->
<!-- 리뷰어의 이해를 돕기 위한 모듈/클래스 설계에 대한 Diagram 포함 -->

## 📝 PR 유형 / PR Type

What kind of change does this PR introduce?

<!-- x 박스로 표기 / Please check the one that applies to this PR using "x". -->

- [ ] 🐞 Bugfix
- [ ] ✨ Feature
- [ ] 📝 Code style update (formatting, local variables)
- [ ] 🔄 Refactoring (no functional changes, no api changes)
- [ ] 🚀 Build related changes
- [ ] 📜 CI related changes
- [ ] 📰 Documentation content changes
- [ ] 🛣️ Other... Please describe:

## 🗃️ DB 마이그레이션 체크리스트 (DB 변경이 포함된 PR 만)
<!-- apps/**/migrations/, apps/**/models.py 변경이 있을 때만 채우세요 -->
<!-- 상세 가이드: docs/migrations.md -->

- [ ] `python manage.py makemigrations` 결과가 단일 논리 변경 (multi-change 면 별도 마이그레이션으로 분리됨)
- [ ] 마이그레이션 파일명이 자동 생성 규칙 (`NNNN_<short>.py`) 을 따르며 시퀀스가 끊기지 않음
- [ ] `python manage.py migrate` / `migrate <app> <prev>` 사이클이 로컬에서 통과 (rollback 안전)
- [ ] 데이터 마이그레이션(`RunPython`) 은 스키마 마이그레이션과 별도 파일로 분리
- [ ] 추가된 `UniqueConstraint` / `Index` 에 명시적 `name=` 부여
- [ ] CI workflow `tests` 통과 (자동 실행됨)

## 📝 테스트 결과 / Test Result

### 단위 테스트 / UnitTest

- [ ] 통과 여부

<!-- 특별히 추가 설명이 필요하다면 적어주세요 -->

### 통합 테스트 / Integration Test

- [ ] 통과 여부

<!-- 특별히 추가 설명이 필요하다면 적어주세요 -->

### 부하 테스트 / Stress Test

- 부하테스트 결과 ( RPS ) : {수치 입력}/s

<!-- 특별히 추가 설명이 필요하다면 적어주세요 -->

### 코드 커버리지 / Test Code Coverage

- 코드 커버리지 : {수치} %

<!-- 특별히 추가 설명이 필요하다면 적어주세요 -->

## 💬 리뷰 요구사항(선택)

<!-- 리뷰어가 특별히 봐주었으면 하는 부분이 있다면 작성해주세요 -->
<!-- ex) 메서드 XXX 의 이름을 더 잘 짓고 싶은데 혹시 좋은 명칭이 있을까요? -->
