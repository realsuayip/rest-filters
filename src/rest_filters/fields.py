import csv
from typing import Any

import django.core.exceptions

from rest_framework import serializers

__all__ = [
    "CSVField",
    "ListField",
]


from rest_framework.fields import SkipField, get_error_detail


class ListField(serializers.ListField):
    """
    Parses list of values. Can be used with ``Multi.ALLOW`` to collect
    multivalue query parameters to a list.

    Requires a ``child`` argument for validation and conversion for each item.

    If you need to parse a list from a single query parameter, you should use
    ``CSVField`` instead.

    To use this field, your lookup needs to support list objects on the right
    hand side. For example ``__in`` lookups. Alternatively, you can use a
    filter method to combine parsed values with ``Q`` or other expressions.
    """

    def run_child_validation(self, data: list[Any]) -> list[Any]:
        result = []
        errors = {}

        for idx, item in enumerate(data):
            try:
                result.append(self.child.run_validation(item))
            except serializers.ValidationError as e:  # noqa: PERF203
                errors[idx] = e.detail
            except django.core.exceptions.ValidationError as e:
                errors[idx] = get_error_detail(e)  # type: ignore[assignment]
            except SkipField:
                pass

        if not errors:
            return result
        raise serializers.ValidationError(errors)  # type: ignore[arg-type]


class CSVField(ListField):
    """
    Parses a comma-separated string into a list of values.

    Requires a ``child`` argument for validation and conversion for each item.
    You can provide ``serializers.ChoiceField`` as the child to simulate a
    multiple-choice field.

    This is a subclass of ``serializers.ListField``, so you can specify
    parameters such as ``min_length``, ``max_length`` and ``allow_empty``.
    """

    def to_internal_value(self, data: Any) -> list[Any]:
        return super().to_internal_value(next(csv.reader([data])))
