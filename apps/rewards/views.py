"""리워드 컨트롤러.

`/api/v1/homes/mine/rewards/` 하위에 마운트된다 (리워드는 집에 종속).
도메인 예외는 서비스 레이어에서 발생시키고, 여기서 DRF 표준 예외로 매핑한다.
"""

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.homes.selectors import get_user_home
from apps.rewards import selectors, services
from apps.rewards.serializers import (
    RewardCreateSerializer,
    RewardDetailOutputSerializer,
    RewardListOutputSerializer,
    RewardOutputSerializer,
    RewardUpdateSerializer,
)
from common.error_responses import ErrorResponseSerializer, error_example
from common.exceptions import Conflict

_AUTH_FAILED_EXAMPLE = error_example(
    code="authentication_failed",
    message="Authentication credentials were not provided.",
    name="인증 실패",
)

# 목록 정렬 우선순위 — 받기 가능 > 진행 중 > 받기 완료 (동순위는 등록일 오름차순).
_STATUS_ORDER = {"claimable": 0, "in_progress": 1, "claimed": 2}


def _require_home(user):
    home = get_user_home(user)
    if home is None:
        raise NotFound("속한 집이 없습니다.")
    return home


class RewardListView(APIView):
    """리워드 목록 조회 / 등록."""

    @extend_schema(
        tags=["Rewards"],
        summary="리워드 목록 조회",
        description=(
            "## 🔥 설명\n"
            "리워드 탭(T4_RewardMain) 응답. 헤더용 **내 포인트 잔액**과 상태별 개수, "
            "정렬된 리워드 목록을 함께 반환한다.\n\n"
            "정렬은 `받기 가능 > 진행 중 > 받기 완료` 이며 동순위는 등록일 오름차순이다. "
            "`status` 는 저장값이 아니라 **요청 유저의 잔액 기준 파생값**이다.\n\n"
            "포인트 잔액 = 집안일 완료로 획득한 포인트 합 − 수령한 리워드의 포인트 합.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📤 응답 (200)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `my_point` | integer | 내 리워드 포인트 잔액 |\n"
            "| body | `claimable_count` / `in_progress_count` / `claimed_count` | integer | 상태별 개수 |\n"
            "| body | `rewards[].status` | string | claimable / in_progress / claimed |\n"
            "| body | `rewards[].remaining_point` | integer | 목표까지 남은 포인트 |\n"
            "| body | `rewards[].claim` | object | 수령 이력. 미수령이면 null |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 404 | `not_found` | 속한 집이 없음 |\n"
        ),
        responses={
            200: RewardListOutputSerializer,
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="속한 집이 없음."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="속한 집이 없습니다.", name="집 미존재"),
        ],
    )
    def get(self, request: Request) -> Response:
        home = _require_home(request.user)
        balance = selectors.get_point_balance(user=request.user)

        rewards = list(selectors.get_home_rewards(home))
        data = RewardOutputSerializer(rewards, many=True, context={"balance": balance}).data
        data.sort(key=lambda r: (_STATUS_ORDER.get(r["status"], 9), r["id"]))

        counts = {"claimable": 0, "in_progress": 0, "claimed": 0}
        for row in data:
            counts[row["status"]] = counts.get(row["status"], 0) + 1

        return Response({
            "my_point": balance,
            "claimable_count": counts["claimable"],
            "in_progress_count": counts["in_progress"],
            "claimed_count": counts["claimed"],
            "rewards": data,
        })

    @extend_schema(
        tags=["Rewards"],
        summary="리워드 등록",
        description=(
            "## 🔥 설명\n"
            "리워드를 등록한다. 같은 집 구성원이면 누구나 등록할 수 있고 등록자(`created_by`)가 기록된다. "
            "입력은 화면(W2_RewardCreateEdit)과 동일하게 **이름 + 목표 포인트** 뿐이다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| body | `name` | string | ✓ | 리워드 이름 (최대 20자) |\n"
            "| body | `goal_point` | integer | ✓ | 목표 포인트 (1 이상) |\n\n"
            "## 📤 응답 (201)\n"
            "등록된 리워드 (목록 항목과 동일 구조).\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `invalid` | 이름 길이 초과 / 목표 포인트 범위 오류 |\n"
            "| 404 | `not_found` | 속한 집이 없음 |\n"
        ),
        request=RewardCreateSerializer,
        responses={
            201: RewardOutputSerializer,
            400: OpenApiResponse(response=ErrorResponseSerializer, description="입력 검증 실패."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="속한 집이 없음."),
        },
        examples=[
            OpenApiExample(
                "리워드 등록",
                value={"name": "저녁 더치페이 1회 면제권", "goal_point": 1600},
                request_only=True,
            ),
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="속한 집이 없습니다.", name="집 미존재"),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = RewardCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            reward = services.create_reward(
                user=request.user,
                name=serializer.validated_data["name"],
                goal_point=serializer.validated_data["goal_point"],
            )
        except services.HomeRequiredError as e:
            raise NotFound(str(e)) from e

        balance = selectors.get_point_balance(user=request.user)
        return Response(
            RewardOutputSerializer(reward, context={"balance": balance}).data,
            status=status.HTTP_201_CREATED,
        )


class RewardDetailView(APIView):
    """리워드 단건 조회 / 수정 / 삭제."""

    @extend_schema(
        tags=["Rewards"],
        summary="리워드 상세 조회",
        description=(
            "## 🔥 설명\n"
            "리워드 상세(W1_RewardDetail) 응답. 목록 항목 구조에 **구성원 현황**(`member_progress`)이 "
            "추가된다 — 구성원별 보유 포인트와 목표 대비 달성률을 보유 포인트 내림차순으로 정렬해 "
            "1등부터 순위를 매긴다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `reward_id` | integer | ✓ | 리워드 PK |\n\n"
            "## 📤 응답 (200)\n"
            "| 위치 | 필드 | 타입 | 설명 |\n"
            "| --- | --- | --- | --- |\n"
            "| body | `member_progress[].rank` | integer | 보유 포인트 기준 순위 |\n"
            "| body | `member_progress[].point` | integer | 구성원 보유 포인트 |\n"
            "| body | `member_progress[].achievement_rate` | integer | 목표 대비 달성률 % (최대 100) |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 404 | `not_found` | 본인 집의 리워드가 아님 |\n"
        ),
        responses={
            200: RewardDetailOutputSerializer,
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="리워드 미존재."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(code="not_found", message="리워드를 찾을 수 없습니다.", name="리워드 미존재"),
        ],
    )
    def get(self, request: Request, reward_id: int) -> Response:
        reward = selectors.get_user_reward(user=request.user, reward_id=reward_id)
        if reward is None:
            raise NotFound("리워드를 찾을 수 없습니다.")

        return Response(
            RewardDetailOutputSerializer(
                reward,
                context={
                    "balance": selectors.get_point_balance(user=request.user),
                    "member_progress": selectors.get_member_progress(reward=reward),
                },
            ).data
        )

    @extend_schema(
        tags=["Rewards"],
        summary="리워드 수정 (PATCH)",
        description=(
            "## 🔥 설명\n"
            "리워드의 이름/목표 포인트를 부분 수정한다. **이미 수령된 리워드는 수정할 수 없다**(409) — "
            "수령 시점의 조건이 사후에 바뀌면 이력이 왜곡되기 때문이다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `reward_id` | integer | ✓ | 리워드 PK |\n"
            "| body | `name` | string | - | 리워드 이름 (최대 20자) |\n"
            "| body | `goal_point` | integer | - | 목표 포인트 (1 이상) |\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 404 | `not_found` | 본인 집의 리워드가 아님 |\n"
            "| 409 | `already_claimed` | 이미 수령된 리워드 |\n"
        ),
        request=RewardUpdateSerializer,
        responses={
            200: RewardOutputSerializer,
            400: OpenApiResponse(response=ErrorResponseSerializer, description="입력 검증 실패."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="리워드 미존재."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="이미 수령된 리워드."),
        },
        examples=[
            OpenApiExample("목표 포인트만 수정", value={"goal_point": 2000}, request_only=True),
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="already_claimed",
                message="이미 수령된 리워드는 수정할 수 없습니다.",
                name="수령 완료",
            ),
        ],
    )
    def patch(self, request: Request, reward_id: int) -> Response:
        serializer = RewardUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            reward = services.update_reward(
                user=request.user, reward_id=reward_id, fields=serializer.validated_data
            )
        except services.RewardAlreadyClaimedError as e:
            raise Conflict({e.code: str(e)}) from e
        except services.RewardError as e:
            raise NotFound(str(e)) from e

        balance = selectors.get_point_balance(user=request.user)
        return Response(RewardOutputSerializer(reward, context={"balance": balance}).data)

    @extend_schema(
        tags=["Rewards"],
        summary="리워드 삭제",
        description=(
            "## 🔥 설명\n"
            "리워드를 삭제한다. **이미 수령된 리워드는 삭제할 수 없다**(409) — 수령 이력을 보존해야 하기 때문이다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📤 응답 (204)\n"
            "본문 없음.\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 404 | `not_found` | 본인 집의 리워드가 아님 |\n"
            "| 409 | `already_claimed` | 이미 수령된 리워드 |\n"
        ),
        responses={
            204: OpenApiResponse(description="삭제 완료 (본문 없음)."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="리워드 미존재."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="이미 수령된 리워드."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="already_claimed",
                message="이미 수령된 리워드는 삭제할 수 없습니다.",
                name="수령 완료",
            ),
        ],
    )
    def delete(self, request: Request, reward_id: int) -> Response:
        try:
            services.delete_reward(user=request.user, reward_id=reward_id)
        except services.RewardAlreadyClaimedError as e:
            raise Conflict({e.code: str(e)}) from e
        except services.RewardError as e:
            raise NotFound(str(e)) from e

        return Response(status=status.HTTP_204_NO_CONTENT)


class RewardClaimView(APIView):
    """리워드 수령 (집당 1회)."""

    @extend_schema(
        tags=["Rewards"],
        summary="리워드 받기 (수령)",
        description=(
            "## 🔥 설명\n"
            "리워드를 수령한다. 수령은 **집당 1회** 이며, 요청 유저의 포인트 잔액이 목표 포인트 이상이어야 한다. "
            "수령 시점의 목표 포인트가 `claimed_point` 로 스냅샷되어 잔액에서 차감된다.\n\n"
            "수령 후 해당 리워드는 잠기며 화면은 \"받기 완료된 리워드예요\" 로 비활성화된다.\n\n"
            "## 🔐 인증\n"
            "Bearer access 토큰 필수.\n\n"
            "## 📥 요청\n"
            "| 위치 | 필드 | 타입 | 필수 | 설명 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| path | `reward_id` | integer | ✓ | 리워드 PK |\n\n"
            "## 📤 응답 (200)\n"
            "수령 처리된 리워드 (`status=claimed`, `claim` 채워짐).\n\n"
            "## ❌ 에러\n"
            "| status | code | 의미 |\n"
            "| --- | --- | --- |\n"
            "| 400 | `not_enough_points` | 포인트 잔액 부족 |\n"
            "| 404 | `not_found` | 본인 집의 리워드가 아님 |\n"
            "| 409 | `already_claimed` | 이미 수령된 리워드 |\n"
        ),
        request=None,
        responses={
            200: RewardOutputSerializer,
            400: OpenApiResponse(response=ErrorResponseSerializer, description="포인트 부족."),
            401: OpenApiResponse(response=ErrorResponseSerializer, description="인증 실패."),
            404: OpenApiResponse(response=ErrorResponseSerializer, description="리워드 미존재."),
            409: OpenApiResponse(response=ErrorResponseSerializer, description="이미 수령됨."),
        },
        examples=[
            _AUTH_FAILED_EXAMPLE,
            error_example(
                code="not_enough_points",
                message="포인트가 부족합니다. (보유 480P / 목표 2000P)",
                name="포인트 부족",
            ),
            error_example(code="already_claimed", message="이미 수령된 리워드입니다.", name="중복 수령"),
        ],
    )
    def post(self, request: Request, reward_id: int) -> Response:
        try:
            claim = services.claim_reward(user=request.user, reward_id=reward_id)
        except services.RewardAlreadyClaimedError as e:
            raise Conflict({e.code: str(e)}) from e
        except services.NotEnoughPointsError as e:
            raise ValidationError({e.code: str(e)}) from e
        except services.RewardError as e:
            raise NotFound(str(e)) from e

        reward = selectors.get_home_rewards(claim.reward.home).get(id=reward_id)
        balance = selectors.get_point_balance(user=request.user)
        return Response(RewardOutputSerializer(reward, context={"balance": balance}).data)
