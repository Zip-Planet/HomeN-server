from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.homes import selectors, services
from apps.homes.serializers import (
    ChoreOutputSerializer,
    ChoreMemoUpdateSerializer,
    HomeChoreListCreateSerializer,
    HomeChoreOutputSerializer,
    HomeCreateSerializer,
    HomeInviteDetailSerializer,
    HomeJoinSerializer,
    HomeOutputSerializer,
    ImageIdSerializer,
    StarterPackSerializer,
    TransferAdminSerializer,
)


class HomeImageListView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="프리셋 집 이미지 목록 조회",
        responses={200: ImageIdSerializer(many=True)},
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

    @extend_schema(
        tags=["Homes"],
        summary="내 집 삭제 (관리자 전용, 구성원 없을 때만)",
        responses={
            204: None,
            400: OpenApiResponse(description="구성원이 있어 삭제 불가"),
            403: OpenApiResponse(description="관리자만 집을 삭제할 수 있음"),
        },
    )
    def delete(self, request: Request) -> Response:
        """현재 유저의 집을 삭제합니다. 관리자 전용이며 구성원이 없어야 합니다."""
        try:
            services.delete_home(user=request.user)
        except services.NotHomeAdminError as e:
            raise PermissionDenied(str(e)) from e
        except services.HomeHasMembersError as e:
            raise ValidationError({"home_has_members": str(e)}) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        request=HomeJoinSerializer,
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


class HomeLeaveView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="집 나가기 (구성원 전용)",
        responses={
            204: None,
            403: OpenApiResponse(description="관리자는 양도 후 나갈 수 있음"),
            404: OpenApiResponse(description="속한 집 없음"),
        },
    )
    def post(self, request: Request) -> Response:
        """현재 유저가 집을 나갑니다. 관리자는 먼저 양도해야 합니다."""
        try:
            services.leave_home(user=request.user)
        except services.HomeNotFoundError as e:
            raise NotFound(str(e)) from e
        except services.AdminCannotLeaveError as e:
            raise PermissionDenied(str(e)) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


class HomeTransferAdminView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="관리자 양도 (관리자 전용)",
        request=TransferAdminSerializer,
        responses={
            204: None,
            400: OpenApiResponse(description="대상이 같은 집의 구성원이 아님"),
            403: OpenApiResponse(description="관리자만 양도 가능"),
        },
    )
    def post(self, request: Request) -> Response:
        """집 관리자 권한을 같은 집의 구성원에게 양도합니다."""
        serializer = TransferAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            services.transfer_admin(user=request.user, target_uid=serializer.validated_data["user_id"])
        except services.NotHomeAdminError as e:
            raise PermissionDenied(str(e)) from e
        except services.TransferAdminTargetError as e:
            raise ValidationError({"transfer_admin_target": str(e)}) from e
        return Response(status=status.HTTP_204_NO_CONTENT)


class HomeChoreListView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="집안일 리스트 생성 (관리자 전용)",
        request=HomeChoreListCreateSerializer,
        responses={
            201: HomeChoreOutputSerializer(many=True),
            400: OpenApiResponse(description="유효성 검사 실패"),
            404: OpenApiResponse(description="속한 집 없음"),
        },
    )
    def post(self, request: Request) -> Response:
        """집에 집안일을 추가합니다. 단건 및 복수 생성을 지원합니다."""
        serializer = HomeChoreListCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            home_chores = services.create_home_chores(
                user=request.user,
                chores=serializer.validated_data["chores"],
            )
        except services.HomeNotFoundError as e:
            raise NotFound(str(e)) from e

        return Response(HomeChoreOutputSerializer(home_chores, many=True).data, status=status.HTTP_201_CREATED)


class HomeChoreDetailView(APIView):
    @extend_schema(
        tags=["Homes"],
        summary="집안일 메모 수정",
        parameters=[OpenApiParameter("home_chore_id", int, OpenApiParameter.PATH, description="집안일 ID")],
        request=ChoreMemoUpdateSerializer,
        responses={
            200: HomeChoreOutputSerializer,
            404: OpenApiResponse(description="집안일을 찾을 수 없음"),
        },
    )
    def patch(self, request: Request, home_chore_id: int) -> Response:
        """집안일 메모를 수정합니다."""
        serializer = ChoreMemoUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            home_chore = services.update_home_chore_memo(
                user=request.user,
                home_chore_id=home_chore_id,
                memo=serializer.validated_data["memo"],
            )
        except services.HomeChoreNotFoundError as e:
            raise NotFound(str(e)) from e

        return Response(HomeChoreOutputSerializer(home_chore).data)


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
