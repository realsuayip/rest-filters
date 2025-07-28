import datetime
import zoneinfo
from typing import Any

from rest_framework import serializers
from rest_framework.fields import empty

import pytest

from rest_filters import Filter, FilterSet
from rest_filters.constraints import (
    Constraint,
    MethodConstraint,
    MutuallyExclusive,
    MutuallyInclusive,
)
from tests.test_filters import get_filterset_instance


def test_handle_constraints() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        email = Filter(serializers.EmailField())

        class Meta:
            constraints = [
                MutuallyExclusive(fields=["username", "email"]),
            ]

    instance = get_filterset_instance(SomeFilterSet)
    errors = instance.handle_constraints(
        {
            "username": "test",
            "email": "test@example.com",
        }
    )
    assert errors == {
        "non_field_errors": [
            "Following fields are mutually exclusive,"
            ' you may only provide one of them: "username", "email"'
        ]
    }

    errors1 = instance.handle_constraints({"username": "test"})
    errors2 = instance.handle_constraints({"email": "test@example.com"})
    assert errors1 == {}
    assert errors2 == {}


def test_handle_constraints_sets_filterset_instance() -> None:
    class MyConstraint(Constraint):
        def check(self, values: dict[str, Any]) -> None:
            if values["age"] < self.filterset.get_magic_value():
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Request failed to meet constraint: MyConstraint"
                        ]
                    }
                )

    class SomeFilterSet(FilterSet[Any]):
        age = Filter(serializers.IntegerField())

        def get_magic_value(self) -> int:
            return 10

        class Meta:
            constraints = [
                MyConstraint(),
            ]

    instance = get_filterset_instance(SomeFilterSet)
    errors1 = instance.handle_constraints({"age": 9})
    errors2 = instance.handle_constraints({"age": 11})
    assert errors1 == {
        "non_field_errors": ["Request failed to meet constraint: MyConstraint"]
    }
    assert errors2 == {}


def test_handle_constraints_case_custom_message() -> None:
    class MyConstraint(Constraint):
        def check(self, values: dict[str, Any]) -> bool:
            if values["age"] == 1:
                raise serializers.ValidationError("something went wrong")
            if values["age"] == 2:
                raise serializers.ValidationError(["something went wrong"])
            if values["age"] == 3:
                raise serializers.ValidationError(
                    {"non_field_errors": ["something went wrong"]}
                )
            if values["age"] == 4:
                raise serializers.ValidationError({"custom": ["something went wrong"]})

    class SomeFilterSet(FilterSet[Any]):
        age = Filter(serializers.IntegerField())

        class Meta:
            constraints = [
                MyConstraint(message="Something went wrong"),
            ]

    instance = get_filterset_instance(SomeFilterSet)
    (
        errors1,
        errors2,
        errors3,
        errors4,
    ) = (
        instance.handle_constraints({"age": 1}),
        instance.handle_constraints({"age": 2}),
        instance.handle_constraints({"age": 3}),
        instance.handle_constraints({"age": 4}),
    )
    assert (
        errors1 == errors2 == errors3 == {"non_field_errors": ["something went wrong"]}
    )
    assert errors4 == {"custom": ["something went wrong"]}


def test_method_constraint() -> None:
    class SomeFilterSet(FilterSet[Any]):
        age = Filter(serializers.IntegerField())

        class Meta:
            constraints = [
                MethodConstraint(method="check_age_constraint"),
            ]

        def check_age_constraint(self, values: dict[str, Any]) -> bool:
            if values["age"] < 10:
                raise serializers.ValidationError("Age must be greater than 10")

    instance = get_filterset_instance(SomeFilterSet)
    errors1 = instance.handle_constraints({"age": 9})
    errors2 = instance.handle_constraints({"age": 11})
    assert errors1 == {"non_field_errors": ["Age must be greater than 10"]}
    assert errors2 == {}


def test_mutually_exclusive_constraint() -> None:
    class SomeFilterSet(FilterSet[Any]):
        a = Filter(serializers.IntegerField())
        b = Filter(serializers.IntegerField())
        c = Filter(serializers.IntegerField())

        class Meta:
            constraints = [
                MutuallyExclusive(fields=["a", "b", "c"]),
            ]

    instance = get_filterset_instance(SomeFilterSet)
    errors1 = instance.handle_constraints({"a": 1, "b": 2})
    errors2 = instance.handle_constraints({"a": 1, "b": 2, "c": 3})
    errors3 = instance.handle_constraints({"a": 1, "c": 3})
    errors4 = instance.handle_constraints({"b": 1, "c": 3})

    errors5 = instance.handle_constraints({"a": 2})
    errors6 = instance.handle_constraints({"b": 2})
    errors7 = instance.handle_constraints({"c": 2})

    assert errors1 == {
        "non_field_errors": [
            "Following fields are mutually exclusive,"
            ' you may only provide one of them: "a", "b"'
        ]
    }
    assert errors2 == {
        "non_field_errors": [
            "Following fields are mutually exclusive,"
            ' you may only provide one of them: "a", "b", "c"'
        ]
    }
    assert errors3 == {
        "non_field_errors": [
            "Following fields are mutually exclusive,"
            ' you may only provide one of them: "a", "c"'
        ]
    }
    assert errors4 == {
        "non_field_errors": [
            "Following fields are mutually exclusive,"
            ' you may only provide one of them: "b", "c"'
        ]
    }
    assert errors5 == errors6 == errors7 == {}


def test_mutually_exclusive_constraint_case_custom_error_message() -> None:
    class SomeFilterSet(FilterSet[Any]):
        pasta = Filter(serializers.BooleanField(required=False))
        ketchup = Filter(serializers.BooleanField(required=False))

        class Meta:
            constraints = [
                MutuallyExclusive(
                    message="This is not the Italian way...",
                    fields=[
                        "pasta",
                        "ketchup",
                    ],
                ),
            ]

    instance = get_filterset_instance(SomeFilterSet)
    errors = instance.handle_constraints({"pasta": "yes", "ketchup": "yes"})
    assert errors == {"non_field_errors": ["This is not the Italian way..."]}


def test_mutually_inclusive_constraint() -> None:
    class SomeFilterSet(FilterSet[Any]):
        a = Filter(serializers.IntegerField())
        b = Filter(serializers.IntegerField())
        c = Filter(serializers.IntegerField())

        class Meta:
            constraints = [
                MutuallyInclusive(fields=["a", "b", "c"]),
            ]

    instance = get_filterset_instance(SomeFilterSet)
    errors1 = instance.handle_constraints({"a": 1, "b": 2})
    errors2 = instance.handle_constraints({"a": 1, "b": 2, "c": 3})
    errors3 = instance.handle_constraints({"a": 1, "c": 3})
    errors4 = instance.handle_constraints({"b": 1, "c": 3})

    errors5 = instance.handle_constraints({"a": 2})
    errors6 = instance.handle_constraints({"b": 2})
    errors7 = instance.handle_constraints({"c": 2})

    assert (
        errors1
        == errors3
        == errors4
        == errors5
        == errors6
        == errors7
        == {
            "non_field_errors": [
                "Following fields are mutually inclusive, you must provide"
                ' them all at once or none of them: "a", "b", "c"'
            ]
        }
    )
    assert errors2 == {}


def test_mutually_inclusive_constraint_case_custom_error_message() -> None:
    class SomeFilterSet(FilterSet[Any]):
        pasta = Filter(serializers.BooleanField(required=False))
        olive_oil_ml = Filter(serializers.IntegerField(required=False))

        class Meta:
            constraints = [
                MutuallyInclusive(
                    message="This is not the Italian way...",
                    fields=[
                        "pasta",
                        "olive_oil_ml",
                    ],
                ),
            ]

    instance = get_filterset_instance(SomeFilterSet)
    errors = instance.handle_constraints({"pasta": "yes"})
    assert errors == {"non_field_errors": ["This is not the Italian way..."]}


def test_constraint_combination_bad_combination() -> None:
    class SomeFilterSet(FilterSet[Any]):
        a = Filter(serializers.IntegerField())
        b = Filter(serializers.IntegerField())
        c = Filter(serializers.IntegerField())

        class Meta:
            constraints = [
                MutuallyInclusive(fields=["a", "b", "c"]),
                MutuallyExclusive(fields=["a", "b"]),
            ]

    instance = get_filterset_instance(SomeFilterSet)
    errors1 = instance.handle_constraints({"a": 1, "b": 2})
    errors2 = instance.handle_constraints({"a": 1, "b": 2, "c": 3})
    assert errors1 == {
        "non_field_errors": [
            "Following fields are mutually inclusive, you must provide them"
            ' all at once or none of them: "a", "b", "c"',
            "Following fields are mutually exclusive, you may only provide"
            ' one of them: "a", "b"',
        ]
    }
    assert errors2 == {
        "non_field_errors": [
            "Following fields are mutually exclusive, you may only provide"
            ' one of them: "a", "b"'
        ]
    }


def test_constraint_values_missing_fields_and_unresolved_fields_behavior() -> None:
    # 1. If a field does not appear in query parameters, accessing it in values
    # must raise KeyError
    #
    # 2. If a field appears in query parameters and has a field level
    # validation error on it, it should be inside values as 'empty' sentinel.
    #
    # 3. If a field appear in query parameter, and has no field level
    # validation error, it should appear as serialized in values.
    class MyConstraint(Constraint):
        def check(self, values: dict[str, Any]) -> bool:
            with pytest.raises(KeyError):
                values["first_name"]
            with pytest.raises(KeyError):
                values["last_name"]
            assert values["created"] is empty
            assert values["created.gte"] == datetime.datetime(
                2025, 1, 1, 0, 0, tzinfo=zoneinfo.ZoneInfo(key="UTC")
            )
            return True

    class SomeFilterSet(FilterSet[Any]):
        first_name = Filter(serializers.CharField(required=False))
        last_name = Filter(serializers.CharField(required=False))
        created = Filter(
            serializers.DateTimeField(default_timezone=zoneinfo.ZoneInfo(key="UTC")),
            children=[Filter(param="gte", lookup="gte")],
        )

        class Meta:
            constraints = [MyConstraint()]

    instance = get_filterset_instance(
        SomeFilterSet,
        query="created=bad-value&created.gte=2025-01-01",
    )
    with pytest.raises(serializers.ValidationError):
        instance.get_groups()


def test_constraint_gives_access_to_all_fields() -> None:
    expected = {
        "a": "hello",
        "b": 64,
        "created": datetime.datetime(
            2025, 1, 2, 0, 0, tzinfo=zoneinfo.ZoneInfo(key="UTC")
        ),
        "created.gte": datetime.datetime(
            2025, 1, 1, 0, 0, tzinfo=zoneinfo.ZoneInfo(key="UTC")
        ),
    }

    class MyConstraint(Constraint):
        def get_message(self, values: dict[str, Any]) -> dict[str, Any]:
            assert values == expected

        def check(self, values: dict[str, Any]) -> bool:
            assert values == expected
            return True

    class SomeFilterSet(FilterSet[Any]):
        a = Filter(serializers.CharField(required=False))
        b = Filter(serializers.IntegerField())
        created = Filter(
            serializers.DateTimeField(default_timezone=zoneinfo.ZoneInfo("UTC")),
            children=[Filter(param="gte", lookup="gte")],
        )

        class Meta:
            constraints = [MyConstraint()]

    instance = get_filterset_instance(
        SomeFilterSet,
        query="created=2025-01-02&created.gte=2025-01-01&a=hello&b=64",
    )
    instance.get_groups()
