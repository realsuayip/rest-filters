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

import enum
import warnings
from typing import TYPE_CHECKING, Any, Final, TypeVar

from django.db import models
from django.db.models import Q

from rest_framework import serializers
from rest_framework.fields import Field

_MT_co = TypeVar("_MT_co", bound=models.Model, covariant=True)

NotSet = enum.Enum("NotSet", "notset")
notset: Final = NotSet.notset

if TYPE_CHECKING:
    from rest_framework.views import APIView

    from rest_filters import Filter, FilterSet

    AnyField = Field[Any, Any, Any, Any]
else:
    AnyField = Field


def fill_q_template(template: Q, *, value: Any) -> Q:
    conditions: list[Any] = []
    for child in template.children:
        if isinstance(child, Q):
            conditions.append(fill_q_template(child, value=value))
        else:
            if isinstance(child, tuple):
                field, value = child
                raise ValueError(
                    "Q objects should not specify values in templates, got"
                    " Q(%(field)s=%(value)r), expected Q(%(field)r)."
                    " If you would like to do more complex queries, use `method`"
                    " argument." % {"field": field, "value": value}
                )
            conditions.append((child, value))
    return Q(
        *conditions,
        _connector=template.connector,
        _negated=template.negated,
    )


def merge_errors(
    source: dict[str, Any],
    errors: dict[str, Any],
) -> None:
    for key, detail in errors.items():
        src = source.get(key)
        if isinstance(src, list):
            if isinstance(detail, (list, tuple)):
                source[key].extend(detail)
            else:
                source[key].append(detail)
        elif isinstance(src, dict) and isinstance(detail, dict):
            merge_errors(source[key], detail)
        else:
            source.setdefault(key, detail)


def _filter_to_schema(
    f: Filter,
    /,
    *,
    view: APIView,
) -> dict[str, Any] | None:
    try:
        field = f.get_serializer()
    except ValueError:
        warnings.warn(
            "Could not determine schema for query parameter: %s" % f.get_param_name(),
            stacklevel=1,
        )
        return None
    if isinstance(field, serializers.Serializer):
        schema = view.schema._map_serializer(field, "request")  # type: ignore[union-attr]
    else:
        schema = view.schema._map_serializer_field(field, "request")  # type: ignore[union-attr]
    return {
        "name": f.get_param_name(),
        "in": "query",
        "required": f.required,
        "schema": schema,
        "explode": False,
    }


def _get_filterset_schema(
    *,
    filterset: type[FilterSet[Any]],
    view: APIView,
) -> list[dict[str, Any]]:
    ret = []
    for _, field in filterset.compiled_fields.items():
        for f in [field, *field.get_all_children()]:
            if f.namespace:
                continue
            schema = _filter_to_schema(f, view=view)
            if schema is not None:
                ret.append(schema)
    return ret
