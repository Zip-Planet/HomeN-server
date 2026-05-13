"""ChoreOutputSerializer / HomeChoreOutputSerializer 의 화면용 매핑 검증.

디자인에 노출되는 표현 규칙:
- 난이도 화면 라벨: 1~2='쉬움', 3~4='중간', 5='어려움'.
- 포인트: 난이도에 1:1 고정 (1=40, 2=80, 3=120, 4=160, 5=200).
- 요일 한글 라벨: `Chore.Weekday(d).label` 그대로.
"""

import pytest

from apps.homes.models import Chore
from apps.homes.serializers import ChoreOutputSerializer, HomeChoreOutputSerializer
from apps.homes.tests.factories import ChoreFactory, HomeChoreFactory

pytestmark = pytest.mark.django_db


DIFFICULTY_TO_POINT = {1: 40, 2: 80, 3: 120, 4: 160, 5: 200}
DIFFICULTY_TO_LABEL = {1: "쉬움", 2: "쉬움", 3: "중간", 4: "중간", 5: "어려움"}


@pytest.mark.parametrize("difficulty", [1, 2, 3, 4, 5])
class TestChoreOutputSerializerMapping:
    def test_난이도별_포인트_매핑(self, difficulty: int):
        chore = ChoreFactory(difficulty=difficulty)

        data = ChoreOutputSerializer(chore).data

        assert data["point"] == DIFFICULTY_TO_POINT[difficulty]

    def test_난이도별_3단계_라벨_매핑(self, difficulty: int):
        chore = ChoreFactory(difficulty=difficulty)

        data = ChoreOutputSerializer(chore).data

        assert data["difficulty_label"] == DIFFICULTY_TO_LABEL[difficulty]


class TestChoreOutputSerializerRepeatDays:
    def test_요일_한글_라벨_정렬_유지(self):
        chore = ChoreFactory(repeat_days=[0, 5, 6])  # 월/토/일

        data = ChoreOutputSerializer(chore).data

        assert data["repeat_days"] == [0, 5, 6]
        assert data["repeat_days_label"] == ["월", "토", "일"]

    def test_빈_repeat_days_는_빈_라벨_배열(self):
        chore = ChoreFactory(repeat_days=[])

        data = ChoreOutputSerializer(chore).data

        assert data["repeat_days_label"] == []


@pytest.mark.parametrize("difficulty", [1, 2, 3, 4, 5])
class TestHomeChoreOutputSerializerMapping:
    def test_난이도별_포인트_매핑(self, difficulty: int):
        home_chore = HomeChoreFactory(chore__difficulty=difficulty)

        data = HomeChoreOutputSerializer(home_chore).data

        assert data["point"] == DIFFICULTY_TO_POINT[difficulty]

    def test_난이도별_3단계_라벨_매핑(self, difficulty: int):
        home_chore = HomeChoreFactory(chore__difficulty=difficulty)

        data = HomeChoreOutputSerializer(home_chore).data

        assert data["difficulty_label"] == DIFFICULTY_TO_LABEL[difficulty]


class TestHomeChoreOutputSerializerRepeatDays:
    def test_요일_한글_라벨(self):
        home_chore = HomeChoreFactory(chore__repeat_days=[1, 3])  # 화/목

        data = HomeChoreOutputSerializer(home_chore).data

        assert data["repeat_days"] == [1, 3]
        assert data["repeat_days_label"] == ["화", "목"]

    def test_difficulty_label_은_5단계_한글이_아님(self):
        """기존 `get_difficulty_display` 매핑('하'/'중하'/'중'/'중상'/'상') 이 더는 응답에 노출되지 않아야 한다."""

        home_chore = HomeChoreFactory(chore__difficulty=Chore.Difficulty.MEDIUM_LOW)

        data = HomeChoreOutputSerializer(home_chore).data

        assert data["difficulty_label"] == "쉬움"
        assert data["difficulty_label"] not in {"하", "중하", "중", "중상", "상"}
