from typing import Any

from rest_framework import serializers


class CSVField(serializers.ListField):
    def to_internal_value(self, data: Any) -> list[Any]:
        return super().to_internal_value(data.split(","))
