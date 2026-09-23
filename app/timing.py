import time
from contextlib import contextmanager
from typing import Literal

from pydantic import BaseModel, ConfigDict

Step = Literal[
    "input_guard",
    "resolve_connection",
    "load_history",
    "router",
    "retrieve_examples",
    "generate_sql",
    "route_and_generate_sql",
    "sql_guard",
    "execute_sql",
    "generate_answer",
]


class StepTimings(BaseModel):
    """Milliseconds spent in each step; steps that did not run are None.

    extra="forbid": a step name missing from this model (e.g. a new
    timings.step("...") added to Step above but not mirrored here) must
    fail loudly here instead of silently vanishing from the response —
    this has already happened twice with steps quietly dropped.
    """

    model_config = ConfigDict(extra="forbid")

    input_guard: float | None = None
    resolve_connection: float | None = None
    load_history: float | None = None
    router: float | None = None
    retrieve_examples: float | None = None
    generate_sql: float | None = None
    route_and_generate_sql: float | None = None
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
