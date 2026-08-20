from django.urls import path

from mnemex.results import views

app_name = "results"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("starter.csv", views.starter_csv, name="starter-csv"),
    path("mappings/new/", views.mapping_create, name="mapping-create"),
    path("upload/", views.upload, name="upload"),
    path("manual/", views.manual, name="manual"),
    path("runs/<uuid:run_id>/issues.csv", views.run_issues_csv, name="run-issues-csv"),
    path("runs/<uuid:run_id>/", views.run_detail, name="run-detail"),
]
