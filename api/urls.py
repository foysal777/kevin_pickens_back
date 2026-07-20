from django.urls import path, include
from users import views as user_views


urlpatterns = [

    path("user-profile/", user_views.UserProfileView.as_view(), name="user-profile"),
    path("image-upload-to-avatar/", user_views.UploadAvatarView.as_view(), name="image-upload-to-avatar"),
    path("avatar-list/", user_views.AvatarListView.as_view(), name="avatar-list"),
    path("generate-video/", user_views.GenerateVideoView.as_view(), name="generate-video"),
    path("video-status/", user_views.VideoStatusView.as_view(), name="video-status"),
    path("video-status/<int:id>/", user_views.VideoStatusView.as_view(), name="video-status-detail"),
    path("text-to-video/", user_views.TextToVideoView.as_view(), name="text-to-video"),
    path("video-list/", user_views.GeneratedVedioList.as_view(), name="video-list"),

]