import factory

from apps.homes.models import Chore, Home, HomeChore, HomeImage, HomeMember, Reward, StarterPack
from apps.users.tests.factories import UserFactory


class HomeImageFactory(factory.django.DjangoModelFactory):
    image = factory.django.ImageField(color="green", width=100, height=100)

    class Meta:
        model = HomeImage


class HomeFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"집{n}")
    image = factory.SubFactory(HomeImageFactory)
    invite_code = factory.Sequence(lambda n: f"H{n:05d}")
    creation_step = Home.CreationStep.PROFILE
    status = Home.Status.DRAFT

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
    image = factory.django.ImageField(color="red", width=50, height=50)
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
