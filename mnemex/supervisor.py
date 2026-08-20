from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from random import uniform


@dataclass(frozen=True)
class QueueTask:
    """One bounded queue action executed once per supervisor cycle."""

    name: str
    run: Callable[[], object]
    unhealthy_after: int = 5


@dataclass(frozen=True)
class SupervisorOutcome:
    cycles: int
    task_runs: int
    failure_count: int
    stopped: bool
    unhealthy: bool


def _checked_tasks(tasks: Iterable[QueueTask]) -> tuple[QueueTask, ...]:
    checked = tuple(tasks)
    if not checked:
        raise ValueError("the worker supervisor requires at least one queue task")
    names: set[str] = set()
    for task in checked:
        if not isinstance(task, QueueTask):
            raise ValueError("worker queue tasks must use QueueTask")
        name = task.name.strip()
        if not name or name != task.name or len(name) > 80 or name in names:
            raise ValueError("worker queue task names must be unique and normalized")
        if not callable(task.run):
            raise ValueError("worker queue task must be callable")
        if (
            isinstance(task.unhealthy_after, bool)
            or not isinstance(task.unhealthy_after, int)
            or not 1 <= task.unhealthy_after <= 100
        ):
            raise ValueError("worker unhealthy threshold must be between 1 and 100")
        names.add(name)
    return checked


def run_supervisor(
    *,
    tasks: Iterable[QueueTask],
    should_stop: Callable[[], bool],
    sleep: Callable[[float], object] = time.sleep,
    jitter: Callable[[float, float], float] = uniform,
    observe: Callable[[str, str, str], object] | None = None,
    idle_seconds: float = 5.0,
    jitter_seconds: float = 1.0,
    max_cycles: int | None = None,
) -> SupervisorOutcome:
    """Run small fair queue batches until stopped or persistently unhealthy.

    Queue functions own their transactions and claim limits. The supervisor owns only
    fair ordering, graceful stop boundaries, bounded idle delay, and redacted failure
    signals. It intentionally records an exception type, never exception text.
    """

    checked = _checked_tasks(tasks)
    if not callable(should_stop) or not callable(sleep) or not callable(jitter):
        raise ValueError("worker supervisor callbacks must be callable")
    if observe is not None and not callable(observe):
        raise ValueError("worker observer must be callable")
    if not isinstance(idle_seconds, (int, float)) or not 0.1 <= idle_seconds <= 60.0:
        raise ValueError("worker idle delay must be between 0.1 and 60 seconds")
    if (
        not isinstance(jitter_seconds, (int, float))
        or jitter_seconds < 0
        or jitter_seconds > idle_seconds
    ):
        raise ValueError("worker jitter must be nonnegative and no greater than idle delay")
    if max_cycles is not None and (
        isinstance(max_cycles, bool)
        or not isinstance(max_cycles, int)
        or not 1 <= max_cycles <= 1_000_000
    ):
        raise ValueError("worker cycle limit must be a positive integer")

    cycles = 0
    task_runs = 0
    failure_count = 0
    consecutive_failures = {task.name: 0 for task in checked}

    while max_cycles is None or cycles < max_cycles:
        if should_stop():
            return SupervisorOutcome(cycles, task_runs, failure_count, True, False)
        offset = cycles % len(checked)
        ordered = checked[offset:] + checked[:offset]
        for task in ordered:
            if should_stop():
                return SupervisorOutcome(cycles, task_runs, failure_count, True, False)
            try:
                task.run()
            except Exception as error:  # Each task is an isolated bounded worker seam.
                failure_count += 1
                task_runs += 1
                consecutive_failures[task.name] += 1
                if observe is not None:
                    observe("task_failed", task.name, type(error).__name__)
                if consecutive_failures[task.name] >= task.unhealthy_after:
                    return SupervisorOutcome(
                        cycles + 1,
                        task_runs,
                        failure_count,
                        False,
                        True,
                    )
            else:
                task_runs += 1
                consecutive_failures[task.name] = 0
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            break
        delay = idle_seconds + float(jitter(-jitter_seconds, jitter_seconds))
        sleep(max(0.1, min(60.0, delay)))

    return SupervisorOutcome(cycles, task_runs, failure_count, False, False)
