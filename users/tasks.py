import os
import time
import logging
from pathlib import Path
from celery import shared_task
from django.conf import settings
from ai_file import test_ai
from users import models

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def generate_video_task(self, video_id, avatar_input_path, voice_sample_path, cartoon_style=False):
    logger.info(f"Starting generate_video_task for video_id={video_id}")
    try:
        video_obj = models.GeneratedVideo.objects.get(id=video_id)
    except models.GeneratedVideo.DoesNotExist:
        logger.error(f"GeneratedVideo with id={video_id} does not exist.")
        return

    try:
        video_obj.status = 'processing'
        video_obj.save(update_fields=['status'])

        # Generate video using test_ai helper
        video_url = test_ai.test_ai(avatar_input_path, voice_sample_path, cartoon_style=cartoon_style)
        if not video_url:
            raise Exception("Video generation failed (returned None).")

        video_obj.video_url = video_url
        video_obj.status = 'completed'
        video_obj.save(update_fields=['video_url', 'status'])
        logger.info(f"Successfully completed generate_video_task for video_id={video_id}")

        # Cleanup temp files if they were uploaded
        for path in (avatar_input_path, voice_sample_path):
            if path and "/temp/" in str(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"Could not remove temp file {path}: {e}")

    except Exception as e:
        logger.error(f"Error in generate_video_task for video_id={video_id}: {e}", exc_info=True)
        video_obj.status = 'failed'
        err_str = str(e)
        if any(k in err_str.lower() for k in ["quota", "credit", "payment", "limit", "exhausted"]):
            video_obj.error_message = "Heygen quota is finished"
        else:
            video_obj.error_message = err_str
        video_obj.save(update_fields=['status', 'error_message'])


@shared_task(bind=True, max_retries=3)
def text_to_video_task(self, video_id, text, avatar_id, is_cartoon, voice_id):
    logger.info(f"Starting text_to_video_task for video_id={video_id}")
    try:
        video_obj = models.GeneratedVideo.objects.get(id=video_id)
    except models.GeneratedVideo.DoesNotExist:
        logger.error(f"GeneratedVideo with id={video_id} does not exist.")
        return

    try:
        video_obj.status = 'processing'
        video_obj.save(update_fields=['status'])

        # 1) Convert text -> speech via ElevenLabs
        tts_name = f"tts_{int(time.time())}.mp3"
        tts_path, tts_err = test_ai.elevenlabs_tts_noninteractive(text, voice_id=voice_id, out_name=tts_name)
        if tts_err:
            raise Exception(f"TTS conversion failed: {tts_err}")
        if not tts_path:
            raise Exception("TTS conversion failed (returned None path).")

        # 2) Upload audio to HeyGen
        audio_asset_id = test_ai._upload_audio_to_heygen(Path(tts_path))
        if not audio_asset_id:
            raise Exception("Failed to upload audio to HeyGen.")

        # 3) Determine avatar payload
        avatar_payload = None
        if avatar_id:
            try:
                avatar_obj = models.Avatar.objects.get(id=avatar_id)
                # inside Celery background task, we can safely wait (wait=True)
                if avatar_obj.heygen_avatar_id and (is_cartoon or avatar_obj.is_cartoon):
                    avatar_payload = {
                        "source": "remote",
                        "avatar_id": avatar_obj.heygen_avatar_id,
                        "name": f"avatar_{avatar_obj.id}",
                        "engine": "avatar_iv",
                    }
                else:
                    image_asset_id = test_ai._upload_asset(avatar_obj.avatar.path, test_ai._guess_mime(avatar_obj.avatar.path))
                    if not image_asset_id:
                        raise Exception("Failed to upload avatar asset to HeyGen.")
                    if is_cartoon or avatar_obj.is_cartoon:
                        avatar_payload = test_ai._create_cartoon_avatar(image_asset_id, wait=True)
                    else:
                        avatar_payload = test_ai._create_photo_avatar(image_asset_id, wait=True)
                    
                    if avatar_payload and isinstance(avatar_payload, dict) and avatar_payload.get("avatar_id"):
                        avatar_obj.heygen_avatar_id = avatar_payload.get("avatar_id")
                        avatar_obj.save(update_fields=["heygen_avatar_id"])
            except models.Avatar.DoesNotExist:
                raise Exception(f"Avatar with id={avatar_id} not found.")

        if not avatar_payload:
            preset = test_ai.DEFAULT_AVATARS.get("1")
            avatar_payload = {
                "source": "default",
                "avatar_id": preset["avatar_id"],
                "name": preset["name"],
                "engine": "avatar_iv"
            }

        # 4) Generate video using HeyGen
        video_url = test_ai.generate_video(avatar_payload, audio_asset_id)
        if not video_url:
            raise Exception("Video generation failed on HeyGen.")

        video_obj.video_url = video_url
        video_obj.status = 'completed'
        video_obj.save(update_fields=['video_url', 'status'])
        logger.info(f"Successfully completed text_to_video_task for video_id={video_id}")

        # Cleanup tts audio path
        try:
            if tts_path and os.path.exists(tts_path):
                os.remove(tts_path)
        except Exception as e:
            logger.warning(f"Could not remove tts file {tts_path}: {e}")

    except Exception as e:
        logger.error(f"Error in text_to_video_task for video_id={video_id}: {e}", exc_info=True)
        video_obj.status = 'failed'
        err_str = str(e)
        if any(k in err_str.lower() for k in ["quota", "credit", "payment", "limit", "exhausted"]):
            video_obj.error_message = "Heygen quota is finished"
        else:
            video_obj.error_message = err_str
        video_obj.save(update_fields=['status', 'error_message'])
