from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users import selectors, services
from apps.users.serializers import (
    AppleLoginSerializer,
    KakaoLoginSerializer,
    ProfileImageSerializer,
    TokenOutputSerializer,
    UserProfileOutputSerializer,
    UserProfileUpdateSerializer,
)


class KakaoLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = KakaoLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = services.kakao_login(**serializer.validated_data)
        except services.SocialLoginError as e:
            raise AuthenticationFailed(str(e)) from e

        return Response(TokenOutputSerializer(result).data, status=status.HTTP_200_OK)


class AppleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = AppleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = services.apple_login(**serializer.validated_data)
        except services.SocialLoginError as e:
            raise AuthenticationFailed(str(e)) from e

        return Response(TokenOutputSerializer(result).data, status=status.HTTP_200_OK)


class UserMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """현재 로그인한 유저의 프로필을 반환합니다."""
        return Response(UserProfileOutputSerializer(request.user, context={"request": request}).data)

    def patch(self, request: Request) -> Response:
        """현재 로그인한 유저의 닉네임과 프로필 이미지를 업데이트합니다."""
        serializer = UserProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = services.update_profile(user=request.user, **serializer.validated_data)
        except services.ProfileUpdateError as e:
            raise ValidationError({"duplicate_nickname": str(e)}) from e

        return Response(UserProfileOutputSerializer(user, context={"request": request}).data)


class ProfileImageListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        """사용 가능한 프리셋 프로필 이미지 목록을 반환합니다."""
        images = selectors.get_profile_images()
        return Response(ProfileImageSerializer(images, many=True, context={"request": request}).data)
