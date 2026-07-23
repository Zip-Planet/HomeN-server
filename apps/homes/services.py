import hashlib
import random
import secrets
import string
from datetime import date, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.homes.models import (
    AssignmentItem,
    Chore,
    ChoreCompletion,
    Home,
    HomeChore,
    HomeChoreNote,
    HomeMember,
    WeeklyAssignment,
)
from apps.homes.selectors import get_user_membership
from apps.rewards.models import Reward
from apps.users.models import User


class HomeError(Exception):
    """집 관련 일반 오류."""


class AlreadyHasHomeError(HomeError):
    """이미 집이 있는 유저가 집을 생성하거나 참여하려 할 때 발생합니다."""


class HomeNotFoundError(HomeError):
    """초대코드에 해당하는 집이 없을 때 발생합니다."""


class NotHomeAdminError(HomeError):
    """관리자가 아닌 유저가 관리자 전용 작업을 시도할 때 발생합니다."""


class HomeHasMembersError(HomeError):
    """집에 구성원이 있어 삭제할 수 없을 때 발생합니다."""


class AdminCannotLeaveError(HomeError):
    """관리자가 양도 없이 집을 나가려 할 때 발생합니다."""


class TransferAdminTargetError(HomeError):
    """관리자 양도 대상이 올바르지 않을 때 발생합니다."""


class HomeChoreNotFoundError(HomeError):
    """집안일을 찾을 수 없을 때 발생합니다."""


class StarterPackNotFoundError(HomeError):
    """스타터팩 ID 에 해당하는 chore 가 없을 때 발생합니다."""


class AmbiguousChoreInputError(HomeError):
    """`starter_pack_id` 와 커스텀 `chores` 가 동시에 지정되었을 때 발생합니다."""


class HomeChoreNoteNotFoundError(HomeError):
    """집안일 메모를 찾을 수 없을 때 발생합니다."""


class NotNoteAuthorError(HomeError):
    """메모 작성자가 아닌 유저가 수정/삭제를 시도할 때 발생합니다."""


class ChoreCompletionError(HomeError):
    """집안일 완료 처리 관련 오류의 공통 부모. `code` 는 API 에러 코드로 노출된다."""

    code = "chore_completion_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class NotChoreAssigneeError(ChoreCompletionError):
    """담당자가 아닌 유저가 완료/취소를 시도할 때 발생합니다 (403)."""

    code = "not_assignee"


class ChoreAlreadyCompletedError(ChoreCompletionError):
    """해당 날짜에 이미 완료 이력이 있을 때 발생합니다 (409)."""

    code = "already_completed"


class ChoreCompletionNotFoundError(ChoreCompletionError):
    """취소할 완료 이력이 없을 때 발생합니다 (404)."""

    code = "not_found"


# ──────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────


def _generate_invite_code() -> str:
    """중복되지 않는 6자리 초대코드를 생성합니다.

    Returns:
        대문자 영문+숫자 조합 6자리 문자열.
    """
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if not Home.objects.filter(invite_code=code).exists():
            return code


# ──────────────────────────────────────────
# 집 생성
# ──────────────────────────────────────────


def create_home(
    *,
    user: User,
    name: str,
    image_id: int,
    chores: list[dict[str, Any]],
    rewards: list[dict[str, Any]],
    starter_pack_id: int | None = None,
    starter_pack_chore_ids: list[int] | None = None,
) -> Home:
    """집을 생성하고 요청 유저를 관리자로 등록합니다.

    집안일·리워드를 함께 받아 하나의 트랜잭션으로 처리합니다. 집안일 입력은
    다음 둘 중 하나만 허용합니다 (둘 다 비어 있어도 됨):
    - `starter_pack_id`: 해당 스타터팩의 chore 들을 일괄로 HomeChore 로 연결.
    - `chores`: 커스텀 chore 정의 배열 (각 dict 가 Chore 신규 생성으로 이어짐).

    Args:
        user: 집을 생성하는 User 인스턴스.
        name: 집 이름.
        image_id: 선택된 집 이미지 enum 값.
        chores: 커스텀 집안일 데이터 목록. 빈 리스트면 생성하지 않습니다.
        rewards: [{"name": ..., "goal_point": ...}, ...] 형식의 리워드 목록. 빈 리스트면 생성하지 않습니다.
        starter_pack_id: 적용할 스타터팩 PK (선택). 지정 시 해당 팩의 chore 들을 일괄 연결.
        starter_pack_chore_ids: 팩에서 실제 적용할 Chore PK 목록 (미리보기 체크 결과).
            None 이면 팩 전체, 빈 리스트면 아무것도 연결하지 않습니다.

    Returns:
        생성된 Home 인스턴스.

    Raises:
        AlreadyHasHomeError: 이미 집이 있는 경우.
        AmbiguousChoreInputError: `starter_pack_id` 와 커스텀 `chores` 가 동시에 지정된 경우.
        StarterPackNotFoundError: `starter_pack_id` 에 해당하는 chore 가 없는 경우.
    """
    if starter_pack_id is not None and chores:
        raise AmbiguousChoreInputError(
            "`starter_pack_id` 와 `chores` 는 동시에 지정할 수 없습니다."
        )

    if HomeMember.objects.filter(user=user).exists():
        raise AlreadyHasHomeError("이미 속한 집이 있습니다.")

    with transaction.atomic():
        home = Home.objects.create(
            name=name,
            image=image_id,
            invite_code=_generate_invite_code(),
            status=Home.Status.ACTIVE,
        )
        HomeMember.objects.create(home=home, user=user, role=HomeMember.Role.ADMIN)

        if starter_pack_id is not None:
            _apply_starter_pack_to_home(
                home=home,
                starter_pack_id=starter_pack_id,
                chore_ids=starter_pack_chore_ids,
            )
        elif chores:
            chore_objs = Chore.objects.bulk_create([
                Chore(
                    category=c["category"],
                    name=c["name"],
                    description=c.get("description", ""),
                    repeat_days=c["repeat_days"],
                    difficulty=c["difficulty"],
                )
                for c in chores
            ])
            HomeChore.objects.bulk_create([HomeChore(home=home, chore=c) for c in chore_objs])

        if rewards:
            Reward.objects.bulk_create(
                [Reward(home=home, name=r["name"], goal_point=r["goal_point"]) for r in rewards]
            )

    return home


def _apply_starter_pack_to_home(
    *, home: Home, starter_pack_id: int, chore_ids: list[int] | None = None
) -> list[HomeChore]:
    """스타터팩의 chore 들을 주어진 집에 HomeChore 로 일괄 연결합니다.

    이미 같은 (home, chore) 쌍이 있으면 건너뜁니다 (멱등 — 동일 팩 재적용 안전).

    미리보기 화면(G4A/C3A)에서 개별 항목의 체크를 해제할 수 있으므로 선택된
    chore 만 적용할 수 있다. `chore_ids` 가 None 이면 팩 전체, 빈 리스트면
    아무것도 적용하지 않는다 ("전체 미선택 후 화면 넘겨도 상관 없음").

    Args:
        home: 대상 Home 인스턴스.
        starter_pack_id: 적용할 StarterPack PK.
        chore_ids: 적용할 Chore PK 목록. None 이면 팩 전체.

    Returns:
        새로 생성된 HomeChore 인스턴스 목록 (이미 존재해 skip 된 것은 제외).

    Raises:
        StarterPackNotFoundError: 해당 스타터팩에 chore 가 하나도 없는 경우.
    """
    pack_chores = list(Chore.objects.filter(starter_pack_id=starter_pack_id))
    if not pack_chores:
        raise StarterPackNotFoundError(
            f"스타터팩(id={starter_pack_id}) 또는 해당 집안일을 찾을 수 없습니다."
        )

    if chore_ids is not None:
        selected = set(chore_ids)
        pack_chores = [c for c in pack_chores if c.id in selected]
        if not pack_chores:
            return []

    existing_chore_ids = set(
        HomeChore.objects.filter(home=home, chore__in=pack_chores).values_list("chore_id", flat=True)
    )
    to_create = [HomeChore(home=home, chore=c) for c in pack_chores if c.id not in existing_chore_ids]
    if not to_create:
        return []
    return HomeChore.objects.bulk_create(to_create)


# ──────────────────────────────────────────
# 집 참여
# ──────────────────────────────────────────


def join_home(*, user: User, invite_code: str) -> HomeMember:
    """초대코드로 집에 구성원으로 참여합니다.

    Args:
        user: 참여할 User 인스턴스.
        invite_code: 6자리 초대코드.

    Returns:
        생성된 HomeMember 인스턴스.

    Raises:
        AlreadyHasHomeError: 이미 집이 있는 경우.
        HomeNotFoundError: 초대코드에 해당하는 활성 집이 없는 경우.
    """
    if HomeMember.objects.filter(user=user).exists():
        raise AlreadyHasHomeError("이미 속한 집이 있습니다. 기존 집에서 나간 후 참여해 주세요.")

    try:
        home = Home.objects.get(invite_code=invite_code.upper(), status=Home.Status.ACTIVE)
    except Home.DoesNotExist:
        raise HomeNotFoundError("유효하지 않은 초대코드입니다.")

    return HomeMember.objects.create(home=home, user=user, role=HomeMember.Role.MEMBER)


# ──────────────────────────────────────────
# 집 삭제
# ──────────────────────────────────────────


def delete_home(*, user: User) -> None:
    """유저가 속한 집을 삭제합니다. 관리자 전용이며 다른 구성원이 없어야 합니다.

    집을 삭제하면 모든 집안일, 리워드가 함께 삭제됩니다.
    단, 향후 구현될 집안일 완료 이력은 유저 FK에 SET_NULL을 사용해 보존합니다.

    Args:
        user: 삭제를 요청한 User 인스턴스.

    Raises:
        NotHomeAdminError: 관리자가 아니거나 집에 속하지 않은 경우.
        HomeHasMembersError: 집에 구성원(관리자 외)이 남아있는 경우.
    """
    membership = get_user_membership(user)
    if membership is None or membership.role != HomeMember.Role.ADMIN:
        raise NotHomeAdminError("관리자만 집을 삭제할 수 있습니다.")

    has_members = HomeMember.objects.filter(home=membership.home, role=HomeMember.Role.MEMBER).exists()
    if has_members:
        raise HomeHasMembersError("구성원이 있는 경우 집을 삭제할 수 없습니다. 구성원이 모두 나간 후 삭제해 주세요.")

    membership.home.delete()


# ──────────────────────────────────────────
# 집 나가기
# ──────────────────────────────────────────


def leave_home(*, user: User) -> None:
    """집을 나갑니다. 구성원만 가능하며 관리자는 양도 후 나갈 수 있습니다.

    Args:
        user: 나가려는 User 인스턴스.

    Raises:
        HomeNotFoundError: 속한 집이 없는 경우.
        AdminCannotLeaveError: 관리자가 양도 없이 나가려는 경우.
    """
    membership = get_user_membership(user)
    if membership is None:
        raise HomeNotFoundError("속한 집이 없습니다.")
    if membership.role == HomeMember.Role.ADMIN:
        raise AdminCannotLeaveError("관리자는 먼저 다른 구성원에게 관리자를 양도해야 합니다.")
    membership.delete()


# ──────────────────────────────────────────
# 관리자 양도
# ──────────────────────────────────────────


def transfer_admin(*, user: User, target_uid: str) -> None:
    """집 관리자 권한을 같은 집의 구성원에게 양도합니다.

    Args:
        user: 현재 관리자인 User 인스턴스.
        target_uid: 관리자를 넘겨받을 구성원의 uid (UUID 문자열).

    Raises:
        NotHomeAdminError: 요청자가 관리자가 아닌 경우.
        TransferAdminTargetError: 대상이 같은 집의 구성원이 아닌 경우.
    """
    my_membership = get_user_membership(user)
    if my_membership is None or my_membership.role != HomeMember.Role.ADMIN:
        raise NotHomeAdminError("관리자만 관리자를 양도할 수 있습니다.")

    try:
        target_membership = HomeMember.objects.get(
            home=my_membership.home,
            user__uid=target_uid,
            role=HomeMember.Role.MEMBER,
        )
    except HomeMember.DoesNotExist:
        raise TransferAdminTargetError("해당 유저는 같은 집의 구성원이 아닙니다.")

    with transaction.atomic():
        my_membership.role = HomeMember.Role.MEMBER
        my_membership.save(update_fields=["role"])
        target_membership.role = HomeMember.Role.ADMIN
        target_membership.save(update_fields=["role"])


# ──────────────────────────────────────────
# 집안일 생성
# ──────────────────────────────────────────


def create_home_chores(*, user: User, chores: list[dict[str, Any]]) -> list[HomeChore]:
    """유저의 집에 커스텀 집안일을 추가합니다.

    단건 및 복수 생성 모두 지원합니다. 스타터팩 일괄 적용은 `apply_starter_pack` 을 사용.

    Args:
        user: 요청한 User 인스턴스.
        chores: 생성할 집안일 데이터 목록.

    Returns:
        생성된 HomeChore 인스턴스 목록.

    Raises:
        HomeNotFoundError: 요청자가 집에 속하지 않은 경우.
    """
    membership = get_user_membership(user)
    if membership is None:
        raise HomeNotFoundError("속한 집이 없습니다.")

    with transaction.atomic():
        chore_objs = Chore.objects.bulk_create([
            Chore(
                category=c["category"],
                name=c["name"],
                description=c.get("description", ""),
                repeat_days=c["repeat_days"],
                difficulty=c["difficulty"],
            )
            for c in chores
        ])
        home_chore_objs = HomeChore.objects.bulk_create([
            HomeChore(home=membership.home, chore=c) for c in chore_objs
        ])

    return home_chore_objs


def apply_starter_pack(
    *, user: User, starter_pack_id: int, chore_ids: list[int] | None = None
) -> list[HomeChore]:
    """유저의 집에 스타터팩 chore 들을 일괄 등록합니다.

    이미 동일 (home, chore) 쌍이 있으면 건너뛰어 멱등성을 보장합니다.
    미리보기에서 체크 해제한 항목을 제외하려면 `chore_ids` 로 선택분만 넘긴다.

    Args:
        user: 요청한 User 인스턴스.
        starter_pack_id: 적용할 StarterPack PK.
        chore_ids: 적용할 Chore PK 목록. None 이면 팩 전체, 빈 리스트면 적용 없음.

    Returns:
        새로 생성된 HomeChore 인스턴스 목록 (이미 존재해 skip 된 것은 제외).

    Raises:
        HomeNotFoundError: 요청자가 집에 속하지 않은 경우.
        StarterPackNotFoundError: 해당 스타터팩에 chore 가 하나도 없는 경우.
    """
    membership = get_user_membership(user)
    if membership is None:
        raise HomeNotFoundError("속한 집이 없습니다.")

    with transaction.atomic():
        return _apply_starter_pack_to_home(
            home=membership.home, starter_pack_id=starter_pack_id, chore_ids=chore_ids
        )


def restore_home_chore(*, user: User, home_chore_id: int) -> HomeChore:
    """비활성화(soft-delete)된 집안일을 되살립니다 — 스낵바 "실행 취소".

    삭제 직후 스낵바에서 취소할 수 있어야 하므로, `is_active=False` 로 전환된
    집안일을 다시 활성화한다. 이력이 전혀 없어 물리 삭제된 집안일은 되살릴 수
    없다 (404).

    Args:
        user: 호출 유저 (같은 집 구성원이면 누구나).
        home_chore_id: 복구할 HomeChore PK.

    Returns:
        복구된 HomeChore 인스턴스.

    Raises:
        HomeChoreNotFoundError: 본인 집의 집안일이 아니거나 물리 삭제된 경우.
    """
    membership = get_user_membership(user)
    if membership is None:
        raise HomeChoreNotFoundError("집안일을 찾을 수 없습니다.")

    home_chore = HomeChore.objects.filter(id=home_chore_id, home=membership.home).first()
    if home_chore is None:
        raise HomeChoreNotFoundError("집안일을 찾을 수 없습니다.")

    if not home_chore.is_active:
        home_chore.is_active = True
        home_chore.save(update_fields=["is_active"])
    return home_chore


# ──────────────────────────────────────────
# 집안일 메모 (HomeChoreNote, 1:N)
# ──────────────────────────────────────────


def _get_home_chore_in_user_home(*, user: User, home_chore_id: int) -> HomeChore:
    """유저의 집에 속한 **활성** HomeChore 를 찾고, 없으면 HomeChoreNotFoundError 를 발생.

    notes 화면이 다른 집의 chore 를 노출하지 못하도록 모든 메모 CRUD 는 본 헬퍼를
    먼저 통과해야 한다. 삭제(비활성화)된 집안일은 조회 전용이므로 모든 쓰기 경로
    (집안일 수정/삭제, 메모 CRUD)에서 없음으로 취급한다.
    """
    membership = get_user_membership(user)
    if membership is None:
        raise HomeChoreNotFoundError("집안일을 찾을 수 없습니다.")
    try:
        return HomeChore.objects.get(id=home_chore_id, home=membership.home, is_active=True)
    except HomeChore.DoesNotExist:
        raise HomeChoreNotFoundError("집안일을 찾을 수 없습니다.")


def update_home_chore(
    *, user: User, home_chore_id: int, fields: dict[str, Any]
) -> HomeChore:
    """HomeChore 의 chore 메타를 부분 수정합니다 (구성원 누구나).

    수정은 항상 **copy-on-write** — 원본 Chore 는 보존하고 본인 집 전용 사본
    (`starter_pack=None`)을 새로 만들어 `HomeChore.chore` 를 교체합니다.
    과거 데이터(분담안 히스토리 등)가 수정 전 값을 참조할 수 있도록 원본을
    물리 수정하지 않습니다. 포인트는 난이도 기반 자동 산출이므로 별도 처리가
    없습니다 (`Chore.point` property).

    Args:
        user: 호출 유저.
        home_chore_id: 수정할 HomeChore PK.
        fields: 변경할 필드의 부분 dict (category/name/description/repeat_days/difficulty).
            지원되지 않는 키는 무시합니다. 빈 dict 면 변경 없이 그대로 반환합니다.

    Returns:
        최신 상태의 HomeChore 인스턴스.

    Raises:
        HomeChoreNotFoundError: 본인 집의 chore 가 아니거나 삭제(비활성화)된 경우.
    """
    home_chore = _get_home_chore_in_user_home(user=user, home_chore_id=home_chore_id)
    chore = home_chore.chore

    editable = ("category", "name", "description", "repeat_days", "difficulty")
    updates = {k: v for k, v in fields.items() if k in editable}

    if not updates:
        return home_chore

    with transaction.atomic():
        new_chore = Chore.objects.create(
            starter_pack=None,
            category=updates.get("category", chore.category),
            name=updates.get("name", chore.name),
            description=updates.get("description", chore.description),
            repeat_days=updates.get("repeat_days", chore.repeat_days),
            difficulty=updates.get("difficulty", chore.difficulty),
        )
        home_chore.chore = new_chore
        home_chore.save(update_fields=["chore"])

    home_chore.refresh_from_db()
    return home_chore


def delete_home_chore(*, user: User, home_chore_id: int) -> None:
    """집안일을 삭제합니다 (구성원 누구나, 원본 Chore 는 보존).

    완료 이력(`ChoreCompletion`)이 있으면 **비활성화**(soft-delete)해 리포트/
    기여도/히스토리 데이터를 보존하고, 이력이 전혀 없으면 물리 삭제합니다.
    비활성화된 집안일은 목록·분담안 (재)생성에서 제외되며, 상세 조회는 가능합니다.

    스타터팩 chore 는 다른 집에서도 살아있어야 하므로 원본 Chore 는 절대 삭제하지
    않습니다. 커스텀 chore 도 동일하게 원본을 보존합니다.

    Raises:
        HomeChoreNotFoundError: 본인 집의 chore 가 아니거나 이미 삭제된 경우.
    """
    home_chore = _get_home_chore_in_user_home(user=user, home_chore_id=home_chore_id)
    if home_chore.completions.exists():
        home_chore.is_active = False
        home_chore.save(update_fields=["is_active"])
    else:
        home_chore.delete()


def create_home_chore_note(*, user: User, home_chore_id: int, content: str) -> HomeChoreNote:
    """집안일에 메모를 추가합니다 (구성원 누구나).

    Raises:
        HomeChoreNotFoundError: 본인 집의 집안일이 아닌 경우.
    """
    home_chore = _get_home_chore_in_user_home(user=user, home_chore_id=home_chore_id)
    return HomeChoreNote.objects.create(home_chore=home_chore, author=user, content=content)


def update_home_chore_note(
    *, user: User, home_chore_id: int, note_id: int, content: str
) -> HomeChoreNote:
    """메모를 수정합니다. **작성자만** 가능.

    Raises:
        HomeChoreNotFoundError: 본인 집의 집안일이 아닌 경우.
        HomeChoreNoteNotFoundError: 해당 메모가 존재하지 않거나 다른 집안일의 것인 경우.
        NotNoteAuthorError: 작성자가 아닌 유저가 호출한 경우.
    """
    home_chore = _get_home_chore_in_user_home(user=user, home_chore_id=home_chore_id)
    try:
        note = HomeChoreNote.objects.get(id=note_id, home_chore=home_chore)
    except HomeChoreNote.DoesNotExist:
        raise HomeChoreNoteNotFoundError("메모를 찾을 수 없습니다.")

    if note.author_id != user.id:
        raise NotNoteAuthorError("본인이 작성한 메모만 수정할 수 있습니다.")

    note.content = content
    note.save(update_fields=["content", "updated_at"])
    return note


def delete_home_chore_note(*, user: User, home_chore_id: int, note_id: int) -> None:
    """메모를 삭제합니다. **작성자만** 가능.

    Raises:
        HomeChoreNotFoundError: 본인 집의 집안일이 아닌 경우.
        HomeChoreNoteNotFoundError: 해당 메모가 존재하지 않거나 다른 집안일의 것인 경우.
        NotNoteAuthorError: 작성자가 아닌 유저가 호출한 경우.
    """
    home_chore = _get_home_chore_in_user_home(user=user, home_chore_id=home_chore_id)
    try:
        note = HomeChoreNote.objects.get(id=note_id, home_chore=home_chore)
    except HomeChoreNote.DoesNotExist:
        raise HomeChoreNoteNotFoundError("메모를 찾을 수 없습니다.")

    if note.author_id != user.id:
        raise NotNoteAuthorError("본인이 작성한 메모만 삭제할 수 있습니다.")

    note.delete()


# ──────────────────────────────────────────
# 분담안 (WeeklyAssignment)
# ──────────────────────────────────────────

MIN_ACTIVE_CHORES_FOR_ASSIGNMENT = 3
CONTRIBUTION_LOOKBACK_WEEKS = 3


class AssignmentError(HomeError):
    """분담안 관련 오류의 공통 부모. `code` 는 API 에러 코드로 노출된다."""

    code = "assignment_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class AssignmentNotFoundError(AssignmentError):
    """분담안이 없거나 본인 집의 것이 아닐 때 발생합니다."""

    code = "not_found"


class AssignmentStateError(AssignmentError):
    """분담안 상태/입력이 요청을 허용하지 않을 때 발생합니다 (400)."""


class AssignmentConflictError(AssignmentError):
    """생성 시점 이후 변경이 감지되어 확정할 수 없을 때 발생합니다 (409).

    코드: chores_changed / members_changed / not_enough_chores.
    재생성으로 최신 상태를 반영한 뒤 다시 확정해야 한다.
    """


def week_start_of(day: date) -> date:
    """주어진 날짜가 속한 주차의 월요일 날짜를 반환합니다."""
    return day - timedelta(days=day.weekday())


def next_week_start(today: date | None = None) -> date:
    """다음 주차의 월요일 날짜를 반환합니다.

    Args:
        today: 기준 날짜 (테스트용 주입). None 이면 서버 로컬 날짜.
    """
    base = today or timezone.localdate()
    return week_start_of(base) + timedelta(days=7)


def _chore_fingerprint(home: Home) -> str:
    """활성 집안일 지문을 계산합니다 (생성 이후 집안일 변경 감지용).

    활성 HomeChore 들의 (id, 이름, 카테고리, 반복요일, 난이도) 를 id 순으로
    직렬화해 해시한다. 집안일 추가/수정(copy-on-write 로 chore_id 변경)/삭제
    (비활성화) 모두 지문을 바꾼다.
    """
    rows = [
        (hc.id, hc.chore.name, hc.chore.category, tuple(sorted(hc.chore.repeat_days)), hc.chore.difficulty)
        for hc in HomeChore.objects.select_related("chore").filter(home=home, is_active=True).order_by("id")
    ]
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def _member_uids_snapshot(home: Home) -> list[str]:
    """구성원 uid 스냅샷을 반환합니다 (생성 이후 구성원 변화 감지용)."""
    return sorted(str(uid) for uid in HomeMember.objects.filter(home=home).values_list("user__uid", flat=True))


def _recent_contribution_points(*, home: Home, week_start: date) -> dict[int, int]:
    """최근 3주 기여도(완료 포인트 합)를 유저 PK 별로 집계합니다.

    기여도 = 해당 주차 직전 3개 주차 동안 완료(`ChoreCompletion`)한 집안일의
    포인트 합. 배정 동점 시 기여도가 낮은 멤버를 우선한다.
    """
    since = week_start - timedelta(weeks=CONTRIBUTION_LOOKBACK_WEEKS)
    completions = (
        ChoreCompletion.objects
        .select_related("home_chore__chore")
        .filter(home_chore__home=home, completed_by__isnull=False, date__gte=since, date__lt=week_start)
    )
    totals: dict[int, int] = {}
    for completion in completions:
        user_id = completion.completed_by_id
        totals[user_id] = totals.get(user_id, 0) + completion.home_chore.chore.point
    return totals


def _generate_assignment_for_home(*, home: Home, week_start: date) -> WeeklyAssignment:
    """분담안 생성 코어 — 권한/주차 중복 검증은 호출 측 책임.

    배정 알고리즘 (specs/assignments.md):
    1. 활성 집안일 × repeat_days 를 (집안일, 요일) 항목으로 펼친다.
    2. 포인트 내림차순으로 정렬 후, 각 항목을 누적 배정 포인트가 가장 낮은
       멤버에게 배정한다 (greedy/LPT — 멤버별 총합 최대한 균등).
    3. 누적 동점 시 최근 3주 기여도가 낮은 멤버 우선, 그래도 동점이면 무작위
       (재생성 시 동일 결과 반복 방지).

    Raises:
        AssignmentStateError: 활성 집안일이 3개 미만이거나 구성원이 없는 경우.
    """
    members = list(HomeMember.objects.select_related("user").filter(home=home))
    if not members:
        raise AssignmentStateError("집에 구성원이 없습니다.", code="no_members")

    home_chores = list(HomeChore.objects.select_related("chore").filter(home=home, is_active=True))
    if len(home_chores) < MIN_ACTIVE_CHORES_FOR_ASSIGNMENT:
        raise AssignmentStateError(
            f"분담안을 만들려면 활성 집안일이 {MIN_ACTIVE_CHORES_FOR_ASSIGNMENT}개 이상이어야"
            " 합니다.",
            code="not_enough_chores",
        )

    entries = [
        (home_chore, weekday)
        for home_chore in home_chores
        for weekday in sorted(set(home_chore.chore.repeat_days))
    ]
    entries.sort(key=lambda entry: (-entry[0].chore.point, entry[0].id, entry[1]))

    contribution = _recent_contribution_points(home=home, week_start=week_start)
    totals: dict[int, int] = {member.user_id: 0 for member in members}
    tie_break: dict[int, tuple[int, float]] = {
        member.user_id: (contribution.get(member.user_id, 0), random.random()) for member in members
    }
    user_by_id = {member.user_id: member.user for member in members}

    assigned: list[tuple[HomeChore, int, int]] = []
    for home_chore, weekday in entries:
        user_id = min(totals, key=lambda uid: (totals[uid], tie_break[uid][0], tie_break[uid][1]))
        totals[user_id] += home_chore.chore.point
        assigned.append((home_chore, weekday, user_id))

    with transaction.atomic():
        assignment = WeeklyAssignment.objects.create(
            home=home,
            week_start=week_start,
            status=WeeklyAssignment.Status.PROPOSED,
            generated_at=timezone.now(),
            member_uids_snapshot=_member_uids_snapshot(home),
            chore_fingerprint=_chore_fingerprint(home),
        )
        AssignmentItem.objects.bulk_create([
            AssignmentItem(
                assignment=assignment,
                home_chore=home_chore,
                weekday=weekday,
                assignee=user_by_id[user_id],
                chore_name=home_chore.chore.name,
                category=home_chore.chore.category,
                difficulty=home_chore.chore.difficulty,
                point=home_chore.chore.point,
            )
            for home_chore, weekday, user_id in assigned
        ])
    return assignment


def _get_admin_membership(user: User) -> HomeMember:
    """분담안 생성/재생성/확정 권한(관리자) 검증 공통 헬퍼."""
    membership = get_user_membership(user)
    if membership is None or membership.role != HomeMember.Role.ADMIN:
        raise NotHomeAdminError("관리자만 분담안을 생성/재생성/확정할 수 있습니다.")
    return membership


def generate_assignment(*, user: User, week_start: date | None = None) -> WeeklyAssignment:
    """분담안을 수동 생성합니다 (관리자 전용).

    Args:
        user: 요청 유저 (관리자여야 함).
        week_start: 대상 주차의 월요일 날짜. 생략 시 다음 주차. 과거 주차 불가.

    Raises:
        NotHomeAdminError: 관리자가 아닌 경우.
        AssignmentStateError: 잘못된 주차 / 해당 주차 분담안 이미 존재 /
            활성 집안일 3개 미만.
    """
    membership = _get_admin_membership(user)
    home = membership.home

    week_start = week_start or next_week_start()
    if week_start.weekday() != 0:
        raise AssignmentStateError("week_start 는 월요일 날짜여야 합니다.", code="invalid_week_start")
    if week_start < week_start_of(timezone.localdate()):
        raise AssignmentStateError("과거 주차의 분담안은 생성할 수 없습니다.", code="invalid_week_start")

    if WeeklyAssignment.objects.filter(home=home, week_start=week_start).exists():
        raise AssignmentStateError(
            "해당 주차의 분담안이 이미 존재합니다. 재생성을 이용해 주세요.",
            code="assignment_already_exists",
        )

    return _generate_assignment_for_home(home=home, week_start=week_start)


def regenerate_assignment(*, user: User, assignment_id: int) -> WeeklyAssignment:
    """proposed 분담안을 폐기하고 최신 원본 기준으로 재생성합니다 (관리자 전용).

    Raises:
        NotHomeAdminError: 관리자가 아닌 경우.
        AssignmentNotFoundError: 본인 집의 분담안이 아닌 경우.
        AssignmentStateError: proposed 상태가 아니거나 활성 집안일 3개 미만.
    """
    membership = _get_admin_membership(user)

    try:
        assignment = WeeklyAssignment.objects.get(id=assignment_id, home=membership.home)
    except WeeklyAssignment.DoesNotExist:
        raise AssignmentNotFoundError("분담안을 찾을 수 없습니다.") from None

    if assignment.status != WeeklyAssignment.Status.PROPOSED:
        raise AssignmentStateError("제안됨 상태의 분담안만 재생성할 수 있습니다.", code="not_proposed")

    with transaction.atomic():
        week_start = assignment.week_start
        assignment.delete()
        return _generate_assignment_for_home(home=membership.home, week_start=week_start)


def confirm_assignment(*, user: User, assignment_id: int) -> WeeklyAssignment:
    """proposed 분담안을 확정합니다 (관리자 전용).

    확정 조건 (specs/assignments.md):
    - proposed 상태 분담안 존재 / 같은 주차 확정본 없음 / 구성원 1명 이상
    - 생성 시점 이후 집안일 변경 없음 (지문 일치)
    - 활성 집안일 3개 이상
    - 생성 시점 이후 구성원 변화 없음 (스냅샷 일치)

    Raises:
        NotHomeAdminError: 관리자가 아닌 경우.
        AssignmentNotFoundError: 본인 집의 분담안이 아닌 경우.
        AssignmentStateError: proposed 상태가 아니거나 같은 주차 확정본 존재 (400).
        AssignmentConflictError: 집안일/구성원 변경 또는 활성 집안일 부족 감지 (409).
    """
    membership = _get_admin_membership(user)
    home = membership.home

    try:
        assignment = WeeklyAssignment.objects.get(id=assignment_id, home=home)
    except WeeklyAssignment.DoesNotExist:
        raise AssignmentNotFoundError("분담안을 찾을 수 없습니다.") from None

    _check_confirm_conditions(home=home, assignment=assignment)
    return _mark_confirmed(assignment, confirmed_by=user)


def _check_confirm_conditions(*, home: Home, assignment: WeeklyAssignment) -> None:
    """확정 조건을 검증합니다 (수동/자동 확정 공용).

    Raises:
        AssignmentStateError: proposed 상태가 아니거나 같은 주차 확정본 존재,
            구성원 없음 (400).
        AssignmentConflictError: 집안일/구성원 변경 또는 활성 집안일 부족 감지 (409).
    """
    if assignment.status != WeeklyAssignment.Status.PROPOSED:
        raise AssignmentStateError("제안됨 상태의 분담안만 확정할 수 있습니다.", code="not_proposed")

    if WeeklyAssignment.objects.filter(
        home=home, week_start=assignment.week_start, status=WeeklyAssignment.Status.CONFIRMED
    ).exists():
        raise AssignmentStateError("해당 주차에 이미 확정된 분담안이 있습니다.", code="already_confirmed_week")

    if not HomeMember.objects.filter(home=home).exists():
        raise AssignmentStateError("집에 구성원이 없습니다.", code="no_members")

    if _member_uids_snapshot(home) != assignment.member_uids_snapshot:
        raise AssignmentConflictError(
            "분담안 생성 이후 구성원이 변경되었습니다. 분담안을 재생성해 주세요.",
            code="members_changed",
        )

    active_count = HomeChore.objects.filter(home=home, is_active=True).count()
    if active_count < MIN_ACTIVE_CHORES_FOR_ASSIGNMENT:
        raise AssignmentConflictError(
            f"활성 집안일이 {MIN_ACTIVE_CHORES_FOR_ASSIGNMENT}개 미만이 되어 확정할 수 없습니다."
            " 분담안을 재생성해 주세요.",
            code="not_enough_chores",
        )

    if _chore_fingerprint(home) != assignment.chore_fingerprint:
        raise AssignmentConflictError(
            "분담안 생성 이후 집안일이 변경되었습니다. 분담안을 재생성해 주세요.",
            code="chores_changed",
        )


def _mark_confirmed(assignment: WeeklyAssignment, *, confirmed_by: User | None) -> WeeklyAssignment:
    """분담안을 확정 상태로 전이합니다 (자동 확정이면 confirmed_by=None)."""
    assignment.status = WeeklyAssignment.Status.CONFIRMED
    assignment.confirmed_at = timezone.now()
    assignment.confirmed_by = confirmed_by
    assignment.save(update_fields=["status", "confirmed_at", "confirmed_by", "updated_at"])
    # TODO(알림): 확정 시 보드 카드 생성 + 전 구성원 앱푸시 (인프라 선정 후 구현 — specs/assignments.md)
    return assignment


# ──────────────────────────────────────────
# 분담안 스케줄 배치 (management command 에서 호출)
# ──────────────────────────────────────────


def generate_weekly_assignments(*, today: date | None = None) -> tuple[int, int]:
    """모든 활성 집에 다음 주차 분담안을 자동 생성합니다 (매주 일요일 21:05).

    해당 주차 분담안이 이미 있으면(관리자 수동 생성 포함) 그 집은 스킵한다.
    활성 집안일 3개 미만·구성원 없음도 스킵한다. 멱등 — 중복 실행 안전.

    Args:
        today: 기준 날짜 (테스트용 주입). None 이면 서버 로컬 날짜.

    Returns:
        (생성 건수, 스킵 건수).
    """
    week_start = next_week_start(today)
    created = skipped = 0
    for home in Home.objects.filter(status=Home.Status.ACTIVE):
        if WeeklyAssignment.objects.filter(home=home, week_start=week_start).exists():
            skipped += 1
            continue
        try:
            _generate_assignment_for_home(home=home, week_start=week_start)
        except AssignmentStateError:
            skipped += 1
            continue
        created += 1
    return created, skipped


def auto_confirm_due_assignments(*, today: date | None = None) -> tuple[int, int]:
    """시작된 주차의 proposed 분담안을 자동 확정합니다 (매주 월요일 00:00).

    확정 조건을 만족하는 것만 확정(`confirmed_by=None`)하고, 불만족은 proposed
    로 유지한다 — 관리자가 재생성하거나 수동 확정해야 한다. 멱등.

    Args:
        today: 기준 날짜 (테스트용 주입). None 이면 서버 로컬 날짜.

    Returns:
        (확정 건수, 스킵 건수).
    """
    week_start = week_start_of(today or timezone.localdate())
    confirmed = skipped = 0
    due = WeeklyAssignment.objects.select_related("home").filter(
        status=WeeklyAssignment.Status.PROPOSED, week_start=week_start
    )
    for assignment in due:
        try:
            _check_confirm_conditions(home=assignment.home, assignment=assignment)
        except AssignmentError:
            skipped += 1
            continue
        _mark_confirmed(assignment, confirmed_by=None)
        confirmed += 1
    return confirmed, skipped


def expire_past_assignments(*, today: date | None = None) -> int:
    """종료된 주차의 confirmed 분담안을 expired 로 전환합니다 (매주 월요일 00:00).

    Args:
        today: 기준 날짜 (테스트용 주입). None 이면 서버 로컬 날짜.

    Returns:
        전환 건수.
    """
    week_start = week_start_of(today or timezone.localdate())
    return WeeklyAssignment.objects.filter(
        status=WeeklyAssignment.Status.CONFIRMED, week_start__lt=week_start
    ).update(status=WeeklyAssignment.Status.EXPIRED, updated_at=timezone.now())


# ──────────────────────────────────────────
# 집안일 완료 처리 (ChoreCompletion)
# ──────────────────────────────────────────


def _assignment_item_for_date(*, home: Home, home_chore: HomeChore, target_date: date) -> AssignmentItem:
    """해당 날짜에 배정된 확정 분담안 항목을 찾습니다.

    완료 처리는 "확정된 분담안의 담당자"만 가능하다 (Figma T1_HomeDashboard 의
    체크박스는 확정 분담안 항목에만 노출된다). 제안(proposed) 상태이거나 해당
    요일에 배정이 없으면 완료할 수 없다.

    Args:
        home: 대상 집.
        home_chore: 대상 집안일.
        target_date: 완료 기준 날짜.

    Returns:
        해당 (집안일, 요일) 의 AssignmentItem.

    Raises:
        ChoreCompletionError: 확정 분담안이 없거나 그 날짜에 배정이 없는 경우.
    """
    assignment = WeeklyAssignment.objects.filter(
        home=home,
        week_start=week_start_of(target_date),
        status=WeeklyAssignment.Status.CONFIRMED,
    ).first()
    if assignment is None:
        raise ChoreCompletionError(
            "확정된 분담안이 없어 완료 처리할 수 없습니다.",
            code="assignment_not_confirmed",
        )

    item = AssignmentItem.objects.filter(
        assignment=assignment, home_chore=home_chore, weekday=target_date.weekday()
    ).first()
    if item is None:
        raise ChoreCompletionError(
            "해당 날짜에 배정된 집안일이 아닙니다.",
            code="not_assigned_on_date",
        )
    return item


def complete_chore(
    *,
    user: User,
    home_chore_id: int,
    target_date: date | None = None,
) -> ChoreCompletion:
    """집안일을 완료 처리합니다 (담당자 전용).

    같은 (집안일, 날짜) 조합은 1건만 기록된다 — 중복 요청은 409 로 차단한다.

    Args:
        user: 완료를 기록하는 User (해당 항목의 담당자여야 함).
        home_chore_id: 대상 HomeChore PK.
        target_date: 완료 기준 날짜. 생략 시 서버 로컬 날짜(오늘).

    Returns:
        생성된 ChoreCompletion 인스턴스.

    Raises:
        HomeChoreNotFoundError: 본인 집의 활성 집안일이 아닌 경우.
        ChoreCompletionError: 확정 분담안이 없거나 그 날짜에 배정이 없는 경우.
        NotChoreAssigneeError: 담당자가 아닌 경우.
        ChoreAlreadyCompletedError: 이미 완료 이력이 있는 경우.
    """
    target_date = target_date or timezone.localdate()
    home_chore = _get_home_chore_in_user_home(user=user, home_chore_id=home_chore_id)

    item = _assignment_item_for_date(
        home=home_chore.home, home_chore=home_chore, target_date=target_date
    )
    if item.assignee_id != user.id:
        raise NotChoreAssigneeError("담당자만 완료 처리할 수 있습니다.")

    completion, created = ChoreCompletion.objects.get_or_create(
        home_chore=home_chore,
        date=target_date,
        defaults={"completed_by": user},
    )
    if not created:
        raise ChoreAlreadyCompletedError("이미 완료 처리된 집안일입니다.")

    # 화면 스낵바("완료! +120pt")가 획득 포인트를 즉시 노출하므로 분담안 항목의
    # 스냅샷 포인트를 응답용 임시 속성으로 실어 보낸다 (DB 컬럼 아님).
    completion.earned_point = item.point
    return completion


def uncomplete_chore(*, user: User, home_chore_id: int, target_date: date) -> None:
    """완료 처리를 취소합니다 (완료한 본인 전용 — 스낵바 "실행 취소").

    Args:
        user: 취소를 요청한 User.
        home_chore_id: 대상 HomeChore PK.
        target_date: 취소할 완료 이력의 날짜.

    Raises:
        HomeChoreNotFoundError: 본인 집의 활성 집안일이 아닌 경우.
        ChoreCompletionNotFoundError: 해당 날짜 완료 이력이 없는 경우.
        NotChoreAssigneeError: 완료를 기록한 본인이 아닌 경우.
    """
    home_chore = _get_home_chore_in_user_home(user=user, home_chore_id=home_chore_id)

    completion = ChoreCompletion.objects.filter(home_chore=home_chore, date=target_date).first()
    if completion is None:
        raise ChoreCompletionNotFoundError("완료 이력을 찾을 수 없습니다.")
    if completion.completed_by_id != user.id:
        raise NotChoreAssigneeError("완료 처리한 본인만 취소할 수 있습니다.")

    completion.delete()


def _announce_assignment(assignment: WeeklyAssignment, *, kind: str) -> None:
    """분담안 생성/확정을 보드 봇 카드와 알림으로 알립니다.

    보드·알림은 부가 기능이므로 실패해도 분담안 자체는 성립해야 한다. 다만 지금은
    같은 DB 트랜잭션 밖에서 단순 호출만 하며, 인프라(푸시)는 미정이라 알림 레코드
    적재까지만 수행한다.

    Args:
        assignment: 대상 분담안.
        kind: "created" (제안) 또는 "confirmed" (확정).
    """
    from apps.boards.models import BotCardKind
    from apps.boards.services import publish_bot_card
    from apps.notifications.models import NotificationCategory
    from apps.notifications.services import notify_home

    total_count = assignment.items.count()
    if kind == "confirmed":
        card_kind = BotCardKind.ASSIGNMENT_CONFIRMED
        title = "분담안이 확정됐어요"
    else:
        card_kind = BotCardKind.ASSIGNMENT_CREATED
        title = "분담안이 생성됐어요"

    publish_bot_card(
        home=assignment.home,
        kind=card_kind,
        week_start=assignment.week_start,
        payload={"total_count": total_count, "week_start": str(assignment.week_start)},
    )
    notify_home(
        home=assignment.home,
        category=NotificationCategory.ASSIGNMENT,
        title=title,
        body=f"총 {total_count}개 집안일 · {assignment.week_start} 주차",
        deep_link=f"assignment:{assignment.week_start}",
    )
