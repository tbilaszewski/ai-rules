from typing import Literal

from airules import (
    Default,
    EmbeddedField,
    Fact,
    Field,
    KnowledgeEngine,
    ListField,
    NumberField,
    Rule,
)

SignalColor = Literal["green", "red", "yellow"]


class RoadSensor(Fact):
    """A roadside sensor reading; embedded in a Crossing and may be absent."""

    approaching_speed_kph: NumberField[int] = NumberField(default=0)


class Crossing(Fact):
    """The live state of a pedestrian crossing."""

    signal: Field[SignalColor]
    seconds_left: NumberField[int]
    sensor: EmbeddedField[RoadSensor] = EmbeddedField(RoadSensor, default=None)
    hazards: ListField[str] = ListField(default=None)


class CrossingAdvisor(KnowledgeEngine[Crossing, str]):
    """Advises a pedestrian whether to cross.

    Earlier rules win, so the most safety-critical conditions come first: a
    reported hazard or a fast approaching vehicle overrides a green light.
    """

    @Rule(Crossing.hazards.contains("flooding") | Crossing.hazards.contains("ice"))
    def hazard_present(self) -> str:
        return "Do not cross — hazard reported"

    @Rule(Crossing.sensor.approaching_speed_kph.ge(50))
    def fast_vehicle(self) -> str:
        return "Wait — a fast vehicle is approaching"

    @Rule(Crossing.signal.eq("green") & Crossing.seconds_left.ge(10))
    def safe(self) -> str:
        return "Safe to cross"

    @Rule(Crossing.signal.eq("red") | Crossing.signal.eq("yellow"))
    def stop(self) -> str:
        return "Stop — wait for green"

    @Default
    def wait(self) -> str:
        # Reached e.g. when the light is green but too little time remains.
        return "Wait for the next signal"


def main() -> None:
    advisor = CrossingAdvisor()

    scenarios: dict[str, Crossing] = {
        "green, plenty of time": Crossing(signal="green", seconds_left=20),
        "green, running out": Crossing(signal="green", seconds_left=4),
        "fast car approaching": Crossing(
            signal="green",
            seconds_left=20,
            sensor=RoadSensor(approaching_speed_kph=80),
        ),
        "flooding reported": Crossing(
            signal="green", seconds_left=20, hazards=["flooding"]
        ),
        "red light": Crossing(signal="red", seconds_left=30),
    }

    print("Advice")
    print("------")
    for label, crossing in scenarios.items():
        print(f"  {label:24} -> {advisor.run(crossing)}")


if __name__ == "__main__":
    main()
