from drf_spectacular.utils import OpenApiResponse, extend_schema
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
    ProfileImageIdSerializer,
    TokenOutputSerializer,
    UserProfileOutputSerializer,
    UserProfileUpdateSerializer,
)


class KakaoLoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Auth"],
        summary="카카오 소셜 로그인",
        request=KakaoLoginSerializer,
        responses={
            200: TokenOutputSerializer,
            400: OpenApiResponse(description="인증 코드 누락"),
            401: OpenApiResponse(description="카카오 인증 실패"),
        },
    )
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

    @extend_schema(
        tags=["Auth"],
        summary="애플 소셜 로그인",
        request=AppleLoginSerializer,
        responses={
            200: TokenOutputSerializer,
            400: OpenApiResponse(description="인증 코드 누락"),
            401: OpenApiResponse(description="애플 인증 실패"),
        },
    )
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

    @extend_schema(
        tags=["Users"],
        summary="내 프로필 조회",
        responses={200: UserProfileOutputSerializer},
    )
    def get(self, request: Request) -> Response:
        """현재 로그인한 유저의 프로필을 반환합니다."""
        return Response(UserProfileOutputSerializer(request.user).data)

    @extend_schema(
        tags=["Users"],
        summary="내 프로필 수정",
        request=UserProfileUpdateSerializer,
        responses={
            200: UserProfileOutputSerializer,
            400: OpenApiResponse(description="유효성 검사 실패 또는 닉네임 중복"),
        },
    )
    def patch(self, request: Request) -> Response:
        """현재 로그인한 유저의 닉네임과 프로필 이미지를 업데이트합니다."""
        serializer = UserProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = services.update_profile(user=request.user, **serializer.validated_data)
        except services.ProfileUpdateError as e:
            raise ValidationError({"duplicate_nickname": str(e)}) from e

        return Response(UserProfileOutputSerializer(user).data)


class ProfileImageListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Users"],
        summary="프리셋 프로필 이미지 목록 조회",
        responses={200: ProfileImageIdSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """선택 가능한 프로필 이미지 enum 목록을 반환합니다."""
        return Response(selectors.get_profile_image_choices())
