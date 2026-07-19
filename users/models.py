from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import random
from users.basemodel import BaseModel
from users.usermanager import CustomUserManager


def user_profile_upload_path(instance, filename):
    return f"profile_pics/user_{instance.id}/{filename}"


class User(AbstractUser, BaseModel):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True, null=True)
    profile_picture = models.ImageField(upload_to=user_profile_upload_path, blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)



    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = CustomUserManager()

    def __str__(self):
        return self.full_name or self.email

class Avatar(BaseModel):
    avatar = models.ImageField(upload_to='avatars/')
    is_cartoon = models.BooleanField(default=False)
    heygen_avatar_id = models.CharField(max_length=255, blank=True, null=True)
    heygen_preview_url = models.TextField(blank=True, null=True)  # URLField max_length too short for HeyGen signed URLs
    heygen_image_urls = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"Avatar for {self.avatar}"
    

class VoiceSample(BaseModel):
    voice_sample = models.FileField(upload_to='voice_samples/')

    def __str__(self):
        return f"Voice Sample for {self.voice_sample}"
    

class GeneratedVideo(BaseModel):
    avatar = models.ForeignKey(Avatar, on_delete=models.SET_NULL, null=True, blank=True)
    video_url = models.URLField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        default='processing',
        choices=[
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ]
    )
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Generated Video at {self.video_url or 'processing'}"