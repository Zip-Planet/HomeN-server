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
    HomeImageSerializer,
    HomeInviteDetailSerializer,
    HomeOutputSerializer,
    RewardCreateSerializer,
    RewardOutputSerializer,
    StarterPackSerializer,
)


class HomeImageListView(APIView):
    def get(self, request: Request) -> Response:
        """프리셋 집 이미지 목록을 반환합니다."""
        images = selectors.get_home_images()
        return Response(HomeImageSerializer(images, many=True, context={"request": request}).data)


class HomeCreateView(APIView):
    def post(self, request: Request) -> Response:
        """새 집을 생성합니다 (1단계)."""
        serializer = HomeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            home = services.create_home(user=request.user, **serializer.validated_data)
        except services.AlreadyHasHomeError as e:
            raise ValidationError({"already_has_home": str(e)}) from e
        except services.HomeError as e:
            raise ValidationError({"invalid_image": str(e)}) from e

        return Response(
            HomeOutputSerializer(home, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class HomeDetailView(APIView):
    def get(self, request: Request) -> Response:
        """현재 유저의 집 정보를 반환합니다."""
        home = selectors.get_user_home(request.user)
        if home is None:
            raise NotFound("속한 집이 없습니다.")
        return Response(HomeOutputSerializer(home, context={"request": request}).data)


class HomeChoreView(APIView):
    def post(self, request: Request, pk: int) -> Response:
        """스타터팩의 집안일을 집에 추가합니다 (2단계)."""
        home = selectors.get_user_home(request.user)
        if home is None or home.pk != pk:
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
            ChoreOutputSerializer(chores, many=True, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class HomeRewardView(APIView):
    def post(self, request: Request, pk: int) -> Response:
        """리워드를 일괄 등록하고 집 생성을 완료합니다 (3단계)."""
        home = selectors.get_user_home(request.user)
        if home is None or home.pk != pk:
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
    def get(self, request: Request, code: str) -> Response:
        """초대코드로 집 정보를 조회합니다 (참여 전 미리보기)."""
        home = selectors.get_home_by_invite_code(code)
        if home is None:
            raise NotFound("유효하지 않은 초대코드입니다.")
        return Response(HomeInviteDetailSerializer(home, context={"request": request}).data)


class HomeJoinView(APIView):
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
        return Response(HomeOutputSerializer(home, context={"request": request}).data)


class StarterPackListView(APIView):
    def get(self, request: Request) -> Response:
        """스타터팩 목록을 반환합니다."""
        packs = selectors.get_starter_packs()
        return Response(StarterPackSerializer(packs, many=True).data)


class StarterPackChoreListView(APIView):
    def get(self, request: Request, pk: int) -> Response:
        """특정 스타터팩의 집안일 목록을 반환합니다."""
        chores = selectors.get_starter_pack_chores(pk)
        return Response(ChoreOutputSerializer(chores, many=True, context={"request": request}).data)
