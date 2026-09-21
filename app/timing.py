import time
from contextlib import contextmanager
from typing import Literal

from pydantic import BaseModel

Step = Literal[
    "input_guard",
    "router",
    "generate_sql",
    "sql_guard",
    "execute_sql",
    "generate_answer",
]


class StepTimings(BaseModel):
    """Milliseconds spent in each step; steps that did not run are None."""

    input_guard: float | None = None
    router: float | None = None
    generate_sql: float | None = None
    sql_guard: float | None = None
    execute_sql: float | None = None
    generate_answer: float | None = None
    total: float | None = None


class Timings:
    """Collects how long each step of a request takes."""

    def __init__(self):
        self._start = time.perf_counter()
        self._steps: dict[str, float] = {}

    @contextmanager
    def step(self, name: Step):
        start = time.perf_counter()
        try:
            yield
        finally:
            self._steps[name] = round((time.perf_counter() - start) * 1000, 1)

    def as_model(self) -> StepTimings:
        return StepTimings(
            **self._steps,
            total=round((time.perf_counter() - self._start) * 1000, 1)
        )
