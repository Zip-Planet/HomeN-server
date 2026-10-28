import factory

from apps.notifications.models import Device
from apps.users.tests.factories import UserFactory


class DeviceFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    registration_id = factory.Sequence(lambda n: f"fcm-registration-id-{n}")
    kind = Device.Kind.TOKEN
    platform = Device.Platform.IOS

    class Meta:
        model = Device
