import operator
from typing import Any

from rest_framework import serializers

import pytest

from rest_filters import Filter, FilterSet
from rest_filters.constraints import MutuallyExclusive
from rest_filters.filtersets import Options
from rest_filters.utils import notset
from tests.test_filters import get_filterset_instance


def test_filterset_options() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

        class Meta:
            fields = ("username",)
            known_parameters = ("page", "page_size")
            combinators = {"group": operator.or_}
            constraints = (MutuallyExclusive(fields=["username", "created"]),)

    options = SomeFilterSet.options
    assert isinstance(options, Options)

    assert options.fields == ("username",)
    assert options.known_parameters == ("page", "page_size")
    assert options.combinators == {"group": operator.or_}

    assert len(options.constraints) == 1
    assert isinstance(options.constraints[0], MutuallyExclusive)
    assert options.constraints[0].fields == ["username", "created"]


def test_filterset_options_no_meta() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

    options = SomeFilterSet.options
    assert isinstance(options, Options)

    assert options.fields is notset
    assert options.known_parameters == []
    assert options.combinators == {}
    assert options.constraints == []


def test_filterset_options_partial_meta() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

        class Meta:
            known_parameters = ("page", "page_size")

    options = SomeFilterSet.options
    assert isinstance(options, Options)

    assert options.fields is notset
    assert options.known_parameters == ("page", "page_size")
    assert options.combinators == {}
    assert options.constraints == []


def test_filterset_compiled_fields_default():
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))
        created = Filter(
            serializers.DateField(help_text="some date"),
            children=[
                Filter(
                    param="date",
                    lookup="created__date",
                    children=[
                        Filter(
                            param="gte",
                            lookup="created__date__gte",
                        ),
                    ],
                )
            ],
        )

    compiled_fields = SomeFilterSet.compiled_fields
    assert compiled_fields == {
        "username": SomeFilterSet.username,
        "created": SomeFilterSet.created,
    }


def test_filterset_compiled_fields_case_omit():
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))
        created = Filter(
            serializers.DateField(help_text="some date"),
            children=[
                Filter(
                    param="date",
                    lookup="created__date",
                    children=[
                        Filter(
                            param="gte",
                            lookup="created__date__gte",
                        ),
                    ],
                )
            ],
        )

        class Meta:
            fields = ("username",)

    compiled_fields = SomeFilterSet.compiled_fields
    assert compiled_fields == {
        "username": SomeFilterSet.username,
    }


def test_filterset_compiled_fields_case_select_child() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))
        created = Filter(
            serializers.DateField(help_text="some date"),
            children=[
                Filter(
                    param="date",
                    lookup="created__date",
                    children=[
                        Filter(
                            param="gte",
                            lookup="created__date__gte",
                        ),
                    ],
                )
            ],
        )

        class Meta:
            fields = ("created.date.gte",)

    created = SomeFilterSet.created
    compiled_fields = SomeFilterSet.compiled_fields
    assert compiled_fields == {"created": created}

    assert created.namespace is True
    assert created.children[0].namespace is True
    assert created.children[0].children[0].namespace is False


def test_filterset_compiled_fields_case_remove_child() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))
        created = Filter(
            serializers.DateField(help_text="some date"),
            children=[
                Filter(
                    param="date",
                    lookup="created__date",
                    children=[
                        Filter(
                            param="gte",
                            lookup="created__date__gte",
                        ),
                    ],
                )
            ],
        )

        class Meta:
            fields = ("created",)

    created = SomeFilterSet.created
    compiled_fields = SomeFilterSet.compiled_fields
    assert compiled_fields == {"created": created}

    assert created.namespace is False
    assert created.children == []


def test_filterset_compiled_fields_case_remove_child_partial() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))
        created = Filter(
            serializers.DateField(help_text="some date"),
            children=[
                Filter(
                    param="date",
                    lookup="created__date",
                ),
                Filter(param="year", lookup="created__year"),
            ],
        )

        class Meta:
            fields = ("created", "created.year")

    created = SomeFilterSet.created
    compiled_fields = SomeFilterSet.compiled_fields
    assert compiled_fields == {"created": created}

    assert created.namespace is False
    assert len(created.children) == 1
    assert created.children[0].get_param_name() == "created.year"


def test_filterset_compiled_fields_bad_meta_fields() -> None:
    with pytest.raises(
        ValueError,
        match=r"Following fields are not valid: 'bad_value', 'another_bad',"
        " available fields: 'username', 'created.date', 'created.year', 'created'",
    ):

        class SomeFilterSet(FilterSet[Any]):
            username = Filter(serializers.CharField(min_length=3))
            created = Filter(
                serializers.DateField(help_text="some date"),
                children=[
                    Filter(
                        param="date",
                        lookup="created__date",
                    ),
                    Filter(param="year", lookup="created__year"),
                ],
            )

            class Meta:
                fields = (
                    "created",
                    "created.year",
                    "bad_value",
                    "another_bad",
                )


def test_filterset_init_copies_compiled_fields() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))

    compiled = SomeFilterSet.compiled_fields["username"]

    instance = get_filterset_instance(SomeFilterSet)
    fields = instance.fields
    copied = fields["username"]

    assert copied is not compiled


def test_filterset_init_copies_constraints() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

        class Meta:
            constraints = [
                MutuallyExclusive(fields=["username", "username.icontains"]),
            ]

    compiled = SomeFilterSet.options.constraints[0]

    instance = get_filterset_instance(SomeFilterSet)
    constraints = instance.constraints
    copied = constraints[0]

    assert copied is not compiled
