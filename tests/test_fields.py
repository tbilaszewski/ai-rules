from typing import Literal

import pytest

from airules import Fact, Field, ListField, NumberField, StringField
from airules.predicates import (
    Contains,
    EndsWith,
    Eq,
    Ge,
    Gt,
    Le,
    Lt,
    StartsWith,
)

Color = Literal["green", "red", "yellow"]


class Box(Fact):
    color: Field[Color]


class Order(Fact):
    quantity: NumberField[int]
    name: StringField
    tags: ListField[str]


class TestMissingSentinel:
    def test_explicit_none_default_is_distinct_from_missing(self):
        # None is a legitimate default value, not the same as "no default given".
        # This distinction is the whole reason the MISSING sentinel exists.
        field: Field[str] = Field(default=None)
        assert field.has_default is True


class TestDescriptorAccess:
    def test_class_access_returns_field_descriptor(self):
        assert isinstance(Box.color, Field)

    def test_instance_access_returns_stored_value(self):
        assert Box(color="green").color == "green"

    def test_set_stores_value_in_instance_dict(self):
        box = Box(color="green")
        box.color = "red"  # type: ignore[assignment]
        assert box.color == "red"

    def test_set_does_not_leak_across_instances(self):
        a = Box(color="green")
        b = Box(color="red")
        assert a.color == "green"
        assert b.color == "red"


class TestSetName:
    def test_field_captures_its_attribute_name(self):
        assert Box.color._name == "color"


class TestEqBuilder:
    def test_eq_returns_eq_predicate(self):
        predicate = Box.color.eq("green")
        assert isinstance(predicate, Eq)

    def test_eq_predicate_carries_field_name(self):
        assert Box.color.eq("green").field_name == "color"

    def test_eq_predicate_carries_expected_value(self):
        assert Box.color.eq("green").value == "green"

    def test_eq_predicate_evaluates_against_fact(self):
        predicate = Box.color.eq("green")
        assert predicate.evaluate(Box(color="green")) is True
        assert predicate.evaluate(Box(color="red")) is False


class TestNumberField:
    def test_class_access_returns_number_field(self):
        assert isinstance(Order.quantity, NumberField)

    @pytest.mark.parametrize(
        "method, predicate_cls",
        [("gt", Gt), ("ge", Ge), ("lt", Lt), ("le", Le)],
    )
    def test_builder_returns_expected_predicate(self, method, predicate_cls):
        assert isinstance(getattr(Order.quantity, method)(5), predicate_cls)

    def test_eq_still_inherited_from_base_field(self):
        assert isinstance(Order.quantity.eq(5), Eq)

    def test_gt_evaluates_against_instance(self):
        order = Order(quantity=10, name="x", tags=[])
        assert Order.quantity.gt(5).evaluate(order) is True
        assert Order.quantity.gt(20).evaluate(order) is False


class TestStringField:
    @pytest.mark.parametrize(
        "method, predicate_cls, arg",
        [
            ("startswith", StartsWith, "ban"),
            ("endswith", EndsWith, "ana"),
            ("contains", Contains, "anan"),
        ],
    )
    def test_builder_returns_expected_predicate(self, method, predicate_cls, arg):
        assert isinstance(getattr(Order.name, method)(arg), predicate_cls)

    def test_startswith_evaluates(self):
        order = Order(quantity=1, name="banana", tags=[])
        assert Order.name.startswith("ban").evaluate(order) is True
        assert Order.name.startswith("xyz").evaluate(order) is False

    def test_endswith_evaluates(self):
        order = Order(quantity=1, name="banana", tags=[])
        assert Order.name.endswith("ana").evaluate(order) is True
        assert Order.name.endswith("xyz").evaluate(order) is False

    def test_contains_evaluates_for_substring(self):
        order = Order(quantity=1, name="banana", tags=[])
        assert Order.name.contains("nan").evaluate(order) is True
        assert Order.name.contains("xyz").evaluate(order) is False


class TestCaseInsensitiveBuilders:
    def test_string_builders_thread_flag_to_predicate(self):
        assert (
            Order.name.startswith("ban", case_insensitive=True).case_insensitive is True
        )
        assert (
            Order.name.endswith("ana", case_insensitive=True).case_insensitive is True
        )
        assert (
            Order.name.contains("nan", case_insensitive=True).case_insensitive is True
        )

    def test_eq_builder_threads_flag(self):
        # Case folding targets free-form string fields; a StringField is the
        # realistic case (a Literal-typed field only holds its exact values).
        assert Order.name.eq("Banana", case_insensitive=True).case_insensitive is True

    def test_builders_default_to_case_sensitive(self):
        assert Order.name.startswith("ban").case_insensitive is False
        assert Order.name.eq("banana").case_insensitive is False

    def test_case_insensitive_builder_evaluates(self):
        order = Order(quantity=1, name="Banana", tags=[])
        assert (
            Order.name.startswith("ban", case_insensitive=True).evaluate(order) is True
        )
        assert Order.name.startswith("ban").evaluate(order) is False


class TestListField:
    def test_contains_returns_contains_predicate(self):
        assert isinstance(Order.tags.contains("urgent"), Contains)

    def test_contains_evaluates_for_element_membership(self):
        order = Order(quantity=1, name="x", tags=["urgent", "wip"])
        assert Order.tags.contains("urgent").evaluate(order) is True
        assert Order.tags.contains("done").evaluate(order) is False

    def test_empty_list_never_contains_anything(self):
        order = Order(quantity=1, name="x", tags=[])
        assert Order.tags.contains("anything").evaluate(order) is False
