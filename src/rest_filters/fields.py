import csv
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

import django.core.exceptions
from django.utils.translation import gettext_lazy

from rest_framework import serializers
from rest_framework.fields import SkipField, get_error_detail

if TYPE_CHECKING:
    from django.utils.functional import _StrOrPromise as StrOrPromise

else:
    from django.utils.functional import Promise as StrPromise

    StrOrPromise = str | StrPromise


__all__ = [
    "CSVField",
    "ListField",
    "VerboseChoiceField",
]


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


class VerboseChoiceField(serializers.ChoiceField):
    """
    An alternative implementation of ``serializers.ChoiceField`` that also
    informs users of the available choices when invalid input is provided.
    """

    default_error_messages: ClassVar[dict[str, StrOrPromise]] = {
        "invalid_choice": gettext_lazy(
            "{input} is not a valid choice, available choices are: {choices}"
        ),
    }

    def to_internal_value(self, data: Any) -> Any:
        if data == "" and self.allow_blank:
            return ""
        if isinstance(data, Enum) and str(data) != str(data.value):
            data = data.value
        try:
            return self.choice_strings_to_values[str(data)]
        except KeyError:
            choices = ", ".join(
                repr(
                    str(
                        key.value
                        if isinstance(key, Enum) and str(key) != str(key.value)
                        else key
                    )
                )
                for key in self.choices
            )
            self.fail("invalid_choice", input=repr(str(data)), choices=choices)
