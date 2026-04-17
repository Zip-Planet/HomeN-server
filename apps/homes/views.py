from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.homes import selectors, services
from apps.homes.serializers import (
    ChoreOutputSerializer,
    HomeCreateSerializer,
    HomeInviteDetailSerializer,
    HomeOutputSerializer,
    StarterPackSerializer,
)


class HomeImageListView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="프리셋 집 이미지 목록 조회",
        responses={200: HomeOutputSerializer},
    )
    def get(self, request: Request) -> Response:
        """선택 가능한 집 이미지 enum 목록을 반환합니다."""
        return Response(selectors.get_home_image_choices())


class HomeCreateView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="집 생성",
        request=HomeCreateSerializer,
        responses={
            201: HomeOutputSerializer,
            400: OpenApiResponse(description="이미 집이 있거나 유효성 검사 실패"),
        },
    )
    def post(self, request: Request) -> Response:
        """집을 생성합니다. 집안일·리워드를 함께 등록하며 빈 리스트는 생성하지 않습니다."""
        serializer = HomeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        try:
            home = services.create_home(
                user=request.user,
                name=data["name"],
                image_id=data["image_id"],
                chores=data["chores"],
                rewards=data["rewards"],
            )
        except services.AlreadyHasHomeError as e:
            raise ValidationError({"already_has_home": str(e)}) from e
        except services.HomeError as e:
            raise ValidationError({"invalid_chore": str(e)}) from e

        return Response(HomeOutputSerializer(home).data, status=status.HTTP_201_CREATED)


class HomeDetailView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="내 집 정보 조회",
        responses={
            200: HomeOutputSerializer,
            404: OpenApiResponse(description="속한 집 없음"),
        },
    )
    def get(self, request: Request) -> Response:
        """현재 유저의 집 정보를 반환합니다."""
        home = selectors.get_user_home(request.user)
        if home is None:
            raise NotFound("속한 집이 없습니다.")
        return Response(HomeOutputSerializer(home).data)


class HomeInviteView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="초대코드로 집 정보 조회 (참여 전 미리보기)",
        parameters=[OpenApiParameter("code", str, OpenApiParameter.PATH, description="초대 코드")],
        responses={
            200: HomeInviteDetailSerializer,
            404: OpenApiResponse(description="유효하지 않은 초대코드"),
        },
    )
    def get(self, request: Request, code: str) -> Response:
        """초대코드로 집 정보를 조회합니다 (참여 전 미리보기)."""
        home = selectors.get_home_by_invite_code(code)
        if home is None:
            raise NotFound("유효하지 않은 초대코드입니다.")
        return Response(HomeInviteDetailSerializer(home).data)


class HomeJoinView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="초대코드로 집 참여",
        request=None,
        responses={
            200: HomeOutputSerializer,
            400: OpenApiResponse(description="이미 집이 있음"),
            404: OpenApiResponse(description="유효하지 않은 초대코드"),
        },
    )
    def post(self, request: Request) -> Response:
        """초대코드로 집에 참여합니다."""
        invite_code = request.data.get("invite_code", "")

        try:
            services.join_home(user=request.user, invite_code=invite_code)
        except services.AlreadyHasHomeError as e:
            raise ValidationError({"already_has_home": str(e)}) from e
        except services.HomeNotFoundError as e:
            raise NotFound(str(e)) from e

        home = selectors.get_user_home(request.user)
        return Response(HomeOutputSerializer(home).data)


class StarterPackListView(APIView):
    @extend_schema(
        tags=["StarterPacks"],
        summary="스타터팩 목록 조회",
        responses={200: StarterPackSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """스타터팩 목록을 반환합니다."""
        packs = selectors.get_starter_packs()
        return Response(StarterPackSerializer(packs, many=True).data)


class StarterPackChoreListView(APIView):
    @extend_schema(
        tags=["StarterPacks"],
        summary="스타터팩 집안일 목록 조회",
        parameters=[OpenApiParameter("starter_pack_id", int, OpenApiParameter.PATH, description="스타터팩 ID")],
        responses={200: ChoreOutputSerializer(many=True)},
    )
    def get(self, request: Request, starter_pack_id: int) -> Response:
        """특정 스타터팩의 집안일 목록을 반환합니다."""
        chores = selectors.get_starter_pack_chores(starter_pack_id)
        return Response(ChoreOutputSerializer(chores, many=True).data)
