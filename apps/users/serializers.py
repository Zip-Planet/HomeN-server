import re

from rest_framework import serializers

from apps.users.models import UserProfileImage


class KakaoLoginSerializer(serializers.Serializer):
    code = serializers.CharField()


class AppleLoginSerializer(serializers.Serializer):
    code = serializers.CharField()


class TokenOutputSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    is_profile_set = serializers.BooleanField()
    has_home = serializers.BooleanField()


class UserProfileOutputSerializer(serializers.Serializer):
    """유저 프로필 조회 응답 시리얼라이저."""

    uid = serializers.UUIDField()
    name = serializers.CharField()
    profile_image = serializers.IntegerField(allow_null=True)
    is_profile_set = serializers.BooleanField()
    has_home = serializers.BooleanField()


class ProfileImageIdSerializer(serializers.Serializer):
    """프로필 이미지 enum ID 목록 응답 시리얼라이저."""

    id = serializers.IntegerField()


class UserProfileUpdateSerializer(serializers.Serializer):
    """유저 프로필 업데이트 요청 시리얼라이저."""

    name = serializers.CharField(max_length=8)
    profile_image = serializers.ChoiceField(choices=UserProfileImage.choices)

    def validate_name(self, value: str) -> str:
        """닉네임에 특수문자가 포함되지 않았는지 검증합니다."""
        if not re.match(r"^[가-힣a-zA-Z0-9]+$", value):
            raise serializers.ValidationError("닉네임은 한글, 영문, 숫자만 사용할 수 있습니다.")
        return value
