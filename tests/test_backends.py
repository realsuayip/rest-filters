from rest_framework.exceptions import ErrorDetail
from rest_framework.generics import ListAPIView
from rest_framework.test import APIRequestFactory

import pytest

from rest_filters import FilterBackend, FilterSet
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
