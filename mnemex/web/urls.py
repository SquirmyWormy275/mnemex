from allauth.account import views as account_views
from django.urls import include, path

from mnemex.partners.views import ingest_result, result_status
from mnemex.web import health

urlpatterns = [
    path("partners/results/ingest", ingest_result, name="show-result-ingest"),
    path("partners/results/status", result_status, name="show-result-status"),
    # Compatibility names keep existing operator templates and bookmarks
    # working while allauth owns the actual staged authentication flow.
    path("accounts/login/", account_views.login, name="login"),
    path("accounts/logout/", account_views.logout, name="logout"),
    path("accounts/", include("mnemex.accounts.urls")),
    path("accounts/", include("allauth.urls")),
    path("results/", include("mnemex.results.urls")),
    path("results/legacy/", include("mnemex.legacy_migration.urls")),
    path("career/", include("mnemex.career.urls")),
    path("exports/", include("mnemex.export.urls")),
    path("health/live", health.live, name="health-live"),
    path("health/ready", health.ready, name="health-ready"),
]
