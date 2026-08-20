from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

_LOCAL_TEST_HOSTS = {"", "localhost", "127.0.0.1", "::1"}


def database_config_from_url(url: str) -> dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("MNEMEX requires a PostgreSQL DATABASE_URL")
    if not parsed.hostname or not parsed.path.lstrip("/"):
        raise ValueError("DATABASE_URL must include a host and database name")

    query = parse_qs(parsed.query)
    config: dict[str, Any] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 5},
    }
    if "sslmode" in query:
        config["OPTIONS"]["sslmode"] = query["sslmode"][-1]
    return config


def assert_safe_test_database(config: dict[str, Any]) -> None:
    engine = str(config.get("ENGINE", ""))
    if engine == "django.db.backends.sqlite3":
        return
    host = str(config.get("HOST", "")).lower()
    name = str(config.get("NAME", "")).lower()
    if engine != "django.db.backends.postgresql" or host not in _LOCAL_TEST_HOSTS:
        raise RuntimeError("refusing non-local test database")
    if name and "test" not in name:
        raise RuntimeError("refusing PostgreSQL test database without 'test' in its name")
