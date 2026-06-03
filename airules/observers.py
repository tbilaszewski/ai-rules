"""Ready-made :class:`OutcomeObserver` implementations.

These are adapters you inject into a ``KnowledgeEngine`` — the engine itself
stays free of ``logging``. ``LoggingObserver`` is the "logging service": it logs
every evaluation, loudly when a Fact falls through to ``@Default`` or matches no
rule at all (e.g. a ``["SECURITY"]`` label missing a case-sensitive rule), so
those near-misses are never lost silently.
"""

import logging

from typing_extensions import TypeVar

from .engine import KnowledgeEngine, Outcome, OutcomeObserver
from .facts import Fact

T = TypeVar("T", bound=Fact)
R = TypeVar("R")

logger = logging.getLogger("airules.decisioning")


class LoggingObserver(OutcomeObserver[T, R]):
    """Logs each ``Outcome``: WARNING on default/no-match, INFO on a real match.

    Generic over the engine's Fact/result types: injecting it into a
    ``KnowledgeEngine[T, R]`` infers ``LoggingObserver[T, R]``, so ``observe``
    stays precisely typed without an ``Any`` in sight.
    """

    def __init__(self, log: logging.Logger | None = None) -> None:
        self._log = log if log is not None else logger

    def observe(self, outcome: Outcome[T, R], engine: KnowledgeEngine[T, R]) -> None:
        if not outcome.matched:
            self._log.warning(f"decision: no rule matched | fact={outcome.fact!r}")

        elif outcome.is_default:
            self._log.warning(
                f"decision: default | rule={outcome.rule_name} "
                f"result={outcome.result!r} fact={outcome.fact!r}"
            )
        else:
            self._log.info(
                f"decision: matched | rule={outcome.rule_name} "
                f"result={outcome.result!r}"
            )

        self._log.info(f"engine schema {engine.describe()}")
