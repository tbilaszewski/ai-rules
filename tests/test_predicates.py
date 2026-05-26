from types import SimpleNamespace

import pytest

from airules.predicates import (
    Always,
    And,
    Contains,
    EndsWith,
    Eq,
    Ge,
    Gt,
    Le,
    Lt,
    Not,
    Or,
    Predicate,
    StartsWith,
    _CaseFoldingOp,
)


class TestAlways:
    def test_always_returns_true_for_any_fact(self):
        assert Always().evaluate(SimpleNamespace()) is True
        assert Always().evaluate(SimpleNamespace(x=1)) is True

    def test_to_dict(self):
        assert Always().to_dict() == {"type": "Always"}


class TestEq:
    def test_evaluates_true_when_field_matches(self):
        assert Eq("color", "red").evaluate(SimpleNamespace(color="red")) is True

    def test_evaluates_false_when_field_differs(self):
        assert Eq("color", "red").evaluate(SimpleNamespace(color="green")) is False

    def test_to_dict(self):
        assert Eq("color", "red").to_dict() == {
            "type": "Eq",
            "field": "color",
            "value": "red",
        }


class TestOr:
    def test_true_when_either_side_matches(self):
        p = Or(Eq("color", "red"), Eq("color", "green"))
        assert p.evaluate(SimpleNamespace(color="red")) is True
        assert p.evaluate(SimpleNamespace(color="green")) is True

    def test_false_when_neither_side_matches(self):
        p = Or(Eq("color", "red"), Eq("color", "green"))
        assert p.evaluate(SimpleNamespace(color="yellow")) is False

    def test_to_dict_nests(self):
        p = Or(Eq("color", "red"), Eq("color", "green"))
        assert p.to_dict() == {
            "type": "Or",
            "left": {"type": "Eq", "field": "color", "value": "red"},
            "right": {"type": "Eq", "field": "color", "value": "green"},
        }


class TestAnd:
    def test_true_when_both_sides_match(self):
        p = And(Eq("color", "red"), Eq("speed", 5))
        assert p.evaluate(SimpleNamespace(color="red", speed=5)) is True

    def test_false_when_one_side_fails(self):
        p = And(Eq("color", "red"), Eq("speed", 5))
        assert p.evaluate(SimpleNamespace(color="red", speed=10)) is False
        assert p.evaluate(SimpleNamespace(color="blue", speed=5)) is False

    def test_to_dict_nests(self):
        p = And(Eq("color", "red"), Eq("speed", 5))
        assert p.to_dict() == {
            "type": "And",
            "left": {"type": "Eq", "field": "color", "value": "red"},
            "right": {"type": "Eq", "field": "speed", "value": 5},
        }


class TestNot:
    def test_inverts_inner(self):
        p = Not(Eq("color", "red"))
        assert p.evaluate(SimpleNamespace(color="red")) is False
        assert p.evaluate(SimpleNamespace(color="blue")) is True

    def test_to_dict_nests(self):
        p = Not(Eq("color", "red"))
        assert p.to_dict() == {
            "type": "Not",
            "inner": {"type": "Eq", "field": "color", "value": "red"},
        }


class TestOperatorOverloads:
    def test_or_operator_builds_or_node(self):
        assert isinstance(Eq("x", 1) | Eq("x", 2), Or)

    def test_and_operator_builds_and_node(self):
        assert isinstance(Eq("x", 1) & Eq("y", 2), And)

    def test_invert_operator_builds_not_node(self):
        assert isinstance(~Eq("x", 1), Not)


class TestRoundTrip:
    @pytest.mark.parametrize(
        "predicate",
        [
            Always(),
            Eq("color", "red"),
            Or(Eq("color", "red"), Eq("color", "green")),
            And(Eq("color", "red"), Eq("speed", 5)),
            Not(Eq("color", "red")),
            Or(And(Eq("a", 1), Eq("b", 2)), Not(Eq("c", 3))),
        ],
    )
    def test_round_trip_matches_original_evaluation(self, predicate):
        rebuilt = Predicate.from_dict(predicate.to_dict())
        fact = SimpleNamespace(color="red", speed=5, a=1, b=2, c=3)
        assert rebuilt.evaluate(fact) == predicate.evaluate(fact)


class TestFromDict:
    def test_raises_on_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown predicate type"):
            Predicate.from_dict({"type": "Bogus"})


class TestNumericComparisons:
    @pytest.mark.parametrize(
        "predicate_cls, expected_truth",
        [
            (Gt, lambda actual, threshold: actual > threshold),
            (Ge, lambda actual, threshold: actual >= threshold),
            (Lt, lambda actual, threshold: actual < threshold),
            (Le, lambda actual, threshold: actual <= threshold),
        ],
    )
    @pytest.mark.parametrize("actual, threshold", [(5, 3), (3, 5), (5, 5)])
    def test_evaluate_matches_python_operator(
        self, predicate_cls, expected_truth, actual, threshold
    ):
        result = predicate_cls("x", threshold).evaluate(SimpleNamespace(x=actual))
        assert result is expected_truth(actual, threshold)

    @pytest.mark.parametrize("predicate_cls", [Gt, Ge, Lt, Le])
    def test_to_dict_uses_value_key(self, predicate_cls):
        assert predicate_cls("x", 5).to_dict() == {
            "type": predicate_cls.__name__,
            "field": "x",
            "value": 5,
        }


class TestContains:
    def test_substring_check_when_field_is_a_string(self):
        assert Contains("name", "ana").evaluate(SimpleNamespace(name="banana")) is True
        assert Contains("name", "ana").evaluate(SimpleNamespace(name="cherry")) is False

    def test_element_membership_when_field_is_a_list(self):
        p = Contains("tags", "urgent")
        assert p.evaluate(SimpleNamespace(tags=["urgent", "wip"])) is True
        assert p.evaluate(SimpleNamespace(tags=["wip"])) is False

    def test_to_dict(self):
        assert Contains("tags", "x").to_dict() == {
            "type": "Contains",
            "field": "tags",
            "value": "x",
        }


class TestStringPrefixSuffix:
    def test_startswith_evaluates(self):
        assert (
            StartsWith("name", "ban").evaluate(SimpleNamespace(name="banana")) is True
        )
        assert (
            StartsWith("name", "xyz").evaluate(SimpleNamespace(name="banana")) is False
        )

    def test_endswith_evaluates(self):
        assert EndsWith("name", "ana").evaluate(SimpleNamespace(name="banana")) is True
        assert EndsWith("name", "xyz").evaluate(SimpleNamespace(name="banana")) is False

    def test_startswith_to_dict(self):
        assert StartsWith("name", "x").to_dict() == {
            "type": "StartsWith",
            "field": "name",
            "value": "x",
        }

    def test_endswith_to_dict(self):
        assert EndsWith("name", "x").to_dict() == {
            "type": "EndsWith",
            "field": "name",
            "value": "x",
        }


class TestCaseInsensitiveMatching:
    def test_eq_folds_case_when_both_operands_are_strings(self):
        p = Eq("name", "Alice", case_insensitive=True)
        assert p.evaluate(SimpleNamespace(name="alice")) is True
        assert p.evaluate(SimpleNamespace(name="ALICE")) is True
        assert p.evaluate(SimpleNamespace(name="bob")) is False

    def test_eq_stays_exact_by_default(self):
        assert Eq("name", "Alice").evaluate(SimpleNamespace(name="alice")) is False

    def test_eq_falls_back_to_exact_when_target_is_not_a_string(self):
        # Flag set, but a non-string target must not attempt case folding.
        p = Eq("n", 5, case_insensitive=True)
        assert p.evaluate(SimpleNamespace(n=5)) is True
        assert p.evaluate(SimpleNamespace(n=6)) is False

    def test_eq_case_insensitive_against_none_target_does_not_raise(self):
        assert (
            Eq("n", "x", case_insensitive=True).evaluate(SimpleNamespace(n=None))
            is False
        )

    @pytest.mark.parametrize(
        "predicate_cls, field_value",
        [(StartsWith, "ban"), (EndsWith, "ANA"), (Contains, "NaN")],
    )
    def test_string_ops_fold_case(self, predicate_cls, field_value):
        p = predicate_cls("name", field_value, case_insensitive=True)
        assert p.evaluate(SimpleNamespace(name="BaNaNa")) is True

    @pytest.mark.parametrize("predicate_cls", [StartsWith, EndsWith, Contains])
    def test_string_ops_stay_exact_by_default(self, predicate_cls):
        p = predicate_cls("name", "BAN")
        assert p.evaluate(SimpleNamespace(name="banana")) is False

    def test_contains_list_membership_stays_exact_even_with_flag(self):
        # Per design: case folding applies to substring matches only; list/set
        # membership is always exact.
        p = Contains("tags", "Urgent", case_insensitive=True)
        assert p.evaluate(SimpleNamespace(tags=["urgent", "wip"])) is False
        assert p.evaluate(SimpleNamespace(tags=["Urgent"])) is True


class TestCaseInsensitiveSerialization:
    @pytest.mark.parametrize("predicate_cls", [Eq, StartsWith, EndsWith, Contains])
    def test_flag_omitted_from_dict_when_false(self, predicate_cls):
        # Backward compatibility: predicates without folding serialize unchanged.
        assert "case_insensitive" not in predicate_cls("f", "v").to_dict()

    @pytest.mark.parametrize("predicate_cls", [Eq, StartsWith, EndsWith, Contains])
    def test_flag_present_in_dict_when_true(self, predicate_cls):
        assert (
            predicate_cls("f", "v", case_insensitive=True).to_dict()["case_insensitive"]
            is True
        )

    @pytest.mark.parametrize("predicate_cls", [Eq, StartsWith, EndsWith, Contains])
    def test_round_trip_preserves_folding(self, predicate_cls):
        original = predicate_cls("name", "Foo", case_insensitive=True)
        rebuilt = Predicate.from_dict(original.to_dict())
        assert isinstance(rebuilt, _CaseFoldingOp)
        assert rebuilt.case_insensitive is True
        fact = SimpleNamespace(name="foo")
        assert rebuilt.evaluate(fact) == original.evaluate(fact) is True

    def test_legacy_dict_without_flag_still_loads(self):
        # A predicate serialized before the flag existed has no key.
        rebuilt = Predicate.from_dict({"type": "Eq", "field": "name", "value": "Alice"})
        assert isinstance(rebuilt, _CaseFoldingOp)
        assert rebuilt.case_insensitive is False
        assert rebuilt.evaluate(SimpleNamespace(name="alice")) is False


class TestRoundTripFieldOps:
    @pytest.mark.parametrize(
        "predicate",
        [
            Gt("x", 5),
            Ge("x", 5),
            Lt("x", 5),
            Le("x", 5),
            Contains("tags", "urgent"),
            StartsWith("name", "foo"),
            EndsWith("name", "bar"),
            And(Gt("x", 0), Lt("x", 10)),
            Or(StartsWith("name", "a"), EndsWith("name", "z")),
        ],
    )
    def test_round_trip_matches_original_evaluation(self, predicate):
        rebuilt = Predicate.from_dict(predicate.to_dict())
        fact = SimpleNamespace(x=7, tags=["urgent", "wip"], name="foobar")
        assert rebuilt.evaluate(fact) == predicate.evaluate(fact)


class TestNoneTolerance:
    @pytest.mark.parametrize(
        "predicate",
        [
            Gt("x", 5),
            Ge("x", 5),
            Lt("x", 5),
            Le("x", 5),
            Contains("tags", "urgent"),
            StartsWith("name", "foo"),
            EndsWith("name", "bar"),
        ],
    )
    def test_field_ops_return_false_when_target_is_none(self, predicate):
        # An absent (None) field value can't satisfy any ordering, containment,
        # or string-shape predicate. Must not raise.
        fact = SimpleNamespace(x=None, tags=None, name=None)
        assert predicate.evaluate(fact) is False

    def test_eq_returns_true_when_both_field_and_value_are_none(self):
        # Eq is the special case: `None == None` is a meaningful, true comparison.
        assert Eq("x", None).evaluate(SimpleNamespace(x=None)) is True

    def test_eq_returns_false_when_field_is_none_but_value_is_not(self):
        assert Eq("x", 5).evaluate(SimpleNamespace(x=None)) is False

    def test_dotted_path_short_circuits_when_intermediate_is_none(self):
        # `outer.inner.leaf` where `outer.inner` is None — must not AttributeError.
        fact = SimpleNamespace(outer=SimpleNamespace(inner=None))
        assert Gt("outer.inner.leaf", 5).evaluate(fact) is False
        assert Contains("outer.inner.tags", "x").evaluate(fact) is False
        assert StartsWith("outer.inner.name", "a").evaluate(fact) is False

    def test_dotted_path_short_circuits_when_root_is_none(self):
        # Reading any path off None should be False, never raise.
        fact = SimpleNamespace(outer=None)
        assert Gt("outer.x", 5).evaluate(fact) is False

    def test_eq_against_none_target_via_dotted_path_returns_true(self):
        # Once the leaf resolves to None, Eq with expected=None still matches.
        fact = SimpleNamespace(outer=SimpleNamespace(inner=None))
        assert Eq("outer.inner", None).evaluate(fact) is True

    def test_eq_against_non_none_value_via_none_intermediate_returns_false(self):
        fact = SimpleNamespace(outer=None)
        assert Eq("outer.x", "anything").evaluate(fact) is False
