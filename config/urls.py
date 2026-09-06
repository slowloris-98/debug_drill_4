from django.contrib import admin
from django.urls import include, path

from dashboard import views as dashboard_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.urls")),
    path("", dashboard_views.shortlist_page, name="shortlist"),
    path("releases/", dashboard_views.releases_page, name="releases"),
    path("webhooks/", dashboard_views.webhooks_page, name="webhooks"),
]
