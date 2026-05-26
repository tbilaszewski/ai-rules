from typing import Literal

from airules import Default, Fact, Field, KnowledgeEngine, Predicate, Rule

Color = Literal["green", "red", "yellow"]


class Light(Fact):
    color: Field[Color]


class LightsCrossing(KnowledgeEngine[Light, str]):
    @Rule(Light.color.eq("green"))
    def green(self, light: Light):
        return "Safe to walk"

    @Rule(Light.color.eq("yellow"))
    def yellow(self, light: Light):
        return "Better hurry up"

    @Rule(Light.color.eq("red") | Light.color.eq("yellow"))
    def red(self, light: Light):
        return "Don't walk!"

    @Default
    def unknown(self, light: Light):
        return "Unknown signal"


class TestRunFiresExpectedRule:
    def test_green_input_fires_green_rule(self):
        assert LightsCrossing().run(Light(color="green")) == "Safe to walk"

    def test_yellow_input_fires_yellow_first_match_wins_over_red(self):
        assert LightsCrossing().run(Light(color="yellow")) == "Better hurry up"

    def test_red_input_fires_red_rule(self):
        assert LightsCrossing().run(Light(color="red")) == "Don't walk!"

    def test_unmatched_input_fires_default(self):
        assert (
            LightsCrossing().run(Light(color="orange"))  # type: ignore[arg-type]
            == "Unknown signal"
        )


class TestDescribePayload:
    def test_describe_includes_fact_schema_with_literal_values(self):
        payload = LightsCrossing.describe()
        assert payload["facts"] == [
            {
                "name": "Light",
                "fields": {
                    "color": {
                        "type": "Literal",
                        "values": ["green", "red", "yellow"],
                    }
                },
            }
        ]

    def test_describe_lists_all_rules_in_definition_order(self):
        payload = LightsCrossing.describe()
        names = [r["name"] for r in payload["rules"]]
        assert names == ["green", "yellow", "red", "unknown"]

    def test_describe_marks_default_rule(self):
        payload = LightsCrossing.describe()
        defaults = [r for r in payload["rules"] if r["is_default"]]
        assert [r["name"] for r in defaults] == ["unknown"]

    def test_describe_assigns_descending_auto_priorities(self):
        payload = LightsCrossing.describe()
        by_name = {r["name"]: r["priority"] for r in payload["rules"]}
        assert by_name["green"] == 3
        assert by_name["yellow"] == 2
        assert by_name["red"] == 1

    def test_describe_predicates_round_trip(self):
        payload = LightsCrossing.describe()
        for rule, entry in zip(payload["rules"], LightsCrossing.rules):
            rebuilt = Predicate.from_dict(rule["predicate"])
            for color in ["green", "yellow", "red", "orange"]:
                fact = Light(color=color)  # type: ignore[arg-type]
                assert rebuilt.evaluate(fact) == entry.predicate.evaluate(fact)


class Car(Fact):
    car_color: Field[Color]


class TrafficFact(Light, Car):
    pass


class TrafficCrossing(KnowledgeEngine[Light | TrafficFact, str]):
    @Rule(Light.color.eq("green") & Car.car_color.eq("red"))
    def safe(self, fact: Light | TrafficFact):
        return "Safe to cross"

    @Rule(Light.color.eq("yellow"))
    def caution(self, fact: Light | TrafficFact):
        return "Caution"

    @Rule(Light.color.eq("red"))
    def stop(self, fact: Light | TrafficFact):
        return "Stop"

    @Default
    def wait(self, fact: Light | TrafficFact):
        return "Wait"


class TestUnionOfFacts:
    def test_combined_predicate_fires_for_fully_specified_traffic_fact(self):
        result = TrafficCrossing().run(TrafficFact(color="green", car_color="red"))
        assert result == "Safe to cross"

    def test_traffic_fact_with_unmatched_car_color_falls_through_to_default(self):
        result = TrafficCrossing().run(TrafficFact(color="green", car_color="green"))
        assert result == "Wait"

    def test_traffic_fact_matches_color_only_rule_when_and_short_circuits(self):
        result = TrafficCrossing().run(TrafficFact(color="yellow", car_color="green"))
        assert result == "Caution"

    def test_simple_light_fact_matches_color_only_rule(self):
        # And-rule's left side is False for color="yellow", so short-circuit
        # avoids touching car_color (which Light doesn't have).
        assert TrafficCrossing().run(Light(color="yellow")) == "Caution"

    def test_simple_light_with_red_color_fires_stop(self):
        assert TrafficCrossing().run(Light(color="red")) == "Stop"

    def test_describe_lists_both_fact_schemas(self):
        payload = TrafficCrossing.describe()
        names = {f["name"] for f in payload["facts"]}
        assert names == {"Light", "TrafficFact"}

    def test_describe_traffic_fact_includes_inherited_and_own_fields(self):
        payload = TrafficCrossing.describe()
        traffic = next(f for f in payload["facts"] if f["name"] == "TrafficFact")
        assert set(traffic["fields"]) == {"color", "car_color"}
