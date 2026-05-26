from typing import Literal

import pytest

from airules import Fact, Field, NumberField
from airules.predicates import Gt

Color = Literal["green", "red", "yellow"]


class Light(Fact):
    color: Field[Color]


class Vehicle(Fact):
    speed: Field[int]


class TrafficSignal(Light):
    direction: Field[str]


class HybridFact(Light, Vehicle):
    pass


class TestConstruction:
    def test_init_accepts_kwargs_matching_fields(self):
        assert Light(color="green").color == "green"

    def test_missing_required_field_raises(self):
        with pytest.raises(TypeError, match="missing required fields"):
            Light()  # type: ignore[call-arg]

    def test_unknown_field_raises(self):
        with pytest.raises(TypeError, match="unexpected fields"):
            Light(color="green", bogus="value")  # type: ignore[call-arg]

    def test_runtime_does_not_enforce_literal_values(self):
        # Literal is a typing hint, not runtime validation.
        # Tested so that downstream code (e.g. predicates) doesn't assume validation here.
        assert Light(color="orange").color == "orange"  # type: ignore[arg-type]


class TestFieldAggregation:
    def test_simple_class_collects_its_own_fields(self):
        assert set(Light._fields) == {"color"}

    def test_subclass_inherits_parent_fields(self):
        assert set(TrafficSignal._fields) == {"color", "direction"}

    def test_multiple_inheritance_aggregates_fields_from_all_parents(self):
        assert set(HybridFact._fields) == {"color", "speed"}


class PlainAnnotation(Fact):
    # `count` is a bare type, not wrapped in a Field descriptor.
    count: int
    color: Field[Color]


class TestPlainAnnotationIsNotAField:
    def test_bare_non_field_annotation_is_not_collected(self):
        # Only Field-typed (or Fact-typed) annotations become fields; a plain
        # `int` annotation is silently ignored rather than raising.
        assert set(PlainAnnotation._fields) == {"color"}

    def test_plain_annotation_is_not_required_at_construction(self):
        # Since `count` isn't a field, omitting it must not raise.
        assert PlainAnnotation(color="green").color == "green"  # type: ignore[call-arg]

    def test_passing_the_plain_annotation_name_is_rejected_as_unknown(self):
        with pytest.raises(TypeError, match="unexpected fields"):
            PlainAnnotation(color="green", count=1)  # type: ignore[call-arg]


class BaseField(Fact):
    value: Field[int]


class OverridesField(BaseField):
    # Re-declares `value` with a richer field type than the parent.
    value: NumberField[int]


class TestFieldOverrideInSubclass:
    def test_subclass_field_type_replaces_parents(self):
        assert isinstance(OverridesField._fields["value"], NumberField)

    def test_overridden_field_exposes_subclass_builders(self):
        predicate = OverridesField.value.gt(5)
        assert isinstance(predicate, Gt)
        assert predicate.field_name == "value"

    def test_overridden_field_evaluates(self):
        assert OverridesField.value.gt(5).evaluate(OverridesField(value=10)) is True


class TestSchema:
    def test_schema_includes_class_name(self):
        assert Light.schema()["name"] == "Light"

    def test_schema_describes_literal_fields_with_values(self):
        assert Light.schema()["fields"]["color"] == {
            "type": "Literal",
            "values": ["green", "red", "yellow"],
        }

    def test_schema_describes_simple_types_by_name(self):
        assert Vehicle.schema()["fields"]["speed"] == {"type": "int"}

    def test_schema_for_subclass_includes_inherited_fields(self):
        assert set(TrafficSignal.schema()["fields"]) == {"color", "direction"}

    def test_schema_for_multiple_inheritance(self):
        assert set(HybridFact.schema()["fields"]) == {"color", "speed"}
