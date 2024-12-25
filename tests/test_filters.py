from typing import Any

from django.db.models.functions import Length
from django.http import QueryDict

from rest_framework import serializers
from rest_framework.fields import empty

import pytest

from rest_filters import Filter, FilterSet


def test_filter_defaults() -> None:
    f = Filter()

    assert f.blank == "omit"
    assert f.lookup == "exact"
    assert f.negate is False
    assert f.namespace is False
    assert f.children == []

    assert f.parent is None
    assert f.aliases is None
    assert f.template is None
    assert f.method is None


def test_filter_group_is_valid_identifier() -> None:
    with pytest.raises(ValueError, match="must be valid Python"):
        Filter(group="not-a-valid-identifier")


def test_filter_blank_invalid_choice() -> None:
    with pytest.raises(ValueError, match="blank must either be 'keep' or 'omit'"):
        Filter(blank="empty")  # type: ignore[arg-type]

    f1 = Filter(blank="keep")
    f2 = Filter(blank="omit")

    assert f1.blank == "keep"
    assert f2.blank == "omit"


def test_filter_child_binding() -> None:
    child1, child2 = Filter(param="child1"), Filter(param="child2")
    parent = Filter(children=[child1, child2])

    assert child1.parent == parent
    assert child2.parent == parent


def test_filter_child_binding_param_required_for_child() -> None:
    with pytest.raises(ValueError, match="param needs to be set for child filters"):
        Filter(children=[Filter()])


def test_namespace_filter_without_children() -> None:
    with pytest.raises(
        ValueError, match="Namespace filters are required to have child filters"
    ):
        Filter(namespace=True)


def test_filter_repr() -> None:
    f = Filter(serializers.DateTimeField(), param="created")
    assert (
        repr(f) == "Filter(param='created', group='chain', serializer=DateTimeField())"
    )


def test_filter_descriptor_sets_name() -> None:
    class SomeFilterSet(FilterSet[Any]):
        created = Filter(serializers.DateTimeField())

    assert SomeFilterSet.created.name == "created"


def test_filter_get_group() -> None:
    f1, f2 = (
        Filter(),
        Filter(group="f2_group"),
    )
    f3_child_1, f3_child_2, f4_child_1 = (
        Filter(param="a"),
        Filter(param="b", group="f3_child_2"),
        Filter(param="c"),
    )

    f3 = Filter(children=[f3_child_1, f3_child_2], group="f3_parent_group")
    f4 = Filter(children=[f4_child_1])

    assert f1.get_group() == "chain"
    assert f2.get_group() == "f2_group"

    assert f3.get_group() == "f3_parent_group"
    assert f3_child_1.get_group() == "f3_parent_group"
    assert f3_child_2.get_group() == "f3_child_2"

    assert f4.get_group() == "chain"
    assert f4_child_1.get_group() == "chain"


def test_filter_get_db_field() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter()
        f2 = Filter(field="created")
        f3 = Filter(field=Length("username"))

        modified = Filter(
            children=[
                Filter(param="gte"),
            ]
        )
        first_name = Filter(
            children=[
                Filter(param="ln", field="last_name"),
                Filter(param="len", field=Length("last_name")),
            ]
        )
        last_name = Filter(
            field=Length("last_name"),
            children=[
                Filter(param="xy"),
            ],
        )

    assert SomeFilterSet.username.get_db_field() == "username"
    assert SomeFilterSet.f2.get_db_field() == "created"
    assert SomeFilterSet.f3.get_db_field() == Length("username")

    assert SomeFilterSet.modified.get_db_field() == "modified"
    assert SomeFilterSet.modified.children[0].get_db_field() == "modified"

    assert SomeFilterSet.first_name.get_db_field() == "first_name"
    assert SomeFilterSet.first_name.children[0].get_db_field() == "last_name"
    assert SomeFilterSet.first_name.children[1].get_db_field() == Length("last_name")

    assert SomeFilterSet.last_name.get_db_field() == Length("last_name")
    assert SomeFilterSet.last_name.children[0].get_db_field() == Length("last_name")


def test_filter_get_param_name() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter()
        email = Filter(param="mail")
        modified = Filter(
            param="updated",
            children=[
                Filter(param="gte"),
            ],
        )
        created = Filter(
            children=[
                Filter(param="gte"),
                Filter(param="lte"),
                Filter(
                    param="year",
                    children=[
                        Filter(param="gte"),
                        Filter(param="lte"),
                    ],
                ),
            ]
        )

    f = SomeFilterSet

    assert f.username.get_param_name() == "username"
    assert f.email.get_param_name() == "mail"

    assert f.modified.get_param_name() == "updated"
    assert f.modified.children[0].get_param_name() == "updated.gte"

    assert f.created.get_param_name() == "created"
    assert f.created.children[0].get_param_name() == "created.gte"
    assert f.created.children[1].get_param_name() == "created.lte"

    assert f.created.children[2].get_param_name() == "created.year"
    assert f.created.children[2].children[0].get_param_name() == "created.year.gte"
    assert f.created.children[2].children[1].get_param_name() == "created.year.lte"


def test_filter_get_query_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter()
        name = Filter(param="first_name")
        surname = Filter(param="last_name")
        created = Filter(
            children=[
                Filter(param="gte"),
            ],
        )

    f = SomeFilterSet
    query_dict = QueryDict("username=kate&created.gte=2024-01-01&first_name=Katie")

    assert f.username.get_query_value(query_dict) == "kate"

    assert f.name.get_query_value(query_dict) == "Katie"
    assert f.surname.get_query_value(query_dict) is empty

    assert f.created.get_query_value(query_dict) is empty
    assert f.created.children[0].get_query_value(query_dict) == "2024-01-01"


def test_filter_get_serializer() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter()
        modified = Filter(serializers.DateTimeField())
        created = Filter(
            serializers.DateTimeField(),
            children=[
                Filter(param="gte"),
                Filter(serializers.DateField(), param="year"),
            ],
        )

    f = SomeFilterSet

    with pytest.raises(
        ValueError, match="Serializer could not be resolved for 'username'"
    ):
        f.username.get_serializer()

    assert isinstance(f.modified.get_serializer(), serializers.DateTimeField)
    assert isinstance(f.created.get_serializer(), serializers.DateTimeField)
    assert isinstance(f.created.children[0].get_serializer(), serializers.DateTimeField)
    assert isinstance(f.created.children[1].get_serializer(), serializers.DateField)
