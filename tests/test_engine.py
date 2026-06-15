from typing import Literal

import pytest

from airules import Default, Fact, Field, KnowledgeEngine, Rule

Color = Literal["green", "red", "yellow"]


class Light(Fact):
    color: Field[Color]


class Vehicle(Fact):
    speed: Field[int]


class ThreeRule(KnowledgeEngine[Light, str]):
    @Rule(Light.color.eq("green"))
    def first(self, light: Light):
        return "first"

    @Rule(Light.color.eq("yellow"))
    def second(self, light: Light):
        return "second"

    @Rule(Light.color.eq("red"))
    def third(self, light: Light):
        return "third"


class WithDefault(KnowledgeEngine[Light, str]):
    @Rule(Light.color.eq("green"))
    def specific(self, light: Light):
        return "specific"

    @Default
    def fallback(self, light: Light):
        return "fallback"


class WithExplicitPriority(KnowledgeEngine[Light, str]):
    @Rule(Light.color.eq("green"))
    def low(self, light: Light):
        return "low"

    @Rule(Light.color.eq("green"), priority=999)
    def high(self, light: Light):
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


class Echo(KnowledgeEngine[Light, str]):
    @Rule(Light.color.eq("green"))
    def matched(self, light: Light) -> str:
        return f"matched {light.color}"

    @Default
    def fell_through(self, light: Light) -> str:
        return f"default {light.color}"


class TestFactInjection:
    def test_matched_rule_receives_the_evaluated_fact(self):
        assert Echo().run(Light(color="green")) == "matched green"

    def test_default_rule_also_receives_the_evaluated_fact(self):
        assert Echo().run(Light(color="red")) == "default red"

    def test_the_exact_instance_is_passed_through(self):
        seen: list[Light] = []

        class Capture(KnowledgeEngine[Light, None]):
            @Default
            def grab(self, light: Light) -> None:
                seen.append(light)

        fact = Light(color="green")
        Capture().run(fact)
        assert seen == [fact] and seen[0] is fact


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


class TestEvaluateOutcome:
    def test_outcome_exposes_matched_rule_name_and_result(self):
        outcome = Echo().evaluate(Light(color="green"))
        assert outcome.matched is True
        assert outcome.is_default is False
        assert outcome.rule_name == "matched"
        assert outcome.result == "matched green"

    def test_outcome_flags_default_fall_through(self):
        outcome = Echo().evaluate(Light(color="red"))
        assert outcome.matched is True
        assert outcome.is_default is True
        assert outcome.rule_name == "fell_through"
        assert outcome.result == "default red"

    def test_outcome_when_nothing_matches_has_no_rule(self):
        outcome = ThreeRule().evaluate(Light(color="orange"))  # type: ignore[arg-type]
        assert outcome.matched is False
        assert outcome.is_default is False
        assert outcome.rule_name is None
        assert outcome.result is None

    def test_outcome_carries_the_evaluated_fact_instance(self):
        fact = Light(color="green")
        outcome = Echo().evaluate(fact)
        assert outcome.fact is fact

    def test_run_returns_the_outcome_result(self):
        engine = Echo()
        for color in ("green", "red"):
            light = Light(color=color)  # type: ignore[arg-type]
            assert engine.run(light) == engine.evaluate(light).result


class AsyncEcho(KnowledgeEngine[Light, str]):
    @Rule(Light.color.eq("green"))
    async def matched(self, light: Light) -> str:
        return f"matched {light.color}"

    @Default
    async def fell_through(self, light: Light) -> str:
        return f"default {light.color}"


class TestAsyncMethods:
    @pytest.mark.asyncio
    async def test_async_rule_is_awaited_and_returns_result(self):
        assert await AsyncEcho().run_async(Light(color="green")) == "matched green"

    @pytest.mark.asyncio
    async def test_async_default_is_awaited_on_fallthrough(self):
        assert await AsyncEcho().run_async(Light(color="red")) == "default red"

    @pytest.mark.asyncio
    async def test_sync_rule_works_in_run_async(self):
        assert await Echo().run_async(Light(color="green")) == "matched green"

    @pytest.mark.asyncio
    async def test_evaluate_async_outcome_has_correct_metadata(self):
        outcome = await AsyncEcho().evaluate_async(Light(color="green"))
        assert outcome.matched is True
        assert outcome.is_default is False
        assert outcome.rule_name == "matched"
        assert outcome.result == "matched green"

    @pytest.mark.asyncio
    async def test_evaluate_async_unmatched_returns_empty_outcome(self):
        outcome = await ThreeRule().evaluate_async(Light(color="orange"))  # type: ignore[arg-type]
        assert outcome.matched is False
        assert outcome.result is None

    @pytest.mark.asyncio
    async def test_mixed_sync_and_async_rules_both_fire(self):
        class Mixed(KnowledgeEngine[Light, str]):
            @Rule(Light.color.eq("green"))
            def sync_rule(self, light: Light) -> str:
                return "sync"

            @Default
            async def async_default(self, light: Light) -> str:
                return "async"

        engine = Mixed()
        assert await engine.run_async(Light(color="green")) == "sync"
        assert await engine.run_async(Light(color="red")) == "async"
