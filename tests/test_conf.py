from typing import Any

from django.db.models import Q
from django.test import override_settings

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

import pytest

from rest_filters import Filter, FilterSet
from rest_filters.filters import Entry
from tests.test_filters import get_filterset_instance


def test_blank_default() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(required=False))

    instance = get_filterset_instance(SomeFilterSet, query="username=")
    groups, _ = instance.get_groups()
    assert groups == {}


@override_settings(REST_FILTERS={"BLANK": "omit"})
def test_blank_omit() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(required=False))

    instance = get_filterset_instance(SomeFilterSet, query="username=")
    groups, _ = instance.get_groups()
    assert groups == {}


@override_settings(REST_FILTERS={"BLANK": "keep"})
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


def test_handle_unknown_parameters_default() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(required=False))

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
        username = Filter(serializers.CharField(required=False))

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
        username = Filter(serializers.CharField(required=False))

    instance = get_filterset_instance(SomeFilterSet, query="unrelated=&username=abc")
    _, valuedict = instance.get_groups()
    assert valuedict == {"username": "abc"}
