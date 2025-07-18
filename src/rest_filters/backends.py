from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import QuerySet

from rest_framework import filters
from rest_framework.request import Request
from rest_framework.views import APIView

from rest_filters.utils import _MT_co

if TYPE_CHECKING:
    from rest_filters import FilterSet

__all__ = [
    "FilterBackend",
]


class FilterBackend(filters.BaseFilterBackend):
    def get_filterset_class(
        self,
        request: Request,
        queryset: QuerySet[_MT_co],
        view: APIView,
    ) -> type[FilterSet[_MT_co]] | None:
        if klass := getattr(view, "filterset_class", None):
            return klass  # type: ignore[no-any-return]
        try:
            return view.get_filterset_class()  # type: ignore[no-any-return, attr-defined]
        except AttributeError:
            return None

    def get_filterset(
        self,
        request: Request,
        queryset: QuerySet[_MT_co],
        view: APIView,
    ) -> FilterSet[_MT_co] | None:
        klass = self.get_filterset_class(request, queryset, view)
        if klass is None:
            return None
        return klass(request, queryset, view)

    def filter_queryset(
        self,
        request: Request,
        queryset: QuerySet[_MT_co],
        view: APIView,
    ) -> QuerySet[_MT_co]:
        filterset = self.get_filterset(request, queryset, view)
        if filterset is None:
            return queryset
        return filterset.filter_queryset()
