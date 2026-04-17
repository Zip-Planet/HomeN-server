from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.users.models import User


class HomeImageType(models.IntegerChoices):
    """집 프로필 이미지 enum.

    프론트엔드에서 값을 받아 해당하는 이미지를 렌더링합니다.
    """

    TYPE_1 = 1, "집 이미지 1"
    TYPE_2 = 2, "집 이미지 2"
    TYPE_3 = 3, "집 이미지 3"
    TYPE_4 = 4, "집 이미지 4"
    TYPE_5 = 5, "집 이미지 5"
    TYPE_6 = 6, "집 이미지 6"
    TYPE_7 = 7, "집 이미지 7"
    TYPE_8 = 8, "집 이미지 8"


class ChoreCategory(models.IntegerChoices):
    """집안일 카테고리 enum."""

    TRASH = 1, "쓰레기"
    BATHROOM = 2, "욕실"
    KITCHEN = 3, "주방"
    LIVING_ROOM = 4, "거실"
    BEDROOM = 5, "침실"
    LAUNDRY = 6, "빨래"
    COOKING = 7, "요리"
    DISHES = 8, "설거지"
    VACUUM = 9, "청소기"
    ETC = 10, "기타"


class Home(models.Model):
    """집 모델.

    Attributes:
        name: 집 이름 (한글·영문·숫자·공백, 최대 10자).
        image: 선택된 집 이미지 enum 값.
        invite_code: 6자리 초대코드 (대문자+숫자).
        status: 생성 상태 (active=활성).
        created_at: 생성 일시.
        updated_at: 최종 수정 일시.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "생성 중"
        ACTIVE = "active", "활성"

    name = models.CharField(max_length=10)
    image = models.IntegerField(choices=HomeImageType.choices)
    invite_code = models.CharField(max_length=6, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "homes"

    def __str__(self) -> str:
        return f"home:{self.pk}:{self.name}"


class HomeMember(models.Model):
    """집 구성원 모델.

    한 유저는 하나의 집에만 속할 수 있습니다 (서비스 레이어에서 강제).
    관리자는 집당 1명, 구성원은 N명입니다.

    Attributes:
        home: 소속 집.
        user: 소속 유저.
        role: 역할 (1=관리자, 2=구성원).
        joined_at: 참여 일시.
    """

    class Role(models.IntegerChoices):
        ADMIN = 1, "관리자"
        MEMBER = 2, "구성원"

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="home_memberships")
    role = models.IntegerField(choices=Role.choices)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "home_members"
        unique_together = [("home", "user")]

    def __str__(self) -> str:
        return f"home_member:{self.pk}"


class StarterPack(models.Model):
    """스타터팩 모델.

    관리자가 사전에 등록한 집안일 프리셋 묶음입니다.

    Attributes:
        name: 스타터팩 이름.
        description: 스타터팩 설명.
    """

    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "starter_packs"

    def __str__(self) -> str:
        return f"starter_pack:{self.pk}:{self.name}"


class Chore(models.Model):
    """집안일 모델.

    starter_pack이 null이면 집 생성 시 직접 등록한 커스텀 집안일입니다.

    Attributes:
        starter_pack: 소속 스타터팩 (null=커스텀).
        category: 집안일 카테고리 enum 값.
        name: 집안일 제목 (최대 20자).
        description: 집안일 설명 (최대 50자).
        repeat_days: 반복 요일 목록 (Weekday enum 정수 배열).
        difficulty: 난이도 (1=하, 2=중하, 3=중, 4=중상, 5=상).
    """

    class Difficulty(models.IntegerChoices):
        LOW = 1, "하"
        MEDIUM_LOW = 2, "중하"
        MEDIUM = 3, "중"
        MEDIUM_HIGH = 4, "중상"
        HIGH = 5, "상"

    class Weekday(models.IntegerChoices):
        MON = 0, "월"
        TUE = 1, "화"
        WED = 2, "수"
        THU = 3, "목"
        FRI = 4, "금"
        SAT = 5, "토"
        SUN = 6, "일"

    starter_pack = models.ForeignKey(
        StarterPack,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chores",
    )
    category = models.IntegerField(choices=ChoreCategory.choices)
    name = models.CharField(max_length=20)
    description = models.CharField(max_length=50, blank=True, default="")
    repeat_days = ArrayField(models.IntegerField(choices=Weekday.choices), default=list)
    difficulty = models.IntegerField(choices=Difficulty.choices)

    class Meta:
        db_table = "chores"

    def __str__(self) -> str:
        return f"chore:{self.pk}:{self.name}"


class HomeChore(models.Model):
    """집에 배정된 집안일 모델.

    Attributes:
        home: 대상 집.
        chore: 배정된 집안일.
        created_at: 배정 일시.
    """

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="home_chores")
    chore = models.ForeignKey(Chore, on_delete=models.CASCADE, related_name="home_chores")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "home_chores"
        unique_together = [("home", "chore")]

    def __str__(self) -> str:
        return f"home_chore:{self.pk}"


class Reward(models.Model):
    """리워드 모델.

    Attributes:
        home: 소속 집.
        name: 리워드 이름.
        goal_point: 목표 포인트.
        created_at: 생성 일시.
        updated_at: 최종 수정 일시.
    """

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="rewards")
    name = models.CharField(max_length=50)
    goal_point = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rewards"

    def __str__(self) -> str:
        return f"reward:{self.pk}:{self.name}"
