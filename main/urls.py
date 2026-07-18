from django.contrib import admin
from django.urls import path, include, re_path
from django.conf.urls.static import static
from django.conf import settings
from django.views.generic import TemplateView
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi


def get_schema_view_lazy():
    return get_schema_view(
        openapi.Info(
            title="JwalkeyBB API",
            default_version='v1',
            description="Test description",
            terms_of_service="https://www.google.com/policies/terms/",
            contact=openapi.Contact(email="contact@snippets.local"),
            license=openapi.License(name="BSD License"),
        ),
        public=True,
        permission_classes=(permissions.AllowAny,),
    )

schema_view = get_schema_view_lazy()


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')), 
    path('', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui')

]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)




