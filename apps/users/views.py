from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users import services
from apps.users.serializers import AppleLoginSerializer, KakaoLoginSerializer, TokenOutputSerializer


class KakaoLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = KakaoLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            tokens = services.kakao_login(**serializer.validated_data)
        except services.SocialLoginError as e:
            raise AuthenticationFailed(str(e)) from e

        return Response(TokenOutputSerializer(tokens).data, status=status.HTTP_200_OK)


class AppleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = AppleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            tokens = services.apple_login(**serializer.validated_data)
        except services.SocialLoginError as e:
            raise AuthenticationFailed(str(e)) from e

        return Response(TokenOutputSerializer(tokens).data, status=status.HTTP_200_OK)
