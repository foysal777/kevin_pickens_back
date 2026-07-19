from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0009_generatedvideo_status_etc'),
    ]

    operations = [
        migrations.AlterField(
            model_name='avatar',
            name='heygen_preview_url',
            field=models.TextField(blank=True, null=True),
        ),
    ]
