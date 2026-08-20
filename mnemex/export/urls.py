from django.urls import path

from mnemex.export import views

app_name = "export"

urlpatterns = [
    path("", views.review_queue, name="review-queue"),
    path("reviews/<uuid:assertion_id>/", views.review_detail, name="review-detail"),
    path("snapshots/new/", views.snapshot_create, name="snapshot-create"),
    path("snapshots/<uuid:snapshot_id>/", views.snapshot_detail, name="snapshot-detail"),
    path(
        "snapshots/<uuid:snapshot_id>/download.json",
        views.snapshot_download,
        name="snapshot-download",
    ),
    path(
        "snapshots/<uuid:snapshot_id>/exclusions.csv",
        views.snapshot_exclusions_download,
        name="snapshot-exclusions-download",
    ),
]
