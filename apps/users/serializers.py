import re

from rest_framework import serializers

from apps.users.models import ProfileImage


class KakaoLoginSerializer(serializers.Serializer):
    code = serializers.CharField()


class AppleLoginSerializer(serializers.Serializer):
    code = serializers.CharField()


class TokenOutputSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    is_profile_set = serializers.BooleanField()


class ProfileImageSerializer(serializers.ModelSerializer):
    """프로필 이미지 조회 응답 시리얼라이저."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = ProfileImage
        fields = ["id", "url"]

    def get_url(self, obj: ProfileImage) -> str | None:
        """이미지의 절대 URL을 반환합니다."""
        if not obj.image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class UserProfileOutputSerializer(serializers.Serializer):
    """유저 프로필 조회 응답 시리얼라이저."""

    uid = serializers.UUIDField()
    name = serializers.CharField()
    profile_image = serializers.SerializerMethodField()
    is_profile_set = serializers.BooleanField()

    def get_profile_image(self, obj) -> str | None:
        """선택된 프로필 이미지의 절대 URL을 반환합니다."""
        if not obj.profile_image:
            return None
        request = self.context.get("request")
        from django.core.files.storage import default_storage
        url = default_storage.url(obj.profile_image)
        return request.build_absolute_uri(url) if request else url


class UserProfileUpdateSerializer(serializers.Serializer):
    """유저 프로필 업데이트 요청 시리얼라이저."""

    name = serializers.CharField(max_length=8)
    profile_image = serializers.PrimaryKeyRelatedField(queryset=ProfileImage.objects.all())

    def validate_name(self, value: str) -> str:
        """닉네임에 특수문자가 포함되지 않았는지 검증합니다."""
        if not re.match(r"^[가-힣a-zA-Z0-9]+$", value):
            raise serializers.ValidationError("닉네임은 한글, 영문, 숫자만 사용할 수 있습니다.")
        return value
