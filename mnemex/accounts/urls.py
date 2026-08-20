from django.urls import path

from mnemex.accounts import views

app_name = "accounts"

urlpatterns = [
    path("action/step-up/", views.action_step_up, name="action-step-up"),
    path(
        "invitations/<uuid:request_id>/accept/",
        views.invitation_accept,
        name="invitation-accept",
    ),
    path("security/operations/", views.security_operations, name="security-operations"),
    path(
        "security/operations/<uuid:request_id>/",
        views.security_operation_detail,
        name="security-operation-detail",
    ),
]
