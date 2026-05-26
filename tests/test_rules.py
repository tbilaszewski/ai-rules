from airules import Default, Rule
from airules.predicates import Always, Eq
from airules.rules import RuleSpec


class TestRuleDecorator:
    def test_returns_rule_spec(self):
        @Rule(Eq("x", 1))
        def fn(self):
            pass

        assert isinstance(fn, RuleSpec)

    def test_captures_predicate(self):
        predicate = Eq("x", 1)

        @Rule(predicate)
        def fn(self):
            pass

        assert fn.predicate is predicate

    def test_captures_explicit_priority(self):
        @Rule(Eq("x", 1), priority=42)
        def fn(self):
            pass

        assert fn.priority == 42

    def test_priority_defaults_to_none(self):
        @Rule(Eq("x", 1))
        def fn(self):
            pass

        assert fn.priority is None

    def test_is_default_false_by_default(self):
        @Rule(Eq("x", 1))
        def fn(self):
            pass

        assert fn.is_default is False


class TestDefaultDecorator:
    def test_returns_rule_spec(self):
        @Default
        def fn(self):
            pass

        assert isinstance(fn, RuleSpec)

    def test_predicate_is_always_node(self):
        @Default
        def fn(self):
            pass

        assert isinstance(fn.predicate, Always)

    def test_is_default_true(self):
        @Default
        def fn(self):
            pass

        assert fn.is_default is True


class Holder:
    @Rule(Eq("x", 1))
    def rule_method(self):
        return "ran"

    @Default
    def fallback(self):
        return "default"


class TestRuleSpecDescriptor:
    def test_class_access_returns_rule_spec(self):
        assert isinstance(Holder.rule_method, RuleSpec)

    def test_instance_access_returns_callable_bound_method(self):
        assert Holder().rule_method() == "ran"

    def test_default_decorated_method_is_also_callable_on_instance(self):
        assert Holder().fallback() == "default"

    def test_class_access_exposes_predicate_for_introspection(self):
        spec = Holder.rule_method
        assert isinstance(spec.predicate, Eq)
        assert spec.predicate.field_name == "x"
        assert spec.predicate.value == 1
