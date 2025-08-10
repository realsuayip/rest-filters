from typing import Any

from django.test import override_settings

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.generics import ListAPIView
from rest_framework.test import APIRequestFactory

import pytest

from rest_filters import Filter, FilterBackend, FilterSet
from tests.testapp.models import User
from tests.testapp.views import UserSerializer


def test_filter_backend_discover_from_filterset_class_attribute() -> None:
    class SomeFilterSet(FilterSet[User]):
        pass

    class UserView(ListAPIView[User]):
        serializer_class = UserSerializer
        queryset = User.objects.all()
        filterset_class = SomeFilterSet
        filter_backends = [FilterBackend]

    factory = APIRequestFactory()
    request = factory.get("/?username=")
    response = UserView.as_view()(request)
    assert response.data == {
        "username": [
            ErrorDetail(
                string="This query parameter does not exist.",
                code="invalid",
            )
        ]
    }


def test_filter_backend_discover_from_get_filterset_class() -> None:
    class SomeFilterSet(FilterSet[User]):
        pass

    class UserView(ListAPIView[User]):
        serializer_class = UserSerializer
        queryset = User.objects.all()
        filter_backends = [FilterBackend]

        def get_filterset_class(self) -> type[FilterSet[User]]:
            return SomeFilterSet

    factory = APIRequestFactory()
    request = factory.get("/?username=")
    response = UserView.as_view()(request)
    assert response.data == {
        "username": [
            ErrorDetail(
                string="This query parameter does not exist.",
                code="invalid",
            )
        ]
    }


@pytest.mark.django_db
def test_filter_backend_noop_when_filterset_not_found() -> None:
    class UserView(ListAPIView[User]):
        serializer_class = UserSerializer
        queryset = User.objects.all()
        filter_backends = [FilterBackend]

    factory = APIRequestFactory()
    request = factory.get("/?username=")
    response = UserView.as_view()(request)
    assert response.data == []


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    }
)
def test_filter_backend_get_schema_operation_parameters() -> None:
    class SomeSerializer(serializers.Serializer[dict[str, Any]]):
        some_attr = serializers.CharField()

    class SomeFilterSet(FilterSet[User]):
        username = Filter(
            serializers.CharField(
                min_length=2,
                help_text="Provide username.",
            ),
            required=True,
        )
        company = Filter(
            namespace=True,
            children=[
                Filter(
                    serializers.IntegerField(min_value=1),
                    lookup="id",
                ),
                Filter(
                    serializers.CharField(min_length=2),
                    lookup="name",
                ),
                Filter(
                    serializers.DateTimeField(),
                    param="created",
                    field="company__created",
                    namespace=True,
                    children=[
                        Filter(lookup="gte"),
                        Filter(lookup="lte"),
                        Filter(
                            serializers.IntegerField(
                                min_value=1900,
                                max_value=2050,
                            ),
                            lookup="year",
                        ),
                    ],
                ),
            ],
        )
        created = Filter(
            serializers.DateField(),
            children=[
                Filter(lookup="gte"),
                Filter(lookup="lte"),
            ],
        )
        details = Filter(SomeSerializer())
        missing = Filter()

    class UserView(ListAPIView[User]):
        serializer_class = UserSerializer
        queryset = User.objects.all()
        filterset_class = SomeFilterSet
        filter_backends = [FilterBackend]

    factory = APIRequestFactory()
    view = UserView()
    view.request = factory.get("/?username=")

    with pytest.warns(
        UserWarning,
        match="Could not determine schema for query parameter: missing",
    ):
        schema = FilterBackend().get_schema_operation_parameters(view)
    assert schema == [
        {
            "name": "username",
            "in": "query",
            "required": True,
            "schema": {
                "description": "Provide username.",
                "type": "string",
            },
            "explode": False,
        },
        {
            "name": "company.id",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "minimum": 1},
            "explode": False,
        },
        {
            "name": "company.name",
            "in": "query",
            "required": False,
            "schema": {"type": "string"},
            "explode": False,
        },
        {
            "name": "company.created.gte",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "format": "date-time"},
            "explode": False,
        },
        {
            "name": "company.created.lte",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "format": "date-time"},
            "explode": False,
        },
        {
            "name": "company.created.year",
            "in": "query",
            "required": False,
            "schema": {"type": "integer", "maximum": 2050, "minimum": 1900},
            "explode": False,
        },
        {
            "name": "created",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "format": "date"},
            "explode": False,
        },
        {
            "name": "created.gte",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "format": "date"},
            "explode": False,
        },
        {
            "name": "created.lte",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "format": "date"},
            "explode": False,
        },
        {
            "name": "details",
            "in": "query",
            "required": False,
            "schema": {
                "type": "object",
                "properties": {"some_attr": {"type": "string"}},
                "required": ["some_attr"],
            },
            "explode": False,
        },
    ]
