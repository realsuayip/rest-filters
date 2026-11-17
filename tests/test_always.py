import operator
from typing import Any

from django.db.models import F, Q

from rest_framework import serializers
from rest_framework.fields import SkipField, empty

import pytest

from rest_filters import Blank, Filter, FilterSet, Multi, always
from rest_filters.constraints import Dependency, MutuallyExclusive
from rest_filters.fields import ListField, StrictBooleanField
from rest_filters.filters import Entry
from rest_filters.utils import Missing, missing
from tests.test_filters import get_filterset_instance


def test_always_requires_a_method_name() -> None:
    with pytest.raises(ValueError, match="non-empty method name"):
        always("")

    method = always("filter_minimum")
    field = Filter(method=method)
    assert field.method is method


def test_always_rejects_explicit_noop() -> None:
    with pytest.raises(
        ValueError,
        match=r"always\(\) cannot be combined with noop=True",
    ):
        Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
            noop=True,
        )


def test_always_calls_method_for_missing_parameter() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
        )

        def filter_minimum(self, param: str, value: int | Missing) -> Q:
            assert param == "minimum"
            assert value is missing
            return Q(id__gte=5)

    instance = get_filterset_instance(SomeFilterSet)
    groups, values = instance.get_groups()
    entry = groups["chain"]["minimum"]

    assert entry.expression == Q(id__gte=5)
    assert entry.value is missing
    assert values == {}


def test_always_receives_parsed_supplied_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
        )

        def filter_minimum(self, param: str, value: Any) -> Q:
            return Q(id__gte=value)

    instance = get_filterset_instance(SomeFilterSet, query="minimum=7")
    groups, values = instance.get_groups()
    entry = groups["chain"]["minimum"]

    assert entry.expression == Q(id__gte=7)
    assert values == {"minimum": 7}


def test_always_uses_serializer_default_before_missing_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(default=7),
            method=always("filter_minimum"),
        )

        def filter_minimum(self, param: str, value: Any) -> Q:
            return Q(id__gte=value)

    instance = get_filterset_instance(SomeFilterSet)
    groups, values = instance.get_groups()
    entry = groups["chain"]["minimum"]

    assert entry.expression == Q(id__gte=7)
    assert values == {"minimum": 7}


def test_always_uses_dynamic_default_before_missing_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
        )

        def get_default(self, param: str, default: Any) -> Any:
            return 9

        def filter_minimum(self, param: str, value: Any) -> Q:
            return Q(id__gte=value)

    instance = get_filterset_instance(SomeFilterSet)
    groups, values = instance.get_groups()
    entry = groups["chain"]["minimum"]

    assert entry.expression == Q(id__gte=9)
    assert values == {"minimum": 9}


def test_always_does_not_bypass_required_validation() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
            required=True,
        )

        def filter_minimum(self, param: str, value: Any) -> Q:
            raise AssertionError("A missing required parameter must not run")

    instance = get_filterset_instance(SomeFilterSet)

    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()

    assert ctx.value.detail == {"minimum": ["This field is required."]}


@pytest.mark.parametrize(
    "query,message",
    (
        ("minimum=invalid", "A valid integer is required."),
        (
            "minimum=-1",
            "Ensure this value is greater than or equal to 0.",
        ),
        (
            "minimum=1&minimum=2",
            "This query parameter does not allow specifying multiple values.",
        ),
    ),
)
def test_always_does_not_bypass_input_validation(
    query: str,
    message: str,
) -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(min_value=0),
            method=always("filter_minimum"),
        )

        def filter_minimum(self, param: str, value: Any) -> Q:
            raise AssertionError("Invalid input must not run the method")

    instance = get_filterset_instance(SomeFilterSet, query=query)

    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()

    assert ctx.value.detail == {"minimum": [message]}


def test_always_treats_omitted_blank_as_missing() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
            blank=Blank.OMIT,
        )

        def filter_minimum(self, param: str, value: Any) -> Q:
            assert value is missing
            return Q(id__gte=5)

    instance = get_filterset_instance(SomeFilterSet, query="minimum=")
    groups, values = instance.get_groups()
    entry = groups["chain"]["minimum"]

    assert entry.expression == Q(id__gte=5)
    assert values == {}


def test_always_preserves_kept_blank_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(allow_blank=True),
            method=always("filter_username"),
            blank=Blank.KEEP,
        )

        def filter_username(self, param: str, value: Any) -> Q:
            return Q(username=value)

    instance = get_filterset_instance(SomeFilterSet, query="username=")
    groups, values = instance.get_groups()
    entry = groups["chain"]["username"]

    assert entry.expression == Q(username="")
    assert values == {"username": ""}


def test_always_validates_kept_blank_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            method=always("filter_username"),
            blank=Blank.KEEP,
        )

        def filter_username(self, param: str, value: Any) -> Q:
            raise AssertionError("Invalid blank input must not run the method")

    instance = get_filterset_instance(SomeFilterSet, query="username=")

    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()

    assert ctx.value.detail == {"username": ["This field may not be blank."]}


def test_always_treats_all_omitted_multi_items_as_missing() -> None:
    class SomeFilterSet(FilterSet[Any]):
        names = Filter(
            ListField(child=serializers.CharField()),
            method=always("filter_names"),
            multi=Multi.ALLOW,
        )

        def filter_names(self, param: str, value: Any) -> Q:
            assert value is missing
            return Q(username="alice")

    instance = get_filterset_instance(SomeFilterSet, query="names=&names=")
    groups, values = instance.get_groups()
    entry = groups["chain"]["names"]

    assert entry.expression == Q(username="alice")
    assert values == {}


def test_always_distinguishes_null_from_missing() -> None:
    class SomeFilterSet(FilterSet[Any]):
        active = Filter(
            StrictBooleanField(allow_null=True),
            method=always("filter_active"),
        )

        def filter_active(self, param: str, value: Any) -> Q:
            assert value is None
            return Q(role__isnull=True)

    instance = get_filterset_instance(SomeFilterSet, query="active=null")
    groups, values = instance.get_groups()
    entry = groups["chain"]["active"]

    assert entry.expression == Q(role__isnull=True)
    assert values == {"active": None}


def test_always_respects_skip_field_for_supplied_input() -> None:
    class SkippingField(serializers.CharField):
        def to_internal_value(self, data: Any) -> str:
            raise SkipField

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            SkippingField(),
            method=always("filter_username"),
        )

        def filter_username(self, param: str, value: Any) -> Q:
            raise AssertionError("Explicitly skipped input must stay skipped")

    instance = get_filterset_instance(SomeFilterSet, query="username=skip")
    groups, values = instance.get_groups()

    assert groups == {}
    assert values == {}


def test_plain_method_still_skips_missing_parameter() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method="filter_minimum",
        )

        def filter_minimum(self, param: str, value: Any) -> Q:
            raise AssertionError("A plain method must skip missing input")

    instance = get_filterset_instance(SomeFilterSet)
    groups, values = instance.get_groups()

    assert groups == {}
    assert values == {}


def test_always_does_not_inherit_to_child_methods() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
            children=[Filter(param="child", method="filter_child")],
        )

        def filter_minimum(self, param: str, value: Any) -> Q:
            return Q(id__gte=5)

        def filter_child(self, param: str, value: Any) -> Q:
            raise AssertionError("Child methods must explicitly opt in")

    instance = get_filterset_instance(SomeFilterSet)
    groups, values = instance.get_groups()

    assert list(groups["chain"]) == ["minimum"]
    assert values == {}


def test_always_respects_namespaces_and_child_opt_in() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
            namespace=True,
            children=[Filter(param="child", method=always("filter_child"))],
        )

        def filter_minimum(self, param: str, value: Any) -> Q:
            raise AssertionError("A namespace must not run its method")

        def filter_child(self, param: str, value: Any) -> Q:
            assert param == "minimum.child"
            assert value is missing
            return Q(id__gte=5)

    instance = get_filterset_instance(SomeFilterSet)
    groups, values = instance.get_groups()
    entry = groups["chain"]["minimum.child"]

    assert entry.expression == Q(id__gte=5)
    assert values == {}


def test_always_survives_filterset_inheritance() -> None:
    class Parent(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
        )

        def filter_minimum(self, param: str, value: Any) -> Q:
            assert value is missing
            return Q(id__gte=5)

    class Child(Parent):
        pass

    instance = get_filterset_instance(Child)
    groups, _ = instance.get_groups()
    entry = groups["chain"]["minimum"]

    assert entry.expression == Q(id__gte=5)


def test_always_can_override_filterset_noop() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
            noop=False,
        )

        class Meta:
            noop = True

        def filter_minimum(self, param: str, value: Any) -> Q:
            return Q(id__gte=5 if value is missing else value)

    omitted = get_filterset_instance(SomeFilterSet)
    groups, values = omitted.get_groups()
    entry = groups["chain"]["minimum"]
    assert entry.expression == Q(id__gte=5)
    assert values == {}

    supplied = get_filterset_instance(SomeFilterSet, query="minimum=7")
    groups, values = supplied.get_groups()
    entry = groups["chain"]["minimum"]
    assert entry.expression == Q(id__gte=7)
    assert values == {"minimum": 7}


def test_always_can_return_none_for_missing_parameter() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
        )

        def filter_minimum(self, param: str, value: Any) -> None:
            assert value is missing
            return None  # noqa: PLR1711, RET501

    instance = get_filterset_instance(SomeFilterSet)
    groups, values = instance.get_groups()
    entry = groups["chain"]["minimum"]

    assert entry.expression is None
    assert values == {}


def test_always_fallback_does_not_trigger_mutual_exclusion() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
        )
        maximum = Filter(serializers.IntegerField(), field="id", lookup="lte")

        class Meta:
            constraints = [MutuallyExclusive(fields=["minimum", "maximum"])]

        def filter_minimum(self, param: str, value: Any) -> Q:
            return Q(id__gte=5)

    instance = get_filterset_instance(SomeFilterSet, query="maximum=10")
    groups, values = instance.get_groups()

    assert set(groups["chain"]) == {"minimum", "maximum"}
    assert values == {"maximum": 10}


def test_always_fallback_does_not_satisfy_dependency() -> None:
    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
        )
        maximum = Filter(serializers.IntegerField(), field="id", lookup="lte")

        class Meta:
            constraints = [
                Dependency(fields=["maximum"], depends_on=["minimum"]),
            ]

        def filter_minimum(self, param: str, value: Any) -> Q:
            return Q(id__gte=5)

    instance = get_filterset_instance(SomeFilterSet, query="maximum=10")

    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()

    assert ctx.value.detail == {
        "maximum": [
            "This query parameter also requires the following parameter "
            "to be present: 'minimum'",
        ],
    }


def test_always_entry_can_supply_value_group_and_aliases() -> None:
    result = Entry(
        group="custom",
        aliases={"minimum_id": F("id")},
        value=5,
        expression=Q(minimum_id__gte=5),
    )

    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
        )
        maximum = Filter(serializers.IntegerField(), field="id", lookup="lte")

        class Meta:
            constraints = [
                Dependency(fields=["maximum"], depends_on=["minimum"]),
            ]

        def filter_minimum(self, param: str, value: Any) -> Entry:
            assert value is missing
            return result

    instance = get_filterset_instance(SomeFilterSet, query="maximum=10")
    groups, values = instance.get_groups()
    entry = groups["custom"]["minimum"]

    assert entry is result
    assert entry.aliases == {"minimum_id": F("id")}
    assert values == {"minimum": 5, "maximum": 10}


def test_method_entry_with_empty_value_still_counts_as_present() -> None:
    result = Entry(
        group="chain",
        value=empty,
        expression=Q(id__gte=5),
    )

    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method="filter_minimum",
        )

        def filter_minimum(self, param: str, value: Any) -> Entry:
            return result

    instance = get_filterset_instance(SomeFilterSet, query="minimum=5")
    groups, values = instance.get_groups()
    entry = groups["chain"]["minimum"]

    assert entry is result
    assert values == {"minimum": empty}


def test_always_explicit_entry_keeps_empty_value() -> None:
    result = Entry(
        group="chain",
        value=empty,
        expression=Q(id__gte=5),
    )

    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
        )

        def filter_minimum(self, param: str, value: Any) -> Entry:
            assert value is missing
            return result

    instance = get_filterset_instance(SomeFilterSet)
    groups, values = instance.get_groups()
    entry = groups["chain"]["minimum"]

    assert entry is result
    assert values == {"minimum": empty}


def test_always_explicit_entry_can_preserve_missing_value() -> None:
    result = Entry(
        group="custom",
        value=missing,
        expression=Q(id__gte=5),
    )

    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(),
            method=always("filter_minimum"),
        )

        def filter_minimum(self, param: str, value: Any) -> Entry:
            assert value is missing
            return result

    instance = get_filterset_instance(SomeFilterSet)
    groups, values = instance.get_groups()
    entry = groups["custom"]["minimum"]

    assert entry is result
    assert values == {}


def test_always_preserves_empty_returned_by_custom_serializer() -> None:
    class EmptyField(serializers.CharField):
        def to_internal_value(self, data: Any) -> Any:
            return empty

    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            EmptyField(),
            method=always("filter_minimum"),
        )

        def filter_minimum(self, param: str, value: Any) -> Q:
            assert value is empty
            return Q(id__gte=5)

    instance = get_filterset_instance(SomeFilterSet, query="minimum=supplied")
    groups, values = instance.get_groups()
    entry = groups["chain"]["minimum"]

    assert entry.expression == Q(id__gte=5)
    assert values == {"minimum": empty}


def test_callable_default_returning_empty_still_counts_as_present() -> None:
    def empty_default() -> Any:
        return empty

    class SomeFilterSet(FilterSet[Any]):
        minimum = Filter(
            serializers.IntegerField(default=empty_default),
            noop=True,
        )

    instance = get_filterset_instance(SomeFilterSet)
    groups, values = instance.get_groups()
    entry = groups["chain"]["minimum"]

    assert entry.value is empty
    assert values == {"minimum": empty}


def test_always_fallback_uses_normal_grouping_and_aliases() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            aliases={"match_name": F("username")},
            method=always("filter_username"),
            group="names",
        )
        last_name = Filter(serializers.CharField(), group="names")

        class Meta:
            combinators = {"names": operator.or_}

        def filter_username(self, param: str, value: Any) -> Q:
            assert value is missing
            return Q(match_name="alice")

    instance = get_filterset_instance(SomeFilterSet, query="last_name=Smith")
    queryset = instance.filter_queryset()

    assert str(queryset.query).split(" WHERE ", 1)[1] == (
        '("testapp_user"."username" = alice OR "testapp_user"."last_name" = Smith)'
    )
