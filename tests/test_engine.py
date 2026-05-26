from typing import Literal

from airules import Default, Fact, Field, KnowledgeEngine, Rule

Color = Literal["green", "red", "yellow"]


class Light(Fact):
    color: Field[Color]


class Vehicle(Fact):
    speed: Field[int]


class ThreeRule(KnowledgeEngine[Light, str]):
    @Rule(Light.color.eq("green"))
    def first(self):
        return "first"

    @Rule(Light.color.eq("yellow"))
    def second(self):
        return "second"

    @Rule(Light.color.eq("red"))
    def third(self):
        return "third"


class WithDefault(KnowledgeEngine[Light, str]):
    @Rule(Light.color.eq("green"))
    def specific(self):
        return "specific"

    @Default
    def fallback(self):
        return "fallback"


class WithExplicitPriority(KnowledgeEngine[Light, str]):
    @Rule(Light.color.eq("green"))
    def low(self):
        return "low"

    @Rule(Light.color.eq("green"), priority=999)
    def high(self):
        return "high"


class UnionEngine(KnowledgeEngine[Light | Vehicle, str]):
    pass


class EmptyEngine(KnowledgeEngine[Light]):
    pass


class TestAutoPriority:
    def test_first_defined_rule_gets_highest_priority(self):
        priorities = {e.method.__name__: e.priority for e in ThreeRule.rules}
        assert priorities["first"] > priorities["second"] > priorities["third"]

    def test_auto_priorities_are_descending_integers_from_n(self):
        priorities = [e.priority for e in ThreeRule.rules]
        assert priorities == [3, 2, 1]

    def test_default_does_not_consume_auto_priority_slot(self):
        # WithDefault has one regular rule + one default; the regular should
        # still get auto-priority 1 (numbered against regulars only).
        regular = [e for e in WithDefault.rules if not e.is_default][0]
        assert regular.priority == 1


class TestExplicitPriority:
    def test_explicit_priority_wins_over_auto(self):
        assert WithExplicitPriority().run(Light(color="green")) == "high"


class TestFirstMatchSemantics:
    def test_only_highest_priority_matching_rule_fires(self):
        assert ThreeRule().run(Light(color="green")) == "first"
        assert ThreeRule().run(Light(color="yellow")) == "second"
        assert ThreeRule().run(Light(color="red")) == "third"

    def test_unmatched_input_returns_none_when_no_default(self):
        assert ThreeRule().run(Light(color="orange")) is None  # type: ignore[arg-type]

    def test_empty_engine_returns_none(self):
        assert EmptyEngine().run(Light(color="green")) is None


class TestDefaults:
    def test_default_fires_when_no_specific_rule_matches(self):
        assert WithDefault().run(Light(color="orange")) == "fallback"  # type: ignore[arg-type]

    def test_default_does_not_fire_when_specific_rule_matches(self):
        assert WithDefault().run(Light(color="green")) == "specific"

    def test_default_is_always_sorted_last(self):
        sorted_entries = sorted(
            WithDefault.rules, key=lambda e: (e.is_default, -e.priority)
        )
        assert sorted_entries[-1].is_default is True


class Unparametrized(KnowledgeEngine):
    pass


class TestFactTypeExtraction:
    def test_single_type_returns_one_element_tuple(self):
        assert ThreeRule._fact_types() == (Light,)

    def test_union_type_returns_tuple_of_members(self):
        assert set(UnionEngine._fact_types()) == {Light, Vehicle}

    def test_unparametrized_engine_has_no_fact_types(self):
        # No `KnowledgeEngine[...]` parameterization anywhere in the bases:
        # degrades to empty rather than raising.
        assert Unparametrized._fact_types() == ()


class TestDescribe:
    def test_describe_includes_facts_list(self):
        payload = ThreeRule.describe()
        assert isinstance(payload["facts"], list)
        assert payload["facts"][0]["name"] == "Light"

    def test_describe_lists_rules_with_serialized_predicates(self):
        payload = ThreeRule.describe()
        for rule in payload["rules"]:
            assert "predicate" in rule
            assert "type" in rule["predicate"]

    def test_describe_marks_default_rule(self):
        payload = WithDefault.describe()
        defaults = [r for r in payload["rules"] if r["is_default"]]
        assert len(defaults) == 1

    def test_describe_for_union_engine_lists_all_fact_schemas(self):
        payload = UnionEngine.describe()
        names = {f["name"] for f in payload["facts"]}
        assert names == {"Light", "Vehicle"}
