from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from django.db import transaction

T = TypeVar("T")


def run_in_transaction(operation: Callable[[], T]) -> T:
    """Run one service operation inside the server-owned commit boundary."""
    with transaction.atomic():
        return operation()
