from pathlib import Path
import time

from django.core.files import File
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from . import models, serializers
from ai_file import test_ai


def _build_absolute_video_url(request, video_url: str) -> str:
    if not video_url:
        return video_url
    if video_url.startswith("http://") or video_url.startswith("https://"):
        return video_url
    if video_url.startswith("/"):
        return request.build_absolute_uri(video_url)
    base = request.build_absolute_uri("/").rstrip("/")
    return f"{base}/api{video_url}"




def _get_heygen_avatar_payload(avatar_obj, is_cartoon: bool):
    if avatar_obj.heygen_avatar_id and (is_cartoon or avatar_obj.is_cartoon):
        return {
            "source": "remote",
            "avatar_id": avatar_obj.heygen_avatar_id,
            "name": f"avatar_{avatar_obj.id}",
            "engine": "avatar_iv",
        }

    image_asset_id = test_ai._upload_asset(avatar_obj.avatar.path, test_ai._guess_mime(avatar_obj.avatar.path))
    if not image_asset_id:
        return None

    if is_cartoon or avatar_obj.is_cartoon:
        payload = test_ai._create_cartoon_avatar(image_asset_id)
    else:
        payload = test_ai._create_photo_avatar(image_asset_id)

    if payload and isinstance(payload, dict) and payload.get("avatar_id"):
        avatar_obj.heygen_avatar_id = payload.get("avatar_id")
        avatar_obj.save(update_fields=["heygen_avatar_id"])

    return payload


class UserProfileView(generics.CreateAPIView, generics.RetrieveUpdateDestroyAPIView):
    queryset = models.User.objects.all()
    serializer_class = serializers.UserSerializer  
    permission_classes = [AllowAny]  



class UploadAvatarView(generics.CreateAPIView):
    queryset = models.Avatar.objects.all()
    serializer_class = serializers.AvatarList 
    permission_classes = [AllowAny]  


    def post(self, request, *args, **kwargs):
        # Skip serializer validation here because AvatarList serializer
        # is read-only for `avatar` (returns absolute URL). Handle
        # the uploaded file directly from request.FILES.
        # Debug logging for terminal: print caller info and uploaded file details
        try:
            remote = request.META.get('REMOTE_ADDR') or request.META.get('HTTP_X_FORWARDED_FOR')
        except Exception:
            remote = 'unknown'
        print(f"[image-upload-to-avatar] called from: {remote}")
        print(f"[image-upload-to-avatar] POST keys: {list(request.data.keys())}")
        print(f"[image-upload-to-avatar] FILES keys: {list(request.FILES.keys())}")
        if 'avatar' in request.FILES:
            f = request.FILES['avatar']
            try:
                size = f.size
            except Exception:
                size = 'unknown'
            print(f"[image-upload-to-avatar] avatar filename={getattr(f, 'name', None)} size={size}")

        # Extract uploaded file and flags directly from request
        avatar = request.FILES.get('avatar')
        raw_is_cartoon = request.data.get('is_cartoon', False)
        if isinstance(raw_is_cartoon, str):
            is_cartoon = raw_is_cartoon.lower() in ('1', 'true', 'yes', 'on')
        else:
            is_cartoon = bool(raw_is_cartoon)

        if not avatar:
            return Response({"error": "Avatar file is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not is_cartoon:
            # Convert uploaded file to cartoon locally, then save the generated file
            cartoon_path = test_ai.cartoon_image_generator(avatar)
            if not cartoon_path:
                return Response({"error": "Cartoon image generation failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            with open(cartoon_path, 'rb') as f:
                avatar_instance = models.Avatar.objects.create(is_cartoon=True)
                avatar_instance.avatar.save(Path(cartoon_path).name, File(f), save=True)
        else:
            # Save the uploaded file directly as a cartoon avatar
            avatar_instance = models.Avatar.objects.create(avatar=avatar, is_cartoon=True)

        # After saving locally, upload the image to HeyGen and create a cartoon avatar there
        heygen_avatar = None
        try:
            img_path = avatar_instance.avatar.path
            mime = test_ai._guess_mime(img_path)
            image_asset_id = test_ai._upload_asset(img_path, mime)
            if image_asset_id:
                # Create cartoon avatar on HeyGen using uploaded asset
                heygen_avatar = test_ai._create_cartoon_avatar(image_asset_id, avatar_name=f"avatar_{avatar_instance.id}")
                if heygen_avatar and isinstance(heygen_avatar, dict) and heygen_avatar.get("avatar_id"):
                    avatar_instance.heygen_avatar_id = heygen_avatar.get("avatar_id")
                    avatar_instance.save(update_fields=["heygen_avatar_id"])
        except Exception as e:
            print(f"[image-upload-to-avatar] HeyGen avatar creation failed: {e}")

        # Return using serializer so output matches AvatarList format (absolute URL)
        out_serializer = serializers.AvatarList(avatar_instance, context={"request": request})
        data = out_serializer.data
        if heygen_avatar:
            data["heygen_avatar"] = heygen_avatar
        else:
            data["heygen_avatar"] = None
        return Response(data, status=status.HTTP_201_CREATED)



class GenerateVideoView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = serializers.UploadAvatarAndVoiceSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        avatar_id = serializer.validated_data.get('avatar_id')
        avatar_file = serializer.validated_data.get('avatar')
        is_cartoon = serializer.validated_data.get('is_cartoon', False)
        voice_sample = serializer.validated_data.get('voice_sample')

        if not voice_sample:
            return Response({"error": "Voice sample is required."}, status=status.HTTP_400_BAD_REQUEST)
        

        cartoon_style = False
        if avatar_id:
            try:
                avatar_obj = models.Avatar.objects.get(id=avatar_id)
            except models.Avatar.DoesNotExist:
                return Response({"error": "Avatar with the given id does not exist."}, status=status.HTTP_400_BAD_REQUEST)
            avatar_input = avatar_obj.avatar.path
            if avatar_obj.is_cartoon or is_cartoon:
                cartoon_style = True
        else:
            avatar_input = avatar_file
            if not is_cartoon:
                cartoon_image = test_ai.cartoon_image_generator(avatar_input)
                if not cartoon_image:
                    return Response({"error": "Cartoon image generation failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                avatar_input = cartoon_image
                cartoon_style = True
            else:
                cartoon_style = True




        video_url = test_ai.test_ai(avatar_input, voice_sample, cartoon_style=cartoon_style)
        if not video_url:
            return Response({"error": "Video generation failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        full_url = _build_absolute_video_url(request, video_url)
        generated = models.GeneratedVideo.objects.create(avatar_id=avatar_id if avatar_id else None, video_url=full_url)
        return Response({"message": "Video generated successfully.", "id": generated.id, "video_url": full_url}, status=status.HTTP_200_OK)








class GeneratedVedioList(generics.ListAPIView):
    queryset = models.GeneratedVideo.objects.all()
    serializer_class = serializers.GeneratedVideoSerializer
    permission_classes = [AllowAny]


class AvatarListView(generics.ListAPIView):
    queryset = models.Avatar.objects.all().order_by('-created_at')
    serializer_class = serializers.AvatarList
    permission_classes = [AllowAny]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx.update({"request": self.request})
        return ctx


class TextToVideoView(generics.CreateAPIView):
    """POST endpoint: {"text": "...", "avatar_id": <optional>, "is_cartoon": <optional>, "voice_id": <optional>}"""
    permission_classes = [AllowAny]
    serializer_class = serializers.TextToVideoSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data.get('text')
        avatar_id = serializer.validated_data.get('avatar_id')
        is_cartoon = serializer.validated_data.get('is_cartoon', False)
        voice_id = serializer.validated_data.get('voice_id')

        # 1) Convert text -> speech via ElevenLabs
        tts_path, tts_err = test_ai.elevenlabs_tts_noninteractive(text, voice_id=voice_id, out_name=f"tts_{int(time.time())}.mp3")
        if tts_err:
            return Response({"error": "TTS conversion failed.", "detail": tts_err}, status=status.HTTP_502_BAD_GATEWAY)
        if not tts_path:
            return Response({"error": "TTS conversion failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 2) Upload audio to HeyGen
        audio_asset_id = test_ai._upload_audio_to_heygen(Path(tts_path))
        if not audio_asset_id:
            return Response({"error": "Failed to upload audio to HeyGen."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 3) Determine avatar payload
        avatar_payload = None
        # If avatar_id provided and is numeric, treat it as DB Avatar
        if avatar_id:
            try:
                aid = int(avatar_id)
                avatar_obj = models.Avatar.objects.get(id=aid)
                avatar_payload = _get_heygen_avatar_payload(avatar_obj, is_cartoon)
                if not avatar_payload:
                    return Response({"error": "Failed to prepare HeyGen avatar payload."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except ValueError:
                avatar_payload = None
            except models.Avatar.DoesNotExist:
                return Response({"error": "Avatar not found."}, status=status.HTTP_400_BAD_REQUEST)

        # If no DB avatar provided, fall back to default preset avatar
        if not avatar_payload:
            # pick preset 1
            preset = test_ai.DEFAULT_AVATARS.get("1")
            avatar_payload = {"source": "default", "avatar_id": preset["avatar_id"], "name": preset["name"], "engine": "avatar_iv"}

        # 4) Generate video using HeyGen
        video_url = test_ai.generate_video(avatar_payload, audio_asset_id)
        if not video_url:
            return Response({"error": "Video generation failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 5) Return absolute URL
        from django.shortcuts import resolve_url
        full_url = request.build_absolute_uri(video_url) if not video_url.startswith('http') else video_url
        generated = models.GeneratedVideo.objects.create(avatar_id=avatar_id if avatar_id else None, video_url=full_url)
        return Response({"id": generated.id, "video_url": full_url}, status=status.HTTP_200_OK)