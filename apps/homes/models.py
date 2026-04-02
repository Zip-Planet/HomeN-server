from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.users.models import User


class HomeImage(models.Model):
    """프리셋 집 이미지 모델.

    Attributes:
        image: 이미지 파일 (preset_homes/ 하위 저장, 추후 S3).
    """

    image = models.ImageField(upload_to="preset_homes/")

    class Meta:
        db_table = "home_images"

    def __str__(self) -> str:
        return f"home_image:{self.pk}"


class Home(models.Model):
    """집 모델.

    집 생성은 3단계로 진행됩니다. creation_step으로 중간 이탈 시 재진입 단계를 파악합니다.

    Attributes:
        name: 집 이름 (한글·영문·숫자·공백, 최대 10자).
        image: 선택된 프리셋 집 이미지.
        invite_code: 6자리 초대코드 (대문자+숫자).
        creation_step: 마지막 완료 단계 (1=집 프로필, 2=집안일, 3=리워드).
        status: 생성 상태 (draft=생성 중, active=활성).
        created_at: 생성 일시.
        updated_at: 최종 수정 일시.
    """

    class CreationStep(models.IntegerChoices):
        PROFILE = 1, "집 프로필"
        CHORES = 2, "집안일"
        REWARDS = 3, "리워드"

    class Status(models.TextChoices):
        DRAFT = "draft", "생성 중"
        ACTIVE = "active", "활성"

    name = models.CharField(max_length=10)
    image = models.ForeignKey(HomeImage, on_delete=models.PROTECT, related_name="homes")
    invite_code = models.CharField(max_length=6, unique=True)
    creation_step = models.IntegerField(choices=CreationStep.choices, default=CreationStep.PROFILE)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
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
    """집안일 마스터 모델.

    starter_pack이 null이면 추후 구현될 커스텀 집안일입니다.

    Attributes:
        starter_pack: 소속 스타터팩 (null=커스텀).
        name: 집안일 이름.
        image: 집안일 이미지.
        repeat_days: 반복 요일 목록 (Weekday enum 정수 배열).
        difficulty: 난이도 (1=하, 2=중하, 3=중, 4=중상, 5=상).
    """

    class Difficulty(models.IntegerChoices):
        VERY_EASY = 1, "하"
        EASY = 2, "중하"
        MEDIUM = 3, "중"
        HARD = 4, "중상"
        VERY_HARD = 5, "상"

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
    name = models.CharField(max_length=50)
    image = models.ImageField(upload_to="chores/")
    repeat_days = ArrayField(models.IntegerField(choices=Weekday.choices), default=list)
    difficulty = models.IntegerField(choices=Difficulty.choices)

    class Meta:
        db_table = "chores"

    def __str__(self) -> str:
        return f"chore:{self.pk}:{self.name}"

    def get_difficulty_label(self) -> str:
        """난이도를 화면 표시용 레이블로 변환합니다.

        Returns:
            difficulty ≤ 2 → "쉬움", 3 ≤ difficulty ≤ 4 → "중간", 5 → "어려움".
        """
        if self.difficulty <= 2:
            return "쉬움"
        if self.difficulty <= 4:
            return "중간"
        return "어려움"


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
