from django.urls import path

from api import views

urlpatterns = [
    path("results/", views.ScoreReportListView.as_view(), name="result-list"),
    path("results/ingest/", views.ScoreReportIngestView.as_view(), name="result-ingest"),
    path("results/<int:pk>/", views.ScoreReportDetailView.as_view(), name="result-detail"),
    path("webhooks/", views.WebhookEndpointListView.as_view(), name="webhook-list"),
    path("webhooks/<int:pk>/", views.WebhookEndpointDetailView.as_view(), name="webhook-detail"),
    path(
        "shortlists/<int:assessment_id>/",
        views.ShortlistView.as_view(),
        name="shortlist-detail",
    ),
    path("pass-rates/", views.PassRateView.as_view(), name="pass-rates"),
]
