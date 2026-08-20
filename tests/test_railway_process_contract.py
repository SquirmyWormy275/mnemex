from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import override_settings

REPO_ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict[str, object]:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))


def test_one_image_has_no_baked_runtime_secret_and_collects_static_assets() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "mnemex.web.settings.build" in dockerfile
    assert "collectstatic --noinput" in dockerfile
    assert "SECRET_KEY=" not in dockerfile
    assert "DATABASE_URL=" not in dockerfile
    assert "SUPABASE" not in dockerfile


def test_image_context_excludes_tests_fixtures_and_operator_documents() -> None:
    ignored = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert "tests/" in ignored
    assert "docs/" in ignored


def test_web_service_is_the_only_release_migration_owner() -> None:
    web = _json("deploy/railway/web.json")
    worker = _json("deploy/railway/worker.json")

    web_deploy = web["deploy"]
    worker_deploy = worker["deploy"]
    assert isinstance(web_deploy, dict)
    assert isinstance(worker_deploy, dict)

    release = web_deploy["preDeployCommand"]
    assert isinstance(release, str)
    assert "migrate --noinput" in release
    assert "check --deploy" in release
    assert "preDeployCommand" not in worker_deploy

    assert "migrate" not in str(web_deploy["startCommand"])
    assert "migrate" not in str(worker_deploy["startCommand"])


def test_web_and_worker_have_separate_bounded_roles() -> None:
    web = _json("deploy/railway/web.json")["deploy"]
    worker = _json("deploy/railway/worker.json")["deploy"]
    assert isinstance(web, dict)
    assert isinstance(worker, dict)

    assert str(web["startCommand"]).startswith("gunicorn ")
    assert web["healthcheckPath"] == "/health/ready"
    assert web["restartPolicyType"] == "ON_FAILURE"

    assert worker["startCommand"] == "mnemex-worker --supervise"
    assert "healthcheckPath" not in worker
    assert worker["restartPolicyType"] == "ON_FAILURE"


def test_build_settings_are_non_serving_and_production_privilege_stays_disabled() -> None:
    from mnemex.web.settings import build

    assert build.DEBUG is False
    assert build.MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED is False
    assert build.STATIC_ROOT.name == "staticfiles"
    production_source = (REPO_ROOT / "mnemex/web/settings/production.py").read_text(
        encoding="utf-8"
    )
    assert "MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED = False" in production_source


def test_production_serves_fingerprinted_static_assets_from_the_image() -> None:
    from mnemex.web.settings import build

    assert build.STORAGES["staticfiles"]["BACKEND"] == (
        "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "whitenoise" in pyproject
    production_source = (REPO_ROOT / "mnemex/web/settings/production.py").read_text(
        encoding="utf-8"
    )
    assert '"whitenoise.middleware.WhiteNoiseMiddleware"' in production_source


def test_image_static_collection_creates_manifest_and_fingerprint(tmp_path: Path) -> None:
    from mnemex.web.settings import build

    destination = tmp_path / "staticfiles"
    with override_settings(STATIC_ROOT=destination, STORAGES=build.STORAGES):
        call_command("collectstatic", interactive=False, verbosity=0)

    assert (destination / "staticfiles.json").is_file()
    assert list((destination / "results").glob("results-desk.*.css"))


@pytest.mark.parametrize("config_path", ["deploy/railway/web.json", "deploy/railway/worker.json"])
def test_railway_configs_use_the_dockerfile_builder(config_path: str) -> None:
    config = _json(config_path)
    assert config["build"] == {
        "builder": "DOCKERFILE",
        "dockerfilePath": "Dockerfile",
    }
