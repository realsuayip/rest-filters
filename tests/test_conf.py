from typing import Any

from django.db.models import Q
from django.test import override_settings

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

import pytest

from rest_filters import Blank, Filter, FilterSet, Multi
from rest_filters.fields import ListField
from rest_filters.filters import Entry
from tests.test_filters import get_filterset_instance


def test_blank_default() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet, query="username=")
    groups, _ = instance.get_groups()
    assert groups == {}


@override_settings(REST_FILTERS={"BLANK": Blank.OMIT})
def test_blank_omit() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet, query="username=")
    groups, _ = instance.get_groups()
    assert groups == {}


@override_settings(REST_FILTERS={"BLANK": Blank.KEEP})
def test_blank_keep() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(allow_blank=True))

    instance = get_filterset_instance(SomeFilterSet, query="username=")
    groups, _ = instance.get_groups()
    assert groups == {
        "chain": {
            "username": Entry(
                group="chain",
                aliases=None,
                value="",
                expression=Q(username=""),
            )
        }
    }


def test_multi_default() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            ListField(child=serializers.CharField()),
        )

    instance = get_filterset_instance(
        SomeFilterSet, query="username=alice&username=bob"
    )
    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()
    assert ctx.value.detail == {
        "username": [
            ErrorDetail(
                string="This query parameter does not allow specifying"
                " multiple values.",
                code="invalid",
            )
        ]
    }


@override_settings(REST_FILTERS={"MULTI": Multi.DISALLOW})
def test_multi_disallow() -> None:
    test_multi_default()


@override_settings(REST_FILTERS={"MULTI": Multi.ALLOW})
def test_multi_allow() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            ListField(child=serializers.CharField()),
            lookup="in",
        )

    instance = get_filterset_instance(
        SomeFilterSet, query="username=alice&username=bob"
    )
    groups, _ = instance.get_groups()
    assert groups == {
        "chain": {
            "username": Entry(
                group="chain",
                aliases=None,
                value=["alice", "bob"],
                expression=Q(username__in=["alice", "bob"]),
            )
        }
    }


@override_settings(REST_FILTERS={"MULTI": Multi.FIRST})
def test_multi_first() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(
        SomeFilterSet, query="username=alice&username=bob"
    )
    groups, _ = instance.get_groups()
    assert groups == {
        "chain": {
            "username": Entry(
                group="chain",
                aliases=None,
                value="alice",
                expression=Q(username="alice"),
            )
        }
    }


@override_settings(REST_FILTERS={"MULTI": Multi.LAST})
def test_multi_last() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(
        SomeFilterSet, query="username=alice&username=bob"
    )
    groups, _ = instance.get_groups()
    assert groups == {
        "chain": {
            "username": Entry(
                group="chain",
                aliases=None,
                value="bob",
                expression=Q(username="bob"),
            )
        }
    }


def test_handle_unknown_parameters_default() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet, query="unrelated=")
    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()
    assert ctx.value.detail == {
        "unrelated": [
            ErrorDetail(string="This query parameter does not exist.", code="invalid")
        ]
    }


@override_settings(REST_FILTERS={"HANDLE_UNKNOWN_PARAMETERS": True})
def test_handle_unknown_parameters_true() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet, query="unrelated=")
    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()
    assert ctx.value.detail == {
        "unrelated": [
            ErrorDetail(string="This query parameter does not exist.", code="invalid")
        ]
    }


@override_settings(REST_FILTERS={"HANDLE_UNKNOWN_PARAMETERS": False})
def test_handle_unknown_parameters_false() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet, query="unrelated=&username=abc")
    _, valuedict = instance.get_groups()
    assert valuedict == {"username": "abc"}


def test_known_parameters_default() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    assert SomeFilterSet.options.known_parameters == [
        "page",
        "page_size",
        "cursor",
        "ordering",
        "version",
        "format",
    ]


@override_settings(
    REST_FRAMEWORK={
        "ORDERING_PARAM": "my_ordering_param",
        "VERSION_PARAM": "my_version_param",
        "URL_FORMAT_OVERRIDE": None,
    }
)
def test_known_parameters_default_drf_dynamic_override() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    assert SomeFilterSet.options.known_parameters == [
        "page",
        "page_size",
        "cursor",
        "my_ordering_param",
        "my_version_param",
    ]


@override_settings(REST_FILTERS={"KNOWN_PARAMETERS": ["hello", "world"]})
def test_known_parameters_custom() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    assert SomeFilterSet.options.known_parameters == ["hello", "world"]


@override_settings(REST_FILTERS={"KNOWN_PARAMETERS": []})
def test_known_parameters_custom_empty() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    assert SomeFilterSet.options.known_parameters == []


def test_default_group_default() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet, query="username=hello")
    groups, _ = instance.get_groups()
    assert list(groups) == ["chain"]


@override_settings(REST_FILTERS={"DEFAULT_GROUP": "custom"})
def test_default_group_custom() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet, query="username=hello")
    groups, _ = instance.get_groups()
    assert list(groups) == ["custom"]
