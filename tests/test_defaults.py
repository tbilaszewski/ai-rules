from typing import Literal

import pytest

from airules import EmbeddedField, Fact, Field, NumberField, StringField

Color = Literal["green", "red", "yellow"]


class Inner(Fact):
    name: StringField


class WithDefaults(Fact):
    required: Field[Color]
    explicit_default: Field[str] = Field(default="hello")
    auto_optional: Field[str | None]
    number: NumberField[int] = NumberField(default=0)
    inner_required: EmbeddedField[Inner]
    inner_optional: EmbeddedField[Inner] = EmbeddedField(Inner, default=None)
    inner_default_instance: EmbeddedField[Inner] = EmbeddedField(
        Inner, default=Inner(name="default-name")
    )


def _make(**overrides: object) -> WithDefaults:
    base = {"required": "green", "inner_required": Inner(name="x")}
    base.update(overrides)
    return WithDefaults(**base)


class TestExplicitDefault:
    def test_omitted_field_uses_explicit_default(self):
        f = _make()
        assert f.explicit_default == "hello"
        assert f.number == 0

    def test_provided_value_overrides_default(self):
        f = _make(explicit_default="custom", number=42)
        assert f.explicit_default == "custom"
        assert f.number == 42


class TestAutoOptional:
    def test_field_with_none_in_annotation_defaults_to_none(self):
        f = _make()
        assert f.auto_optional is None

    def test_explicit_none_is_accepted(self):
        f = _make(auto_optional=None)
        assert f.auto_optional is None

    def test_value_can_be_passed_for_optional_field(self):
        f = _make(auto_optional="present")
        assert f.auto_optional == "present"


class TestEmbeddedDefault:
    def test_optional_embedded_defaults_to_none(self):
        f = _make()
        assert f.inner_optional is None

    def test_embedded_default_instance_is_used_when_omitted(self):
        f = _make()
        assert isinstance(f.inner_default_instance, Inner)
        assert f.inner_default_instance.name == "default-name"

    def test_embedded_default_is_overridden_by_provided_value(self):
        f = _make(inner_default_instance=Inner(name="override"))
        assert f.inner_default_instance.name == "override"

    def test_optional_embedded_accepts_explicit_instance(self):
        f = _make(inner_optional=Inner(name="explicit"))
        assert f.inner_optional is not None
        assert f.inner_optional.name == "explicit"


class TestRequiredEnforcement:
    def test_omitting_required_field_raises(self):
        with pytest.raises(TypeError, match="missing required fields"):
            WithDefaults(inner_required=Inner(name="x"))  # type: ignore[call-arg]

    def test_omitting_required_embedded_field_raises(self):
        with pytest.raises(TypeError, match="missing required fields"):
            WithDefaults(required="green")  # type: ignore[call-arg]

    def test_missing_message_lists_only_required_fields(self):
        with pytest.raises(TypeError) as exc_info:
            WithDefaults()  # type: ignore[call-arg]
        message = str(exc_info.value)
        assert "required" in message
        assert "inner_required" in message
        # fields that have defaults must NOT appear in the missing list
        assert "explicit_default" not in message
        assert "auto_optional" not in message
        assert "number" not in message
        assert "inner_optional" not in message

    def test_unknown_field_still_raises(self):
        with pytest.raises(TypeError, match="unexpected fields"):
            _make(bogus="value")  # type: ignore[call-arg]


class TestHasDefaultIntrospection:
    @pytest.mark.parametrize(
        "field_name, expected_has_default",
        [
            ("required", False),
            ("explicit_default", True),
            ("auto_optional", True),
            ("number", True),
            ("inner_required", False),
            ("inner_optional", True),
            ("inner_default_instance", True),
        ],
    )
    def test_has_default_reflects_declaration(
        self, field_name: str, expected_has_default: bool
    ):
        assert WithDefaults._fields[field_name].has_default is expected_has_default
