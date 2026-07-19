from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_avatar_heygen_image_urls_avatar_heygen_preview_url'),
    ]

    operations = [
        migrations.AlterField(
            model_name='generatedvideo',
            name='video_url',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='generatedvideo',
            name='status',
            field=models.CharField(
                choices=[('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')],
                default='processing',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='generatedvideo',
            name='error_message',
            field=models.TextField(blank=True, null=True),
        ),
    ]
