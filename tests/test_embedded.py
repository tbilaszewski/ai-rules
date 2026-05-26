from typing import Literal

import pytest

from airules import (
    EmbeddedField,
    Fact,
    Field,
    ListField,
    NumberField,
    StringField,
)
from airules.predicates import Eq, Lt

Color = Literal["green", "red", "yellow"]


class Sensor(Fact):
    voltage: NumberField[float]


class Light(Fact):
    color: Field[Color]
    sensor: EmbeddedField[Sensor]


class Metadata(Fact):
    region: StringField


class Customer(Fact):
    metadata: EmbeddedField[Metadata]
    name: StringField


class Order(Fact):
    customer: EmbeddedField[Customer]
    total: NumberField[float]


class Bay(Fact):
    tags: ListField[str]


class Inventory(Fact):
    bay: EmbeddedField[Bay]


class TestEmbeddedFieldSynthesis:
    def test_fact_typed_annotation_installs_embedded_field_descriptor(self):
        descriptor = Light.__dict__["sensor"]
        assert isinstance(descriptor, EmbeddedField)

    def test_embedded_field_appears_in_collected_fields(self):
        assert "sensor" in Light._fields
        assert isinstance(Light._fields["sensor"], EmbeddedField)

    def test_non_embedded_fields_are_still_synthesized(self):
        # Regression: ordinary fields still work alongside embedded ones
        assert "color" in Light._fields
        assert isinstance(Light._fields["color"], Field)


class TestPathAwarePredicateBuilding:
    def test_two_level_chain_builds_dotted_predicate(self):
        predicate = Light.sensor.voltage.lt(5)
        assert isinstance(predicate, Lt)
        assert predicate.field_name == "sensor.voltage"
        assert predicate.value == 5

    def test_chain_via_string_field(self):
        predicate = Order.customer.name.eq("Alice")
        assert isinstance(predicate, Eq)
        assert predicate.field_name == "customer.name"
        assert predicate.value == "Alice"

    def test_three_level_chain(self):
        predicate = Order.customer.metadata.region.eq("EU")
        assert isinstance(predicate, Eq)
        assert predicate.field_name == "customer.metadata.region"

    def test_unknown_attribute_on_proxy_raises(self):
        with pytest.raises(AttributeError):
            Light.sensor.bogus  # type: ignore[attr-defined]


class TestPathEvaluation:
    def test_predicate_reads_value_through_embedded_path(self):
        light = Light(color="red", sensor=Sensor(voltage=3.0))
        assert Light.sensor.voltage.lt(5).evaluate(light) is True
        assert Light.sensor.voltage.lt(2).evaluate(light) is False

    def test_top_level_field_still_evaluates(self):
        light = Light(color="red", sensor=Sensor(voltage=3.0))
        assert Light.color.eq("red").evaluate(light) is True
        assert Light.color.eq("green").evaluate(light) is False

    def test_three_level_predicate_evaluates(self):
        order = Order(
            total=99.99,
            customer=Customer(name="Alice", metadata=Metadata(region="EU")),
        )
        assert Order.customer.metadata.region.eq("EU").evaluate(order) is True
        assert Order.customer.metadata.region.eq("US").evaluate(order) is False


class TestDictCoercionOnAssignment:
    def test_dict_passed_for_embedded_field_constructs_inner_fact(self):
        light = Light(color="red", sensor={"voltage": 3.0})
        assert isinstance(light.sensor, Sensor)
        assert light.sensor.voltage == 3.0

    def test_explicit_inner_fact_is_stored_as_is(self):
        sensor = Sensor(voltage=3.0)
        light = Light(color="red", sensor=sensor)
        assert light.sensor is sensor

    def test_two_level_nested_dict_coerces_recursively(self):
        order = Order(
            total=99.99,
            customer={"name": "Alice", "metadata": {"region": "EU"}},
        )
        assert isinstance(order.customer, Customer)
        assert isinstance(order.customer.metadata, Metadata)
        assert order.customer.metadata.region == "EU"


class TestEmbeddedSchema:
    def test_schema_describes_embedded_fact_recursively(self):
        sensor_schema = Light.schema()["fields"]["sensor"]
        assert sensor_schema["type"] == "Fact"
        assert sensor_schema["schema"]["name"] == "Sensor"
        assert "voltage" in sensor_schema["schema"]["fields"]

    def test_three_level_schema_nests_all_facts(self):
        schema = Order.schema()
        customer_schema = schema["fields"]["customer"]
        assert customer_schema["type"] == "Fact"
        metadata_schema = customer_schema["schema"]["fields"]["metadata"]
        assert metadata_schema["type"] == "Fact"
        assert metadata_schema["schema"]["name"] == "Metadata"
        assert "region" in metadata_schema["schema"]["fields"]


class Car(Fact):
    sensor: EmbeddedField[Sensor] = EmbeddedField(Sensor, default=None)
    tags: ListField[str] = ListField(default=None)


class TestPathProxyBuildersForEveryOperator:
    """The proxy reached via class access (`Order.customer...`) must expose the
    full operator set of each leaf field type, not just `eq`/`lt`. These build
    the same predicate classes as direct class access, but carry the dotted path.
    """

    @pytest.mark.parametrize("method", ["gt", "ge", "lt", "le"])
    def test_number_field_operators_through_path(self, method):
        predicate = getattr(Order.total, method)(50)  # sanity: direct access
        via_path = getattr(Light.sensor.voltage, method)(50)
        assert type(via_path) is type(predicate)
        assert via_path.field_name == "sensor.voltage"
        assert via_path.value == 50

    @pytest.mark.parametrize("method", ["startswith", "endswith", "contains"])
    def test_string_field_operators_through_path(self, method):
        via_path = getattr(Order.customer.name, method)("Al")
        assert via_path.field_name == "customer.name"
        assert via_path.value == "Al"

    def test_list_field_contains_through_embedded_path(self):
        # `Car.tags` is class access (ListField.contains); reaching a list field
        # *through* an embedded fact goes via the path proxy (`_ListPath`).
        predicate = Inventory.bay.tags.contains("urgent")
        assert predicate.field_name == "bay.tags"
        assert predicate.value == "urgent"

    def test_list_field_contains_through_embedded_path_evaluates(self):
        inv = Inventory(bay=Bay(tags=["urgent", "wip"]))
        assert Inventory.bay.tags.contains("urgent").evaluate(inv) is True
        assert Inventory.bay.tags.contains("done").evaluate(inv) is False

    def test_number_operators_through_path_evaluate(self):
        light = Light(color="red", sensor=Sensor(voltage=5.0))
        assert Light.sensor.voltage.gt(2).evaluate(light) is True
        assert Light.sensor.voltage.gt(9).evaluate(light) is False
        assert Light.sensor.voltage.ge(5).evaluate(light) is True
        assert Light.sensor.voltage.le(5).evaluate(light) is True

    def test_string_operators_through_path_evaluate(self):
        order = Order(
            total=1.0,
            customer=Customer(name="Alice", metadata=Metadata(region="EU")),
        )
        assert Order.customer.name.startswith("Al").evaluate(order) is True
        assert Order.customer.name.endswith("ce").evaluate(order) is True
        assert Order.customer.name.contains("lic").evaluate(order) is True
        assert Order.customer.name.startswith("Bo").evaluate(order) is False


class TestNoneTolerantPredicatesThroughFacts:
    """Integration: predicates built via the descriptor/proxy API must not
    crash when the runtime value is None (default=None on Optional fields)."""

    def test_contains_on_default_none_list_returns_false(self):
        car = Car()
        assert Car.tags.contains("urgent").evaluate(car) is False

    def test_ordering_on_path_through_default_none_embedded_returns_false(self):
        car = Car()
        assert Car.sensor.voltage.lt(5).evaluate(car) is False

    def test_eq_on_path_through_default_none_embedded_returns_false(self):
        car = Car()
        assert Car.sensor.voltage.eq(3.0).evaluate(car) is False

    def test_predicate_still_evaluates_when_optional_is_filled(self):
        car = Car(sensor=Sensor(voltage=2.5), tags=["urgent"])
        assert Car.sensor.voltage.lt(5).evaluate(car) is True
        assert Car.tags.contains("urgent").evaluate(car) is True
