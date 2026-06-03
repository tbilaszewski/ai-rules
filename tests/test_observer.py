import logging
from typing import Literal

from airules import (
    Default,
    Fact,
    Field,
    KnowledgeEngine,
    LoggingObserver,
    Outcome,
    OutcomeObserver,
    Rule,
)

Color = Literal["green", "red"]


class Light(Fact):
    color: Field[Color]


class Gate(KnowledgeEngine[Light, str]):
    @Rule(Light.color.eq("green"))
    def go(self, light: Light) -> str:
        return "go"

    @Default
    def hold(self, light: Light) -> str:
        return "hold"


class Recorder(OutcomeObserver[Light, str]):
    def __init__(self) -> None:
        self.seen: list[Outcome[Light, str]] = []

    def observe(self, outcome: Outcome[Light, str]) -> None:
        self.seen.append(outcome)


class TestProtocolConformance:
    def test_concrete_observers_satisfy_the_protocol_at_runtime(self):
        # OutcomeObserver is runtime_checkable: anything with observe() conforms.
        assert isinstance(LoggingObserver(), OutcomeObserver)
        assert isinstance(Recorder(), OutcomeObserver)

    def test_object_without_observe_does_not_conform(self):
        assert not isinstance(object(), OutcomeObserver)


class TestObserverInjection:
    def test_observer_is_notified_for_every_evaluation(self):
        rec = Recorder()
        gate = Gate(observer=rec)
        gate.run(Light(color="green"))
        gate.run(Light(color="red"))
        assert [o.rule_name for o in rec.seen] == ["go", "hold"]

    def test_observer_sees_the_same_outcome_run_returns(self):
        rec = Recorder()
        gate = Gate(observer=rec)
        outcome = gate.evaluate(Light(color="red"))
        assert rec.seen == [outcome]
        assert outcome.is_default is True

    def test_no_observer_is_a_no_op(self):
        # Default construction (no observer) must still evaluate normally.
        assert Gate().run(Light(color="green")) == "go"


class TestLoggingObserver:
    def test_default_fall_through_logs_warning(self, caplog):
        gate = Gate(observer=LoggingObserver())
        with caplog.at_level(logging.INFO, logger="airules.decisioning"):
            gate.run(Light(color="red"))
        records = [r for r in caplog.records if r.name == "airules.decisioning"]
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert "decision: default" in records[0].getMessage()

    def test_specific_match_logs_info(self, caplog):
        gate = Gate(observer=LoggingObserver())
        with caplog.at_level(logging.INFO, logger="airules.decisioning"):
            gate.run(Light(color="green"))
        records = [r for r in caplog.records if r.name == "airules.decisioning"]
        assert [r.levelno for r in records] == [logging.INFO]

    def test_observer_accepts_a_custom_logger(self, caplog):
        custom = logging.getLogger("my.app.decisions")
        gate = Gate(observer=LoggingObserver(custom))
        with caplog.at_level(logging.WARNING, logger="my.app.decisions"):
            gate.run(Light(color="red"))
        assert any(r.name == "my.app.decisions" for r in caplog.records)
