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
    CLEANING = 3, "청소"
    KITCHEN = 4, "주방"
    LAUNDRY = 5, "세탁"


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

    # 포인트는 난이도에 1:1 로 고정된 파생 값이다 ("포인트는 난이도에 따라 자동
    # 고정돼요"). 직접 입력을 허용하지 않으므로 DB 컬럼 없이 property 로 노출한다.
    POINT_BY_DIFFICULTY: dict[int, int] = {
        Difficulty.LOW: 40,
        Difficulty.MEDIUM_LOW: 80,
        Difficulty.MEDIUM: 120,
        Difficulty.MEDIUM_HIGH: 160,
        Difficulty.HIGH: 200,
    }

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
    description = models.CharField(max_length=20, blank=True, default="")
    repeat_days = ArrayField(models.IntegerField(choices=Weekday.choices), default=list)
    difficulty = models.IntegerField(choices=Difficulty.choices)

    class Meta:
        db_table = "chores"

    @property
    def point(self) -> int:
        """난이도에 따라 자동 부여되는 포인트 (하40/중하80/중120/중상160/상200)."""
        return self.POINT_BY_DIFFICULTY.get(self.difficulty, 0)

    def __str__(self) -> str:
        return f"chore:{self.pk}:{self.name}"


class HomeChore(models.Model):
    """집에 배정된 집안일 모델.

    메모는 별도 모델(`HomeChoreNote`) 로 1:N 관리한다 (Figma 의 메모 화면이 다중
    작성자 메모 + 수정/삭제를 노출하므로).

    삭제는 soft-delete — 완료 이력이 있는 집안일은 `is_active=False` 로 비활성화해
    리포트/기여도/히스토리 데이터를 보존한다 (이력이 전혀 없으면 물리 삭제).

    Attributes:
        home: 대상 집.
        chore: 배정된 집안일.
        is_active: 활성 여부. False 면 삭제(비활성화)된 집안일.
        created_at: 배정 일시.
    """

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="home_chores")
    chore = models.ForeignKey(Chore, on_delete=models.CASCADE, related_name="home_chores")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "home_chores"
        unique_together = [("home", "chore")]

    def __str__(self) -> str:
        return f"home_chore:{self.pk}"


class HomeChoreNote(models.Model):
    """집안일에 작성자가 남기는 메모 (1:N).

    Figma 의 \"집안일 상세\" 화면이 메모 목록을 다중 작성자/수정·삭제 가능한 형태
    로 노출한다. 본 모델은 그 목록의 단일 row 다.

    Attributes:
        home_chore: 대상 HomeChore.
        author: 메모를 작성한 User.
        content: 메모 본문 (최대 200자).
        created_at / updated_at: 생성·수정 일시.
    """

    home_chore = models.ForeignKey(HomeChore, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="home_chore_notes")
    content = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "home_chore_notes"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"home_chore_note:{self.pk}"


class ChoreCompletion(models.Model):
    """집안일 완료 이력 (집 단위, 날짜별 1건).

    같은 HomeChore 에 대해 같은 날짜 1건만 기록한다 — 누가 먼저 끝냈는지가 그
    날의 완료자(`completed_by`) 로 남고, 그 후 이중 등록은 unique_together 로
    차단된다. 완료자 유저가 탈퇴해도 이력 자체는 보존되어야 하므로 FK 는
    `SET_NULL` 이다.

    Attributes:
        home_chore: 대상 HomeChore.
        completed_by: 완료를 기록한 User (탈퇴 시 NULL).
        date: 완료 기준 날짜 (요일/주 윈도우 매칭에 사용).
        created_at: 기록 일시.
    """

    home_chore = models.ForeignKey(HomeChore, on_delete=models.CASCADE, related_name="completions")
    completed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chore_completions",
    )
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chore_completions"
        unique_together = [("home_chore", "date")]
        indexes = [models.Index(fields=["home_chore", "date"])]

    def __str__(self) -> str:
        return f"chore_completion:{self.pk}"


class WeeklyAssignment(models.Model):
    """분담안 — 한 집의 한 주차에 대한 집안일 배정 묶음.

    상태 전이: proposed → confirmed → expired. 재생성 시 기존 proposed 는
    폐기(물리 삭제)되고 새 proposed 가 생성된다. confirmed/expired 는 불변
    히스토리로 보존한다. (specs/assignments.md 참조)

    생성 시점 스냅샷(`member_uids_snapshot`, `chore_fingerprint`)은 확정 시점에
    현재 상태와 비교해 "생성 이후 집안일/구성원 변경 없음" 확정 조건을 검증한다.

    Attributes:
        home: 대상 집.
        week_start: 적용 주차의 월요일 날짜.
        status: proposed / confirmed / expired.
        generated_at: 분담안 생성(재생성) 시점.
        member_uids_snapshot: 생성 시점 구성원 uid 문자열 목록 (정렬).
        chore_fingerprint: 생성 시점 활성 집안일 지문 (sha256 hex).
        confirmed_at: 확정 시각 (미확정이면 null).
        confirmed_by: 확정한 관리자 (자동 확정이면 null).
    """

    class Status(models.TextChoices):
        PROPOSED = "proposed", "제안됨"
        CONFIRMED = "confirmed", "확정됨"
        EXPIRED = "expired", "만료됨"

    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="weekly_assignments")
    week_start = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROPOSED)
    generated_at = models.DateTimeField()
    member_uids_snapshot = ArrayField(models.CharField(max_length=36), default=list)
    chore_fingerprint = models.CharField(max_length=64)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "weekly_assignments"
        constraints = [
            models.UniqueConstraint(
                fields=["home", "week_start"],
                condition=models.Q(status="proposed"),
                name="uniq_proposed_assignment_per_home_week",
            ),
            models.UniqueConstraint(
                fields=["home", "week_start"],
                condition=models.Q(status="confirmed"),
                name="uniq_confirmed_assignment_per_home_week",
            ),
        ]

    def __str__(self) -> str:
        return f"weekly_assignment:{self.pk}:{self.week_start}:{self.status}"


class AssignmentItem(models.Model):
    """분담안 항목 — 주차별 실행 집안일 한 건 (요일 × 집안일 × 담당자).

    집안일명/카테고리/난이도/포인트는 생성 시점 **스냅샷** — 이후 원본 집안일이
    수정·삭제(비활성화)돼도 확정·만료 분담안의 값은 변하지 않는다 (히스토리 보존).
    완료 여부는 별도 저장하지 않고 `ChoreCompletion(home_chore, date)` 과 조인해
    계산한다 (date = week_start + weekday).

    Attributes:
        assignment: 소속 분담안.
        home_chore: 원본 집안일 링크 (원본이 물리 삭제돼도 항목 유지 — SET_NULL).
        weekday: 실행 요일 (0=월 ~ 6=일).
        assignee: 자동 배정된 담당자 (탈퇴 시 null).
        chore_name / category / difficulty / point: 생성 시점 스냅샷.
    """

    assignment = models.ForeignKey(WeeklyAssignment, on_delete=models.CASCADE, related_name="items")
    home_chore = models.ForeignKey(
        HomeChore,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignment_items",
    )
    weekday = models.IntegerField(choices=Chore.Weekday.choices)
    assignee = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignment_items",
    )
    chore_name = models.CharField(max_length=20)
    category = models.IntegerField(choices=ChoreCategory.choices)
    difficulty = models.IntegerField(choices=Chore.Difficulty.choices)
    point = models.IntegerField()

    class Meta:
        db_table = "assignment_items"
        ordering = ["weekday", "id"]

    def __str__(self) -> str:
        return f"assignment_item:{self.pk}:{self.chore_name}"
