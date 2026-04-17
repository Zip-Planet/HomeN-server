import factory

from apps.homes.models import (
    Chore,
    ChoreImageType,
    Home,
    HomeChore,
    HomeImageType,
    HomeMember,
    Reward,
    StarterPack,
)
from apps.users.tests.factories import UserFactory


class HomeFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"집{n}")
    image = HomeImageType.TYPE_1
    invite_code = factory.Sequence(lambda n: f"H{n:05d}")
    status = Home.Status.ACTIVE

    class Meta:
        model = Home


class HomeMemberFactory(factory.django.DjangoModelFactory):
    home = factory.SubFactory(HomeFactory)
    user = factory.SubFactory(UserFactory)
    role = HomeMember.Role.MEMBER

    class Meta:
        model = HomeMember


class StarterPackFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"스타터팩{n}")
    description = ""

    class Meta:
        model = StarterPack


class ChoreFactory(factory.django.DjangoModelFactory):
    starter_pack = factory.SubFactory(StarterPackFactory)
    name = factory.Sequence(lambda n: f"집안일{n}")
    image = ChoreImageType.TYPE_1
    repeat_days = [0, 2, 4]
    difficulty = Chore.Difficulty.EASY

    class Meta:
        model = Chore


class HomeChoreFactory(factory.django.DjangoModelFactory):
    home = factory.SubFactory(HomeFactory)
    chore = factory.SubFactory(ChoreFactory)

    class Meta:
        model = HomeChore


class RewardFactory(factory.django.DjangoModelFactory):
    home = factory.SubFactory(HomeFactory)
    name = factory.Sequence(lambda n: f"리워드{n}")
    goal_point = 100

    class Meta:
        model = Reward
