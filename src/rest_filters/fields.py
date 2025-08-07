from typing import Any

from rest_framework import serializers


class CSVField(serializers.ListField):
    """
    Parses a comma-separated string into a list of values.

    Requires a ``child`` argument for validation and conversion for each item.
    You can provide ``serializers.ChoiceField`` as the child to simulate a
    multiple choice field.

    This is a subclass of ``serializers.ListField``, so you can specify
    parameters such as ``min_length``, ``max_length`` and ``allow_empty``.
    """

    def to_internal_value(self, data: Any) -> list[Any]:
        return super().to_internal_value(data.split(","))
