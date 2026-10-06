from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Generic

from rest_filters.filtersets.base import BaseFilterSet
from rest_filters.utils import _MT_co

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import QueryDict

    from rest_framework.request import Request
    from rest_framework.views import APIView

    from rest_filters.filters import Entry
    from rest_filters.filtersets.base import Entries, Groups


class FilterSet(BaseFilterSet, Generic[_MT_co]):
    class Meta:
        abstract = True

    def __init__(
        self,
        request: Request,
        queryset: QuerySet[_MT_co],
        view: APIView,
    ) -> None:
        super().__init__()
        self.request = request
        """Django REST framework ``Request`` object."""
        self.queryset = queryset
        self.view = view
        """View instance for this request."""

    def add_to_queryset(
        self, queryset: QuerySet[_MT_co], entry: Entry
    ) -> QuerySet[_MT_co]:
        if entry.expression is None:
            return queryset
        if entry.aliases:
            queryset = queryset.alias(**entry.aliases)
        return queryset.filter(entry.expression)

    def filter_group(
        self,
        queryset: QuerySet[_MT_co],
        group: str,
        entries: Entries,
    ) -> QuerySet[_MT_co]:
        return self.add_to_queryset(queryset, self.get_group_entry(group, entries))

    def filter_group_namespace(
        self,
        queryset: QuerySet[_MT_co],
        root: str,
        groups: Groups,
    ) -> QuerySet[_MT_co]:
        return self.add_to_queryset(
            queryset,
            self._resolve_group_namespace(root, groups),
        )

    def filter_queryset(self) -> QuerySet[_MT_co]:
        queryset = self.queryset
        groupdict, valuedict = self.get_groups()

        for entry in groupdict.pop("chain", {}).values():
            queryset = self.add_to_queryset(queryset, entry)

        ns: defaultdict[str, Groups] = defaultdict(dict)
        for name, entries in groupdict.items():
            root = name.split(".", maxsplit=1)[0]
            ns[root][name] = entries

        for root, groups in ns.items():
            if len(groups) == 1:
                group, entries = next(iter(groups.items()))
                queryset = self.filter_group(queryset, group, entries)
            else:
                queryset = self.filter_group_namespace(queryset, root, groups)
        return self.get_queryset(queryset, valuedict)

    def get_queryset(
        self,
        queryset: QuerySet[_MT_co],
        values: dict[str, Any],
    ) -> QuerySet[_MT_co]:
        """
        Returns the final QuerySet object. At this point, all the filters are
        applied. Override this method to perform operations on QuerySet that
        are otherwise not possible, such as ``order_by()`` and ``distinct()``
        calls.

        :param queryset: Filtered QuerySet object.
        :param values: Parsed query parameters.
        """
        return queryset

    def get_query_params(self) -> QueryDict:
        return self.request.query_params

    def get_serializer_context(self, param: str) -> dict[str, Any]:
        """
        Get serializer context for the given param. By default, this will use
        ``view.get_serializer_context()``. The context will also include this
        FilterSet instance.

        :param param: Parameter name.
        :return: Context dictionary.
        """
        context = super().get_serializer_context(param)
        view_context = self.view.get_serializer_context()
        return view_context | context
