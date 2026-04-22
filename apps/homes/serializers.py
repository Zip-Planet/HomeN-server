import re

from rest_framework import serializers

from apps.homes.models import Chore, ChoreCategory, Home, HomeChore, HomeMember, HomeImageType, Reward, StarterPack


class HomeCreateSerializer(serializers.Serializer):
    """집 생성 입력 시리얼라이저."""

    class ChoreInputSerializer(serializers.Serializer):
        category = serializers.ChoiceField(choices=ChoreCategory.choices)
        name = serializers.CharField(max_length=20)
        description = serializers.CharField(max_length=20, default="", allow_blank=True)
        repeat_days = serializers.ListField(
            child=serializers.ChoiceField(choices=Chore.Weekday.choices),
            default=list,
        )
        difficulty = serializers.ChoiceField(choices=Chore.Difficulty.choices)

    class RewardInputSerializer(serializers.Serializer):
        name = serializers.CharField(max_length=50)
        goal_point = serializers.IntegerField(min_value=1)

    name = serializers.CharField(max_length=10)
    image_id = serializers.ChoiceField(choices=HomeImageType.choices)
    chores = ChoreInputSerializer(many=True, default=list)
    rewards = RewardInputSerializer(many=True, default=list)

    def validate_name(self, value: str) -> str:
        """집 이름 규칙: 한글·영문·숫자·공백만 허용, 공백 단독 불가."""
        if not re.match(r"^[가-힣a-zA-Z0-9 ]+$", value):
            raise serializers.ValidationError("집 이름은 한글, 영문, 숫자, 띄어쓰기만 사용할 수 있습니다.")
        if value.strip() == "":
            raise serializers.ValidationError("집 이름을 입력해 주세요.")
        return value


class HomeOutputSerializer(serializers.ModelSerializer):
    """집 출력 시리얼라이저."""

    class Meta:
        model = Home
        fields = ["id", "name", "image", "invite_code", "status", "created_at"]


class StarterPackSerializer(serializers.ModelSerializer):
    """스타터팩 출력 시리얼라이저."""

    class Meta:
        model = StarterPack
        fields = ["id", "name", "description"]


class ChoreOutputSerializer(serializers.ModelSerializer):
    """집안일 출력 시리얼라이저."""

    difficulty_label = serializers.CharField(source="get_difficulty_display", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Chore
        fields = ["id", "category", "category_label", "name", "description", "repeat_days", "difficulty", "difficulty_label"]


class RewardOutputSerializer(serializers.ModelSerializer):
    """리워드 출력 시리얼라이저."""

    class Meta:
        model = Reward
        fields = ["id", "name", "goal_point"]


class HomeMemberSerializer(serializers.ModelSerializer):
    """집 구성원 출력 시리얼라이저."""

    name = serializers.CharField(source="user.name")
    profile_image = serializers.IntegerField(source="user.profile_image", allow_null=True)
    role_label = serializers.SerializerMethodField()

    class Meta:
        model = HomeMember
        fields = ["name", "profile_image", "role", "role_label"]

    def get_role_label(self, obj: HomeMember) -> str:
        """역할의 표시 이름을 반환합니다."""
        return obj.get_role_display()


class ImageIdSerializer(serializers.Serializer):
    """이미지 enum ID 목록 응답 시리얼라이저."""

    id = serializers.IntegerField()


class HomeJoinSerializer(serializers.Serializer):
    """집 참여 요청 시리얼라이저."""

    invite_code = serializers.CharField(max_length=6)


class TransferAdminSerializer(serializers.Serializer):
    """관리자 양도 요청 시리얼라이저."""

    user_id = serializers.UUIDField()


class HomeChoreCreateSerializer(serializers.Serializer):
    """집안일 생성 요청 시리얼라이저 (단건 및 복수 생성 공통)."""

    category = serializers.ChoiceField(choices=ChoreCategory.choices)
    name = serializers.CharField(max_length=20)
    description = serializers.CharField(max_length=20, default="", allow_blank=True)
    repeat_days = serializers.ListField(
        child=serializers.ChoiceField(choices=Chore.Weekday.choices),
        default=list,
    )
    difficulty = serializers.ChoiceField(choices=Chore.Difficulty.choices)


class HomeChoreListCreateSerializer(serializers.Serializer):
    """집안일 리스트 생성 요청 시리얼라이저."""

    chores = HomeChoreCreateSerializer(many=True)


class HomeChoreOutputSerializer(serializers.ModelSerializer):
    """집 집안일 출력 시리얼라이저 (memo 포함)."""

    category = serializers.IntegerField(source="chore.category")
    category_label = serializers.CharField(source="chore.get_category_display")
    name = serializers.CharField(source="chore.name")
    description = serializers.CharField(source="chore.description")
    repeat_days = serializers.ListField(source="chore.repeat_days")
    difficulty = serializers.IntegerField(source="chore.difficulty")
    difficulty_label = serializers.CharField(source="chore.get_difficulty_display")

    class Meta:
        model = HomeChore
        fields = ["id", "category", "category_label", "name", "description", "repeat_days", "difficulty", "difficulty_label", "memo"]


class ChoreMemoUpdateSerializer(serializers.Serializer):
    """집안일 메모 수정 요청 시리얼라이저."""

    memo = serializers.CharField(max_length=200, allow_blank=True)


class HomeInviteDetailSerializer(serializers.ModelSerializer):
    """초대코드 조회 출력 시리얼라이저."""

    member_count = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()

    class Meta:
        model = Home
        fields = ["invite_code", "name", "image", "member_count", "created_at", "members"]

    def get_member_count(self, obj: Home) -> int:
        """전체 구성원 수(관리자 포함)를 반환합니다."""
        return obj.members.count()

    def get_members(self, obj: Home) -> list:
        """구성원 목록을 반환합니다."""
        return HomeMemberSerializer(obj.members.all(), many=True).data
