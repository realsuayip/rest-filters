from typing import Any

from django.test import override_settings

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.generics import ListAPIView
from rest_framework.test import APIRequestFactory

import pytest
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from rest_filters import Filter, FilterBackend, FilterSet, Multi
from rest_filters.fields import ListField, StrictBooleanField
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


@pytest.mark.parametrize("exc_type", (AttributeError, AssertionError))
@pytest.mark.django_db
def test_filter_backend_discover_from_get_filterset_class_case_method_raises(
    exc_type: type[BaseException],
) -> None:
    class UserView(ListAPIView[User]):
        serializer_class = UserSerializer
        queryset = User.objects.none()
        filter_backends = [FilterBackend]

        def get_filterset_class(self) -> type[FilterSet[User]]:
            raise exc_type

    factory = APIRequestFactory()
    request = factory.get("/?username=")
    with pytest.raises(exc_type):
        UserView.as_view()(request)


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
    @extend_schema_field(OpenApiTypes.NONE)
    class OmittedField(serializers.CharField):
        pass

    class SomeSerializer(serializers.Serializer[dict[str, Any]]):
        some_attr = serializers.CharField()

    @extend_schema_field(OpenApiTypes.NONE)
    class OmittedSerializer(serializers.Serializer[dict[str, Any]]):
        some_attr = serializers.CharField()

    @extend_schema_field(OpenApiTypes.STR)
    class StringSerializer(serializers.Serializer[dict[str, Any]]):
        some_attr = serializers.CharField()

    class SomeFilterSet(FilterSet[User]):
        username = Filter(
            serializers.CharField(
                min_length=3,
                max_length=8,
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
        is_active = Filter(StrictBooleanField())
        details = Filter(
            SomeSerializer(
                help_text="Details to match.",
                label="Details filter",
                allow_null=True,
                default={"some_attr": "hello"},
            ),
        )
        missing = Filter()
        secret = Filter(OmittedField())
        omitted_details = Filter(OmittedSerializer())
        string_details = Filter(StringSerializer(help_text="Encoded details."))

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
                "minLength": 3,
                "maxLength": 8,
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
            "schema": {"type": "string", "minLength": 2},
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
            "name": "is_active",
            "in": "query",
            "required": False,
            "schema": {
                "type": "boolean",
            },
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
                "description": "Details to match.",
                "title": "Details filter",
                "nullable": True,
                "default": {"some_attr": "hello"},
            },
            "explode": False,
        },
        {
            "name": "string_details",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "description": "Encoded details."},
            "explode": False,
        },
    ]


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    }
)
def test_filter_backend_get_schema_operation_parameters_case_primitives() -> None:
    class SomeFilterSet(FilterSet[User]):
        text = Filter(
            serializers.CharField(
                min_length=2,
                max_length=10,
                default="abc",
                label="Search text",
                help_text="Text to match.",
                allow_null=True,
            ),
            required=True,
        )
        pattern = Filter(serializers.RegexField(r"^[a-z]+$"))
        email = Filter(serializers.EmailField(max_length=100))
        url = Filter(serializers.URLField(max_length=200))
        integer = Filter(serializers.IntegerField(min_value=1, max_value=100))
        number = Filter(serializers.FloatField(min_value=0.5, max_value=10.5))
        decimal = Filter(
            serializers.DecimalField(
                max_digits=5,
                decimal_places=2,
                coerce_to_string=False,
            ),
        )
        boolean = Filter(serializers.BooleanField(default=False))
        date = Filter(serializers.DateField())
        datetime = Filter(serializers.DateTimeField())
        time = Filter(serializers.TimeField())
        uuid = Filter(serializers.UUIDField())
        choice = Filter(serializers.ChoiceField(choices=["red", "blue"]))
        blank_email = Filter(serializers.EmailField(allow_blank=True))

    class UserView(ListAPIView[User]):
        filterset_class = SomeFilterSet

    parameters = FilterBackend().get_schema_operation_parameters(UserView())
    schemas = {parameter["name"]: parameter["schema"] for parameter in parameters}
    choice_schema = schemas.pop("choice")
    assert choice_schema["type"] == "string"
    assert choice_schema["enum"] == ["red", "blue"]
    assert schemas == {
        "text": {
            "type": "string",
            "nullable": True,
            "default": "abc",
            "title": "Search text",
            "description": "Text to match.",
            "minLength": 2,
            "maxLength": 10,
        },
        "pattern": {"type": "string", "pattern": "^[a-z]+$"},
        "email": {"type": "string", "format": "email", "maxLength": 100},
        "url": {"type": "string", "format": "uri", "maxLength": 200},
        "integer": {"type": "integer", "minimum": 1, "maximum": 100},
        "number": {
            "type": "number",
            "format": "double",
            "minimum": 0.5,
            "maximum": 10.5,
        },
        "decimal": {
            "type": "number",
            "format": "double",
            "minimum": -1000,
            "maximum": 1000,
            "exclusiveMinimum": True,
            "exclusiveMaximum": True,
        },
        "boolean": {"type": "boolean", "default": False},
        "date": {"type": "string", "format": "date"},
        "datetime": {"type": "string", "format": "date-time"},
        "time": {"type": "string", "format": "time"},
        "uuid": {"type": "string", "format": "uuid"},
        "blank_email": {
            "oneOf": [
                {"type": "string", "format": "email"},
                {"type": "string", "maxLength": 0},
            ],
        },
    }
    assert parameters[0]["required"] is True
    assert all(parameter["required"] is False for parameter in parameters[1:])


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    }
)
def test_filter_backend_get_schema_operation_parameters_case_multi() -> None:
    class SomeFilterSet(FilterSet[User]):
        username = Filter(
            ListField(child=serializers.CharField()),
            multi=Multi.ALLOW,
        )

    class UserView(ListAPIView[User]):
        serializer_class = UserSerializer
        queryset = User.objects.none()
        filter_backends = [FilterBackend]
        filterset_class = SomeFilterSet

    factory = APIRequestFactory()
    view = UserView()
    view.request = factory.get("/?username=")

    schema = FilterBackend().get_schema_operation_parameters(view)
    assert schema == [
        {
            "name": "username",
            "in": "query",
            "required": False,
            "schema": {
                "type": "array",
                "items": {"type": "string"},
            },
            "explode": True,
        }
    ]


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    }
)
def test_filter_backend_get_schema_operation_parameters_case_multi_filterset() -> None:
    class SomeFilterSet(FilterSet[User]):
        username = Filter(
            ListField(child=serializers.CharField()),
        )

        class Meta:
            multi = Multi.ALLOW

    class UserView(ListAPIView[User]):
        serializer_class = UserSerializer
        queryset = User.objects.none()
        filter_backends = [FilterBackend]
        filterset_class = SomeFilterSet

    factory = APIRequestFactory()
    view = UserView()
    view.request = factory.get("/?username=")

    schema = FilterBackend().get_schema_operation_parameters(view)
    assert schema == [
        {
            "name": "username",
            "in": "query",
            "required": False,
            "schema": {
                "type": "array",
                "items": {"type": "string"},
            },
            "explode": True,
        }
    ]


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    }
)
def test_filter_backend_serializer_schema_context_is_isolated_between_views() -> None:
    class ContextSerializer(serializers.Serializer[dict[str, Any]]):
        def get_fields(self) -> dict[str, Any]:
            return {
                self.context["view"].field_name: serializers.CharField(),
            }

    class SomeFilterSet(FilterSet[User]):
        details = Filter(ContextSerializer())

    class FirstView(ListAPIView[User]):
        serializer_class = UserSerializer
        queryset = User.objects.none()
        filterset_class = SomeFilterSet
        field_name = "first"

    class SecondView(FirstView):
        field_name = "second"

    factory = APIRequestFactory()
    first_view = FirstView(format_kwarg=None)
    first_view.request = factory.get("/first/")
    second_view = SecondView(format_kwarg=None)
    second_view.request = factory.get("/second/")

    first = FilterBackend().get_schema_operation_parameters(first_view)
    second = FilterBackend().get_schema_operation_parameters(second_view)

    assert list(first[0]["schema"]["properties"]) == ["first"]
    assert list(second[0]["schema"]["properties"]) == ["second"]
    declared = SomeFilterSet._compiled_fields["details"].get_serializer()
    assert declared.context == {}


def test_filter_backend_get_schema_operation_parameters_case_missing_filterset() -> (
    None
):
    class UserView(ListAPIView[User]):
        serializer_class = UserSerializer
        queryset = User.objects.none()
        filter_backends = [FilterBackend]

    factory = APIRequestFactory()
    view = UserView()
    view.request = factory.get("/?username=")

    schema = FilterBackend().get_schema_operation_parameters(view)
    assert schema == []
