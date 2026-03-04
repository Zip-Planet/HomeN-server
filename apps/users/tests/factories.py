import factory

from apps.users.models import SocialAccount, User


class UserFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"User {n}")

    class Meta:
        model = User
        skip_postgeneration_save = True

    @factory.post_generation
    def set_unusable_password(self, create, extracted, **kwargs):
        if create:
            self.set_unusable_password()
            self.save()


class SocialAccountFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    provider = SocialAccount.KAKAO
    provider_id = factory.Sequence(lambda n: f"kakao_id_{n}")

    class Meta:
        model = SocialAccount
