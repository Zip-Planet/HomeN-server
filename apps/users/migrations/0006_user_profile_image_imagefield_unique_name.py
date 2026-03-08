from django.db import migrations, models


class Migration(migrations.Migration):
    """User.profile_image를 FK에서 ImageField로 변경하고 name에 조건부 UniqueConstraint 추가."""

    dependencies = [
        ("users", "0005_profileimage_user_profile_image_remove_user_avatar"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="user",
            name="profile_image",
        ),
        migrations.AddField(
            model_name="user",
            name="profile_image",
            field=models.ImageField(blank=True, null=True, upload_to="profile_images/"),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(name__gt=""),
                fields=["name"],
                name="unique_user_name_when_set",
            ),
        ),
    ]
