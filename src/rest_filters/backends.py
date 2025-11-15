from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from django.db.models import Model

from rest_filters.utils import _get_filterset_schema

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from rest_framework.generics import BaseFilterProtocol as BaseFilterBackend
    from rest_framework.request import Request
    from rest_framework.views import APIView

    from rest_filters import FilterSet
else:
    BaseFilterBackend = Generic


_MT_inv = TypeVar("_MT_inv", bound=Model)


__all__ = [
    "FilterBackend",
]


class FilterBackend(BaseFilterBackend[_MT_inv]):
    def _get_filterset_class(self, view: APIView) -> type[FilterSet[Any]] | None:
        from rest_filters import FilterSet  # noqa: PLC0415

        if (klass := getattr(view, "filterset_class", None)) and issubclass(
            klass, FilterSet
        ):
            return klass  # type: ignore[no-any-return]
        try:
            return view.get_filterset_class()  # type: ignore[no-any-return, attr-defined]
        except AttributeError:
            return None

    def get_filterset_class(
        self,
        request: Request,
        queryset: QuerySet[_MT_inv],
        view: APIView,
    ) -> type[FilterSet[_MT_inv]] | None:
        return self._get_filterset_class(view)

    def get_filterset(
        self,
        request: Request,
        queryset: QuerySet[_MT_inv],
        view: APIView,
    ) -> FilterSet[_MT_inv] | None:
        klass = self.get_filterset_class(request, queryset, view)
        if klass is None:
            return None
        return klass(request, queryset, view)

    def filter_queryset(
        self,
        request: Request,
        queryset: QuerySet[_MT_inv],
        view: APIView,
    ) -> QuerySet[_MT_inv]:
        filterset = self.get_filterset(request, queryset, view)
        if filterset is None:
            return queryset
        return filterset.filter_queryset()

    def get_schema_operation_parameters(self, view: APIView) -> list[dict[str, Any]]:
        filterset = self._get_filterset_class(view)
        if filterset is None:
            return []
        return _get_filterset_schema(filterset=filterset, view=view)
