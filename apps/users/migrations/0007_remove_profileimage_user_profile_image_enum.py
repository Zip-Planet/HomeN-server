from django.db import migrations, models


class Migration(migrations.Migration):
    """ProfileImage 모델 삭제 및 User.profile_image를 ImageField에서 IntegerField(enum)로 변경."""

    dependencies = [
        ("users", "0006_user_profile_image_imagefield_unique_name"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="user",
            name="profile_image",
        ),
        migrations.AddField(
            model_name="user",
            name="profile_image",
            field=models.IntegerField(
                blank=True,
                choices=[
                    (1, "캐릭터 1"),
                    (2, "캐릭터 2"),
                    (3, "캐릭터 3"),
                    (4, "캐릭터 4"),
                    (5, "캐릭터 5"),
                    (6, "캐릭터 6"),
                    (7, "캐릭터 7"),
                    (8, "캐릭터 8"),
                ],
                null=True,
            ),
        ),
        migrations.DeleteModel(
            name="ProfileImage",
        ),
    ]
