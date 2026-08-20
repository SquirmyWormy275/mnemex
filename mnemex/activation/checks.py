from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security, deploy=True)
def production_privilege_must_remain_disabled(
    app_configs: Any,
    **kwargs: Any,
) -> list[Error]:
    """Reject the one forbidden state this implementation must never activate."""

    settings_module = str(getattr(settings, "SETTINGS_MODULE", ""))
    enabled = bool(getattr(settings, "MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED", False))
    if settings_module.endswith(".production") and enabled:
        return [
            Error(
                "Production privileged authorization must remain hard-disabled.",
                hint=(
                    "Activation reports are evidence only. They cannot authorize "
                    "privileged production access."
                ),
                id="mnemex.activation.E001",
            )
        ]
    return []
