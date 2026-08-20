from django.urls import path

from mnemex.career import views

app_name = "career"

urlpatterns = [
    path("identity/", views.identity_queue, name="identity-queue"),
    path("identity/<uuid:case_id>/", views.identity_detail, name="identity-detail"),
]
