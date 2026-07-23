from pathlib import Path
import time

from django.core.files import File
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from . import models, serializers, tasks
from ai_file import test_ai

from rest_framework.parsers import MultiPartParser, FormParser

try:
    from drf_yasg.utils import swagger_auto_schema
    from drf_yasg import openapi
    HAS_YASG = True
except ImportError:
    HAS_YASG = False
    class openapi:
        IN_FORM = 'form'
        TYPE_FILE = 'file'
        TYPE_BOOLEAN = 'boolean'
        class Parameter:
            def __init__(self, *args, **kwargs):
                pass
    def swagger_auto_schema(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

#hello

def _build_absolute_video_url(request, video_url: str) -> str:
    if not video_url:
        return video_url
    if video_url.startswith("http://") or video_url.startswith("https://"):
        return serializers.ensure_https(video_url)
    if video_url.startswith("/"):
        return serializers.build_absolute_https_uri(request, video_url)
    base = request.build_absolute_uri("/").rstrip("/")
    return serializers.ensure_https(f"{base}/api{video_url}")


def _save_uploaded_file_temp(uploaded_file, prefix="file") -> str:
    import os
    import time
    from pathlib import Path
    from django.conf import settings
    
    temp_dir = Path(settings.MEDIA_ROOT) / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    ext = Path(uploaded_file.name).suffix
    filename = f"{prefix}_{int(time.time())}_{os.urandom(4).hex()}{ext}"
    dest_path = temp_dir / filename
    
    with open(dest_path, 'wb+') as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)
            
    return str(dest_path)




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
        payload = test_ai._create_cartoon_avatar(image_asset_id, wait=False)
    else:
        payload = test_ai._create_photo_avatar(image_asset_id, wait=False)

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
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_id="image_upload_to_avatar",
        operation_description=(
            "Upload an image file and generate a HeyGen cartoon avatar.\n\n"
            "Steps:\n"
            "1. Converts the image to a cartoon locally (via PIL).\n"
            "2. Uploads the cartoon image to HeyGen asset manager.\n"
            "3. Dispatches HeyGen avatar creation asynchronously.\n"
            "4. Returns the locally generated cartoon image immediately as `heygen_generated_image`."
        ),
        manual_parameters=[
            openapi.Parameter(
                name="avatar",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                required=True,
                description="Avatar photo/image file to upload"
            ),
            openapi.Parameter(
                name="is_cartoon",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_BOOLEAN,
                required=False,
                default=False,
                description="If true, skip PIL cartoon conversion (treat input as already cartoonised)"
            )
        ],
        responses={
            201: serializers.AvatarList,
            400: "Bad Request (e.g. missing avatar)",
            500: "Internal Server Error (e.g. PIL cartoon generation failed)"
        },
        tags=["Avatar"]
    )
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
        heygen_info = None
        try:
            img_path = avatar_instance.avatar.path
            mime = test_ai._guess_mime(img_path)
            image_asset_id = test_ai._upload_asset(img_path, mime)
            if image_asset_id:
                # Create cartoon avatar on HeyGen using uploaded asset with long-polling (wait=True)
                heygen_avatar = test_ai._create_cartoon_avatar(image_asset_id, avatar_name=f"avatar_{avatar_instance.id}", wait=True)
                if heygen_avatar and isinstance(heygen_avatar, dict) and heygen_avatar.get("avatar_id"):
                    avatar_instance.heygen_avatar_id = heygen_avatar.get("avatar_id")
                    avatar_instance.save(update_fields=["heygen_avatar_id"])

                    # Fetch the completed avatar info from HeyGen
                    try:
                        heygen_info = test_ai.fetch_heygen_avatar_info(avatar_instance.heygen_avatar_id)
                        if heygen_info:
                            preview = heygen_info.get("preview_image_url") or heygen_avatar.get("preview_url") or ""
                            img_urls = heygen_info.get("image_urls") or []
                            if not img_urls and preview:
                                img_urls = [preview]
                            # Persist to DB since it's now ready
                            if preview or img_urls:
                                avatar_instance.heygen_preview_url = preview
                                avatar_instance.heygen_image_urls = img_urls
                                avatar_instance.save(update_fields=["heygen_preview_url", "heygen_image_urls"])
                    except Exception as fe:
                        print(f"[image-upload-to-avatar] fetch_heygen_avatar_info failed: {fe}")
        except Exception as e:
            print(f"[image-upload-to-avatar] HeyGen avatar creation failed: {e}")

        # Return using serializer so output matches AvatarList format (absolute URL)
        # Refresh from DB so serializer sees persisted heygen_preview_url / heygen_image_urls
        avatar_instance.refresh_from_db()
        out_serializer = serializers.AvatarList(avatar_instance, context={"request": request})
        data = out_serializer.data

        # Inject heygen_avatar context + ensure image fields are populated from heygen_info
        data["heygen_avatar"] = heygen_avatar or None

        # If serializer returned empty urls but we have data from heygen_info, patch them in
        if heygen_info:
            if not data.get("heygen_image_urls") and heygen_info.get("image_urls"):
                data["heygen_image_urls"] = [serializers.ensure_https(u) for u in heygen_info["image_urls"] if u]
            if not data.get("heygen_preview_url") and heygen_info.get("preview_image_url"):
                data["heygen_preview_url"] = serializers.ensure_https(heygen_info["preview_image_url"])
            if not data.get("heygen_avatar_info"):
                data["heygen_avatar_info"] = heygen_info

        # Ensure heygen_generated_image is always present:
        # prioritise HeyGen CDN preview → first image_url → local avatar file
        if not data.get("heygen_generated_image"):
            generated_img = (
                data.get("heygen_preview_url")
                or (data.get("heygen_image_urls") or [None])[0]
                or data.get("avatar")
            )
            data["heygen_generated_image"] = serializers.ensure_https(generated_img)

        return Response(data, status=status.HTTP_201_CREATED)



class GenerateVideoView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = serializers.UploadAvatarAndVoiceSerializer
    parser_classes = [MultiPartParser, FormParser]

    @swagger_auto_schema(
        operation_id="generate_video",
        operation_description="Generate video from uploaded avatar image (or avatar_id) and voice sample",
        manual_parameters=[
            openapi.Parameter(
                name="voice_sample",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                required=True,
                description="Audio/voice sample file"
            ),
            openapi.Parameter(
                name="avatar",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                required=False,
                description="Avatar image file (if avatar_id is not provided)"
            ),
            openapi.Parameter(
                name="avatar_id",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="ID of an existing avatar (if avatar file is not provided)"
            ),
            openapi.Parameter(
                name="is_cartoon",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_BOOLEAN,
                required=False,
                default=False,
                description="Whether to treat/convert avatar as a cartoon style"
            )
        ],
        responses={
            202: "Accepted (Video generation started in background)",
            400: "Bad Request"
        },
        tags=["Video"]
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        avatar_id = serializer.validated_data.get('avatar_id')
        avatar_file = serializer.validated_data.get('avatar')
        is_cartoon = serializer.validated_data.get('is_cartoon', False)
        voice_sample = serializer.validated_data.get('voice_sample')

        if not voice_sample:
            return Response({"error": "Voice sample is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Save voice sample to temp path so celery task can access it
        voice_sample_path = _save_uploaded_file_temp(voice_sample, prefix="voice")

        cartoon_style = False
        if avatar_id:
            try:
                avatar_obj = models.Avatar.objects.get(id=avatar_id)
            except models.Avatar.DoesNotExist:
                return Response({"error": "Avatar with the given id does not exist."}, status=status.HTTP_400_BAD_REQUEST)
            avatar_input_path = avatar_obj.avatar.path
            if avatar_obj.is_cartoon or is_cartoon:
                cartoon_style = True
        else:
            if not avatar_file:
                return Response({"error": "Provide either avatar_id or avatar file."}, status=status.HTTP_400_BAD_REQUEST)
            
            # Save uploaded avatar to temp path
            avatar_input_path = _save_uploaded_file_temp(avatar_file, prefix="avatar")
            if not is_cartoon:
                cartoon_image = test_ai.cartoon_image_generator(avatar_input_path)
                if not cartoon_image:
                    return Response({"error": "Cartoon image generation failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                avatar_input_path = cartoon_image
                cartoon_style = True
            else:
                cartoon_style = True

        # Create GeneratedVideo record immediately in 'processing' status
        generated = models.GeneratedVideo.objects.create(
            avatar_id=avatar_id if avatar_id else None,
            status='processing'
        )

        # Trigger task asynchronously (non-blocking, background execution)
        try:
            tasks.generate_video_task.delay(
                generated.id,
                avatar_input_path,
                voice_sample_path,
                cartoon_style=cartoon_style
            )
        except Exception:
            import threading
            threading.Thread(
                target=tasks.generate_video_task,
                args=(generated.id, avatar_input_path, voice_sample_path),
                kwargs={"cartoon_style": cartoon_style}
            ).start()

        video_data = serializers.GeneratedVideoSerializer(generated, context={"request": request}).data

        return Response({
            "message": "Video generation request accepted and is processing.",
            "id": generated.id,
            "status": "processing",
            "hygen_video": video_data,
            "heygen_video": video_data
        }, status=status.HTTP_202_ACCEPTED)









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

        # Create GeneratedVideo record immediately in 'processing' status
        generated = models.GeneratedVideo.objects.create(
            avatar_id=avatar_id if avatar_id else None,
            status='processing'
        )

        # Trigger task asynchronously (non-blocking, background execution)
        try:
            tasks.text_to_video_task.delay(
                generated.id,
                text,
                avatar_id,
                is_cartoon,
                voice_id
            )
        except Exception:
            import threading
            threading.Thread(
                target=tasks.text_to_video_task,
                args=(generated.id, text, avatar_id, is_cartoon, voice_id)
            ).start()

        video_data = serializers.GeneratedVideoSerializer(generated, context={"request": request}).data

        return Response({
            "message": "Video generation request accepted and is processing.",
            "id": generated.id,
            "status": "processing",
            "hygen_video": video_data,
            "heygen_video": video_data
        }, status=status.HTTP_202_ACCEPTED)



class VideoStatusView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = serializers.GeneratedVideoSerializer
    queryset = models.GeneratedVideo.objects.all()

    @swagger_auto_schema(
        operation_id="video_status",
        operation_description="Check video generation status ('processing', 'completed', 'failed') and get HeyGen video URL using video ID.",
        manual_parameters=[
            openapi.Parameter(
                name="id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="ID of the generated video"
            ),
            openapi.Parameter(
                name="video_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="ID of the generated video (alias for id)"
            ),
        ],
        responses={
            200: "Video status details",
            400: "Bad Request (missing video ID)",
            404: "Video not found"
        },
        tags=["Video"]
    )
    def get(self, request, id=None, pk=None, *args, **kwargs):
        v_id = id or pk or request.query_params.get('id') or request.query_params.get('video_id')
        if not v_id:
            return Response(
                {"error": "Video ID is required. Pass ID in URL path (e.g. /api/video-status/1/) or query parameter (e.g. /api/video-status/?id=1)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            video_obj = models.GeneratedVideo.objects.get(id=v_id)
        except (models.GeneratedVideo.DoesNotExist, ValueError):
            return Response(
                {"error": f"Video with ID '{v_id}' not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        video_data = serializers.GeneratedVideoSerializer(video_obj, context={"request": request}).data
        video_url = serializers.ensure_https(video_data.get('video_url') or "")

        if video_obj.status == 'completed':
            message = "Video generated successfully."
        elif video_obj.status == 'processing':
            message = "Video is currently processing."
        else:
            if video_obj.error_message and any(k in video_obj.error_message.lower() for k in ["quota", "credit", "payment", "limit", "exhausted"]):
                message = "Heygen quota is finished"
            else:
                message = video_obj.error_message or "Video generation failed."

        return Response({
            "message": message,
            "id": video_obj.id,
            "status": video_obj.status,
            "error_message": video_obj.error_message or (message if "quota" in message.lower() else None),
            "hygen_url": video_url,
            "heygen_url": video_url,
            "video_url": video_url,
            "hygen_video": video_data,
            "heygen_video": video_data
        }, status=status.HTTP_200_OK)


class DeleteAvatarView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    queryset = models.Avatar.objects.all()

    @swagger_auto_schema(
        operation_id="delete_avatar",
        operation_description="Delete an avatar by ID.",
        manual_parameters=[
            openapi.Parameter(
                name="id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="ID of the avatar to delete"
            ),
        ],
        responses={
            200: "Avatar deleted successfully",
            400: "Bad Request (missing avatar ID)",
            404: "Avatar not found"
        },
        tags=["Avatar"]
    )
    def delete(self, request, id=None, pk=None, *args, **kwargs):
        avatar_id = id or pk or request.query_params.get('id') or request.query_params.get('avatar_id') or (request.data.get('id') if isinstance(request.data, dict) else None)
        if not avatar_id:
            return Response(
                {"error": "Avatar ID is required. Pass ID in URL path (e.g. /api/delete-avatar/1/) or query parameter (e.g. /api/delete-avatar/?id=1)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            avatar_obj = models.Avatar.objects.get(id=avatar_id)
        except (models.Avatar.DoesNotExist, ValueError):
            return Response(
                {"error": f"Avatar with ID '{avatar_id}' not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            if avatar_obj.avatar:
                avatar_obj.avatar.delete(save=False)
        except Exception as e:
            print(f"[delete-avatar] Error deleting avatar file: {e}")

        avatar_obj.delete()
        return Response(
            {"message": "Avatar deleted successfully.", "id": int(avatar_id)},
            status=status.HTTP_200_OK
        )


class DeleteVideoView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    queryset = models.GeneratedVideo.objects.all()

    @swagger_auto_schema(
        operation_id="delete_video",
        operation_description="Delete a generated video by ID.",
        manual_parameters=[
            openapi.Parameter(
                name="id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=False,
                description="ID of the video to delete"
            ),
        ],
        responses={
            200: "Video deleted successfully",
            400: "Bad Request (missing video ID)",
            404: "Video not found"
        },
        tags=["Video"]
    )
    def delete(self, request, id=None, pk=None, *args, **kwargs):
        video_id = id or pk or request.query_params.get('id') or request.query_params.get('video_id') or (request.data.get('id') if isinstance(request.data, dict) else None)
        if not video_id:
            return Response(
                {"error": "Video ID is required. Pass ID in URL path (e.g. /api/delete-video/1/) or query parameter (e.g. /api/delete-video/?id=1)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            video_obj = models.GeneratedVideo.objects.get(id=video_id)
        except (models.GeneratedVideo.DoesNotExist, ValueError):
            return Response(
                {"error": f"Video with ID '{video_id}' not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        video_obj.delete()
        return Response(
            {"message": "Video deleted successfully.", "id": int(video_id)},
            status=status.HTTP_200_OK
        )