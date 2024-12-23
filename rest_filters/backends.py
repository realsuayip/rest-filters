from typing import TYPE_CHECKING

from rest_framework import filters

__all__ = [
    "FilterBackend",
]

from rest_framework.views import APIView

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from rest_framework.request import Request

    from rest_filters import FilterSet
    from rest_filters.utils import _MT_co


class FilterBackend(filters.BaseFilterBackend):
    def get_filterset_class(
        self,
        request: Request,
        queryset: QuerySet[_MT_co],
        view: APIView,
    ) -> type[FilterSet[_MT_co]]:
        # todo def get_filterset_class
        return view.filterset_classes.get(view.action)  # type: ignore

    def get_filterset(
        self,
        request: Request,
        queryset: QuerySet[_MT_co],
        view: APIView,
    ) -> FilterSet[_MT_co]:
        klass = self.get_filterset_class(request, queryset, view)
        return klass(request, queryset, view)

    def filter_queryset(
        self,
        request: Request,
        queryset: QuerySet[_MT_co],
        view: APIView,
    ) -> QuerySet[_MT_co]:
        filterset = self.get_filterset(request, queryset, view)
        return filterset.get_queryset()
