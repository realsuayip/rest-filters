from typing import Any

from django.db.models import Q
from django.test import override_settings

from rest_framework import serializers

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
