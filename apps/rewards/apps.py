from django.apps import AppConfig


class RewardsConfig(AppConfig):
    """리워드 도메인 앱.

    포인트로 교환하는 보상(`Reward`)과 수령 이력(`RewardClaim`) 을 다룬다.
    포인트 자체는 집안일 완료 이력(`homes.ChoreCompletion`) 에서 파생되므로
    이 앱은 잔액을 저장하지 않고 조회 시점에 계산한다.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.rewards"
