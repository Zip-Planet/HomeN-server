import factory

from apps.homes.tests.factories import HomeFactory
from apps.rewards.models import Reward, RewardClaim
from apps.users.tests.factories import UserFactory


class RewardFactory(factory.django.DjangoModelFactory):
    home = factory.SubFactory(HomeFactory)
    name = factory.Sequence(lambda n: f"리워드{n}")
    goal_point = 100
    created_by = factory.SubFactory(UserFactory)

    class Meta:
        model = Reward


class RewardClaimFactory(factory.django.DjangoModelFactory):
    reward = factory.SubFactory(RewardFactory)
    claimed_by = factory.SubFactory(UserFactory)
    claimed_point = 100

    class Meta:
        model = RewardClaim
