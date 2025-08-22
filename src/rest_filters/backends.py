"""
Copyright (c) 2025, Şuayip Üzülmez

All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet

from rest_framework import filters
from rest_framework.request import Request
from rest_framework.views import APIView

from rest_filters.utils import _get_filterset_schema, _MT_co

if TYPE_CHECKING:
    from rest_filters import FilterSet

__all__ = [
    "FilterBackend",
]


class FilterBackend(filters.BaseFilterBackend):
    def _get_filterset_class(self, view: APIView) -> type[FilterSet[Any]] | None:
        from rest_filters import FilterSet

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
        queryset: QuerySet[_MT_co],
        view: APIView,
    ) -> type[FilterSet[_MT_co]] | None:
        return self._get_filterset_class(view)

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

    def get_schema_operation_parameters(self, view: APIView) -> list[dict[str, Any]]:
        filterset = self._get_filterset_class(view)
        if filterset is None:
            return []
        return _get_filterset_schema(filterset=filterset, view=view)
