from django.urls import path

from mnemex.legacy_migration import views

app_name = "legacy_migration"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("upload/", views.upload, name="upload"),
    path("runs/<uuid:run_id>/", views.run_detail, name="run-detail"),
    path("runs/<uuid:run_id>/configure/", views.configure, name="configure"),
    path("runs/<uuid:run_id>/dry-run/", views.dry_run, name="dry-run"),
    path("runs/<uuid:run_id>/approve/", views.approve, name="approve"),
    path("runs/<uuid:run_id>/apply/", views.apply, name="apply"),
    path("runs/<uuid:run_id>/reconciliation.csv", views.report_csv, name="report-csv"),
    path("runs/<uuid:run_id>/withdraw/", views.withdraw, name="withdraw"),
]
