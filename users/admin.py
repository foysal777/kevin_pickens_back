from django.contrib import admin
from . import models


class UserAdmin(admin.ModelAdmin):
	list_display = ("id", "email", "full_name", "is_staff", "is_active")
	search_fields = ("email", "full_name")


class AvatarAdmin(admin.ModelAdmin):
	list_display = ("id", "avatar", "is_cartoon", "heygen_avatar_id", "heygen_preview_url", "created_at")
	readonly_fields = ("heygen_avatar_id", "heygen_preview_url", "heygen_image_urls")
	search_fields = ("heygen_avatar_id",)
	list_filter = ("is_cartoon",)


class VoiceSampleAdmin(admin.ModelAdmin):
	list_display = ("id", "voice_sample", "created_at")
	readonly_fields = ("voice_sample",)


class GeneratedVideoAdmin(admin.ModelAdmin):
	list_display = ("id", "avatar", "video_url", "created_at")
	readonly_fields = ("video_url",)


admin.site.register(models.User, UserAdmin)
admin.site.register(models.Avatar, AvatarAdmin)
admin.site.register(models.VoiceSample, VoiceSampleAdmin)
admin.site.register(models.GeneratedVideo, GeneratedVideoAdmin)