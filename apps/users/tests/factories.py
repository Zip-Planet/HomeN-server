import factory

from apps.users.models import ProfileImage, SocialAccount, User


class ProfileImageFactory(factory.django.DjangoModelFactory):
    image = factory.django.ImageField(color="blue", width=100, height=100)

    class Meta:
        model = ProfileImage


class UserFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: f"user{n}")

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
