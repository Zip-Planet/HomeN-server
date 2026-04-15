from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.homes import selectors, services
from apps.homes.serializers import (
    ChoreOutputSerializer,
    HomeChoreCreateSerializer,
    HomeCreateSerializer,
    HomeInviteDetailSerializer,
    HomeOutputSerializer,
    RewardCreateSerializer,
    RewardOutputSerializer,
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
        summary="집 생성 (1단계)",
        request=HomeCreateSerializer,
        responses={
            201: HomeOutputSerializer,
            400: OpenApiResponse(description="이미 집이 있거나 잘못된 이미지 ID"),
        },
    )
    def post(self, request: Request) -> Response:
        """새 집을 생성합니다 (1단계)."""
        serializer = HomeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            home = services.create_home(user=request.user, **serializer.validated_data)
        except services.AlreadyHasHomeError as e:
            raise ValidationError({"already_has_home": str(e)}) from e

        return Response(
            HomeOutputSerializer(home).data,
            status=status.HTTP_201_CREATED,
        )


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


class HomeChoreView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="스타터팩 집안일 추가 (2단계)",
        parameters=[OpenApiParameter("home_id", int, OpenApiParameter.PATH, description="집 ID")],
        request=HomeChoreCreateSerializer,
        responses={
            201: ChoreOutputSerializer(many=True),
            400: OpenApiResponse(description="잘못된 스타터팩 ID"),
            403: OpenApiResponse(description="권한 없음"),
            404: OpenApiResponse(description="집을 찾을 수 없음"),
        },
    )
    def post(self, request: Request, home_id: int) -> Response:
        """스타터팩의 집안일을 집에 추가합니다 (2단계)."""
        home = selectors.get_user_home(request.user)
        if home is None or home.pk != home_id:
            raise NotFound("집을 찾을 수 없습니다.")

        serializer = HomeChoreCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            chores = services.add_starter_pack_chores(
                home=home, user=request.user, **serializer.validated_data
            )
        except services.HomePermissionError as e:
            raise PermissionDenied(str(e)) from e
        except services.HomeError as e:
            raise ValidationError({"invalid_starter_pack": str(e)}) from e

        return Response(
            ChoreOutputSerializer(chores, many=True).data,
            status=status.HTTP_201_CREATED,
        )


class HomeRewardView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="리워드 등록 및 집 생성 완료 (3단계)",
        parameters=[OpenApiParameter("home_id", int, OpenApiParameter.PATH, description="집 ID")],
        request=RewardCreateSerializer(many=True),
        responses={
            201: RewardOutputSerializer(many=True),
            403: OpenApiResponse(description="권한 없음"),
            404: OpenApiResponse(description="집을 찾을 수 없음"),
        },
    )
    def post(self, request: Request, home_id: int) -> Response:
        """리워드를 일괄 등록하고 집 생성을 완료합니다 (3단계)."""
        home = selectors.get_user_home(request.user)
        if home is None or home.pk != home_id:
            raise NotFound("집을 찾을 수 없습니다.")

        serializer = RewardCreateSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        try:
            rewards = services.add_rewards(
                home=home, user=request.user, rewards_data=serializer.validated_data
            )
        except services.HomePermissionError as e:
            raise PermissionDenied(str(e)) from e

        return Response(
            RewardOutputSerializer(rewards, many=True).data,
            status=status.HTTP_201_CREATED,
        )


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
