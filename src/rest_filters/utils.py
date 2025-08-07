from __future__ import annotations

import enum
import warnings
from typing import TYPE_CHECKING, Any, Final, TypeVar

from django.db import models
from django.db.models import Q

from rest_framework import serializers
from rest_framework.fields import Field

AnyField = Field[Any, Any, Any, Any]
_MT_co = TypeVar("_MT_co", bound=models.Model, covariant=True)

NotSet = enum.Enum("NotSet", "notset")
notset: Final = NotSet.notset

if TYPE_CHECKING:
    from rest_framework.views import APIView

    from rest_filters import Filter, FilterSet


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
        "required": field.required,
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
