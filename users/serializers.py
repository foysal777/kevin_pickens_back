from rest_framework import serializers
from . import models
from ai_file import test_ai
import os, shutil, re
from datetime import datetime, timezone
from pathlib import Path
from django.conf import settings


def ensure_https(url: str) -> str:
    if not url:
        return url
    s_url = str(url).strip().strip('"').strip("'")
    if s_url.startswith("http://"):
        return "https://" + s_url[7:]
    return s_url


def build_absolute_https_uri(request, url: str) -> str:
    if not url:
        return url
    s_url = str(url).strip().strip('"').strip("'")
    if request and not (s_url.startswith("http://") or s_url.startswith("https://")):
        s_url = request.build_absolute_uri(s_url)
    return ensure_https(s_url)


class UserSerializer(serializers.ModelSerializer):
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = models.User
        fields = ['id', 'email', 'full_name', 'profile_picture', 'phone_number', 'date_of_birth']

    def get_profile_picture(self, obj):
        if not obj.profile_picture:
            return None
        request = self.context.get('request')
        url = (obj.profile_picture.url or "").strip().strip('"').strip("'")
        return build_absolute_https_uri(request, url)


class AvatarList(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()
    heygen_avatar_id = serializers.CharField(read_only=True)
    heygen_avatar_info = serializers.SerializerMethodField()
    heygen_preview_url = serializers.SerializerMethodField()
    heygen_image_urls = serializers.SerializerMethodField()
    heygen_generated_image = serializers.SerializerMethodField()

    class Meta:
        model = models.Avatar
        fields = [
            'id', 'avatar', 'is_cartoon', 'created_at',
            'heygen_generated_image',
            'heygen_avatar_id', 'heygen_preview_url', 'heygen_image_urls',
            'heygen_avatar_info',
        ]

    def get_avatar(self, obj):
        request = self.context.get('request')
        if not obj.avatar:
            return None
        url = (obj.avatar.url or "").strip().strip('"').strip("'")
        return build_absolute_https_uri(request, url)

    def _get_cached_heygen_info(self, obj):
        if not hasattr(obj, '_cached_heygen_info'):
            obj._cached_heygen_info = self._fetch_and_update_info(obj)
        return obj._cached_heygen_info

    def _fetch_and_update_info(self, obj):
        avatar_id = getattr(obj, 'heygen_avatar_id', None)
        request = self.context.get('request')

        # If we don't yet have a remote HeyGen avatar id, try to create one
        if not avatar_id:
            try:
                img_path = getattr(obj.avatar, 'path', None)
                if not img_path:
                    return None
                mime = test_ai._guess_mime(img_path)
                image_asset_id = test_ai._upload_asset(img_path, mime)
                if not image_asset_id:
                    return None
                if obj.is_cartoon:
                    payload = test_ai._create_cartoon_avatar(image_asset_id, avatar_name=f"avatar_{obj.id}", wait=False)
                else:
                    payload = test_ai._create_photo_avatar(image_asset_id, avatar_name=f"avatar_{obj.id}", wait=False)
                if payload and isinstance(payload, dict) and payload.get('avatar_id'):
                    obj.heygen_avatar_id = payload.get('avatar_id')
                    try:
                        obj.save(update_fields=['heygen_avatar_id'])
                    except Exception:
                        pass
                    avatar_id = obj.heygen_avatar_id
                else:
                    return None
            except Exception:
                return None

        info = test_ai.fetch_heygen_avatar_info(avatar_id)
        if not info:
            # Fall back to returning current DB data if API call fails
            prev = ensure_https(obj.heygen_preview_url) if obj.heygen_preview_url else None
            imgs = [ensure_https(u) for u in (obj.heygen_image_urls or []) if u]
            return {
                "avatar_id": avatar_id,
                "status": "error",
                "preview_image_url": prev,
                "image_urls": imgs
            }

        # Normalize image URLs — make absolute if request available and URL is relative, enforce https
        normalized = dict(info)
        avatar_status = normalized.get('status', '')
        img_list = normalized.get('image_urls') or []
        norm_urls = []
        for u in img_list:
            if not u:
                continue
            u = build_absolute_https_uri(request, u)
            norm_urls.append(u)
        # also normalize preview
        preview = normalized.get('preview_image_url')
        if preview:
            normalized['preview_image_url'] = build_absolute_https_uri(request, preview)

        normalized['image_urls'] = norm_urls

        # Only persist to DB when avatar is ready (not still processing).
        # Saving empty values during "processing" would permanently null out the fields.
        is_ready = avatar_status in ('completed', 'active')
        if is_ready and (norm_urls or normalized.get('preview_image_url')):
            try:
                obj.heygen_preview_url = normalized.get('preview_image_url')
                obj.heygen_image_urls = norm_urls
                obj.save(update_fields=['heygen_preview_url', 'heygen_image_urls'])
            except Exception:
                pass
        elif not is_ready:
            # Fall back to previously persisted values so the response still
            # returns whatever was cached from a prior successful fetch.
            if not norm_urls and obj.heygen_image_urls:
                normalized['image_urls'] = [ensure_https(u) for u in obj.heygen_image_urls if u]
            if not normalized.get('preview_image_url') and obj.heygen_preview_url:
                normalized['preview_image_url'] = ensure_https(obj.heygen_preview_url)

        # Also expose the persisted fields at top-level for serializer convenience
        normalized['persisted_preview_url'] = ensure_https(obj.heygen_preview_url) if obj.heygen_preview_url else None
        normalized['persisted_image_urls'] = [ensure_https(u) for u in (obj.heygen_image_urls or []) if u]
        return normalized

    def get_heygen_avatar_info(self, obj):
        return self._get_cached_heygen_info(obj)

    def get_heygen_preview_url(self, obj):
        info = self._get_cached_heygen_info(obj)
        if info and info.get('preview_image_url'):
            return ensure_https(info.get('preview_image_url'))
        return ensure_https(obj.heygen_preview_url) if obj.heygen_preview_url else None

    def get_heygen_image_urls(self, obj):
        info = self._get_cached_heygen_info(obj)
        if info and info.get('image_urls'):
            return [ensure_https(u) for u in info.get('image_urls') if u]
        urls = obj.heygen_image_urls or []
        return [ensure_https(u) for u in urls if u]

    def get_heygen_generated_image(self, obj):
        """Return the locally generated cartoon avatar image as an absolute URL.
        This is available immediately after upload — unlike heygen_image_urls
        which requires waiting for HeyGen async processing (2-10 mins).
        Priority: heygen_preview_url (HeyGen CDN) → heygen_image_urls[0] → local avatar file.
        """
        request = self.context.get('request')

        # 1. Use HeyGen CDN preview URL if already available
        if obj.heygen_preview_url:
            return ensure_https(obj.heygen_preview_url)

        # 2. Use first URL from persisted heygen_image_urls list
        if obj.heygen_image_urls:
            urls = obj.heygen_image_urls if isinstance(obj.heygen_image_urls, list) else []
            if urls and urls[0]:
                return ensure_https(urls[0])

        # 3. Fall back to the locally saved avatar image (cartoon converted by PIL)
        if obj.avatar:
            url = (obj.avatar.url or '').strip().strip('"').strip("'")
            if url:
                return build_absolute_https_uri(request, url)

        return None


class VoiceSampleList(serializers.ModelSerializer):
    voice_sample = serializers.SerializerMethodField()

    class Meta:
        model = models.VoiceSample
        fields = ['id', 'voice_sample', 'created_at']

    def get_voice_sample(self, obj):
        if not obj.voice_sample:
            return None
        request = self.context.get('request')
        url = (obj.voice_sample.url or '').strip().strip('"').strip("'")
        return build_absolute_https_uri(request, url)


class UploadAvatarSerializer(serializers.Serializer):
    avatar = serializers.ImageField(required=True, help_text="Image file to upload")
    is_cartoon = serializers.BooleanField(required=False, default=False, help_text="If true, treat uploaded image as cartoon (skips local cartoonisation)")


class UploadAvatarAndVoiceSerializer(serializers.Serializer):
    avatar_id = serializers.IntegerField(required=False)
    avatar = serializers.ImageField(required=False)
    is_cartoon = serializers.BooleanField(required=False, default=False)
    voice_sample = serializers.FileField()

    def validate(self, data):
        if not data.get('avatar_id') and not data.get('avatar'):
            raise serializers.ValidationError("Provide either avatar_id or avatar file.")
        return data


def find_local_video_by_timestamp(created_at) -> Path | None:
    if not created_at:
        return None
    
    if isinstance(created_at, str):
        try:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except Exception:
            return None
    else:
        dt = created_at

    dt_utc = dt.astimezone(timezone.utc)
    
    # scan both test_output and media/generated_videos
    scan_dirs = [Path("test_output"), Path(settings.MEDIA_ROOT) / "generated_videos"]
    
    best_match = None
    min_diff = 30.0  # Allow up to 30 seconds difference
    
    for folder in scan_dirs:
        if not folder.exists():
            continue
        for file in folder.glob("final_video_*.mp4"):
            match = re.search(r"final_video_(\d{8})_(\d{6})\.mp4", file.name)
            if match:
                date_str, time_str = match.groups()
                try:
                    file_dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
                    diff = (dt_utc - file_dt).total_seconds()
                    if 0 <= diff < min_diff:
                        min_diff = diff
                        best_match = file
                except Exception:
                    continue
                    
    return best_match


def get_or_fix_video_url(video_url: str, created_at=None) -> str:
    if not video_url:
        return ""

    media_root = Path(settings.MEDIA_ROOT)
    generated_dir = media_root / "generated_videos"
    generated_dir.mkdir(parents=True, exist_ok=True)

    # 1. If it is a remote URL starting with http/https
    if video_url.startswith(("http://", "https://")):
        if "heygen" in video_url or "aws_pacific" in video_url:
            local_file = find_local_video_by_timestamp(created_at)
            if local_file and local_file.exists():
                # Copy it to media/generated_videos if not already there
                dest_path = generated_dir / local_file.name
                if not dest_path.exists():
                    shutil.copy2(local_file, dest_path)
                return f"{settings.MEDIA_URL}generated_videos/{local_file.name}"
        return ensure_https(video_url)

    # 2. Absolute local path (e.g. /home/foysal_munna/...)
    if video_url.startswith("/"):
        local_path = Path(video_url)
        if local_path.is_absolute() and local_path.exists() and local_path.is_file():
            if not str(local_path.resolve()).startswith(str(media_root.resolve())):
                dest_path = generated_dir / local_path.name
                shutil.copy2(local_path, dest_path)
                return f"{settings.MEDIA_URL}generated_videos/{local_path.name}"
            else:
                rel_path = local_path.resolve().relative_to(media_root.resolve())
                return f"{settings.MEDIA_URL}{rel_path}"

    # 3. Already relative media URL, e.g. /media/generated_videos/...
    if video_url.startswith(settings.MEDIA_URL):
        return video_url

    return video_url


class GeneratedVideoSerializer(serializers.ModelSerializer):
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = models.GeneratedVideo
        fields = ['id', 'avatar', 'video_url', 'status', 'error_message', 'created_at']

    def get_video_url(self, obj):
        url = obj.video_url
        if not url:
            return None
        fixed_url = get_or_fix_video_url(url, created_at=obj.created_at)
        
        if fixed_url != url:
            obj.video_url = fixed_url
            try:
                obj.save(update_fields=['video_url'])
            except Exception:
                pass
                
        request = self.context.get('request')
        if fixed_url.startswith(settings.MEDIA_URL):
            return build_absolute_https_uri(request, fixed_url)
        return ensure_https(fixed_url)


class TextToVideoSerializer(serializers.Serializer):
    text = serializers.CharField(required=True)
    avatar_id = serializers.IntegerField(required=False, allow_null=True)
    is_cartoon = serializers.BooleanField(required=False, default=False)
    voice_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
