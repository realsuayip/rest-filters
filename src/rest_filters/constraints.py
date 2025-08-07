from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext, ngettext

from rest_framework import serializers
from rest_framework.settings import api_settings

if TYPE_CHECKING:
    from django.utils.functional import _StrOrPromise as StrOrPromise

    from rest_filters.filtersets import FilterSet
else:
    from django.utils.functional import Promise as StrPromise

    StrOrPromise = str | StrPromise


__all__ = [
    "Constraint",
    "Dependency",
    "MethodConstraint",
    "MutuallyExclusive",
    "MutuallyInclusive",
]


class Constraint:
    def __init__(
        self,
        *,
        message: StrOrPromise = "",
        **kwargs: Any,
    ) -> None:
        self._message = message
        self.kwargs = kwargs
        self.filterset: FilterSet[Any] | None = None

    def get_message(self, values: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        message = self._message or gettext(
            "Request failed to meet constraint: %(constraint)s"
        ) % {"constraint": self.__class__.__name__}
        return {api_settings.NON_FIELD_ERRORS_KEY: [message]}

    def check(self, values: dict[str, Any]) -> None:
        raise NotImplementedError


class MethodConstraint(Constraint):
    def __init__(
        self,
        *,
        message: StrOrPromise = "",
        method: str,
        **kwargs: Any,
    ) -> None:
        self.method = method
        super().__init__(message=message, **kwargs)

    def check(self, values: dict[str, Any]) -> None:
        assert self.filterset, "Missing filterset for constraint"
        getattr(self.filterset, self.method)(values)


class MutuallyExclusive(Constraint):
    def __init__(
        self,
        *,
        message: StrOrPromise = "",
        fields: Sequence[str],
        **kwargs: Any,
    ) -> None:
        assert len(fields) > 1, "Provide 2 or more fields for this constraint"
        self.fields = fields
        super().__init__(message=message, **kwargs)

    def get_message(self, values: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        if self._message:
            return super().get_message(values, **kwargs)
        return {
            api_settings.NON_FIELD_ERRORS_KEY: [
                gettext(
                    "The following fields are mutually exclusive,"
                    " you may only provide one of them: %(fields)s"
                )
                % {
                    "fields": ", ".join(
                        f'"{field}"' for field in self.fields if field in values
                    )
                }
            ]
        }

    def check(self, values: dict[str, Any]) -> None:
        if sum(field in values for field in self.fields) > 1:
            raise serializers.ValidationError(self.get_message(values))


class MutuallyInclusive(Constraint):
    def __init__(
        self,
        *,
        message: StrOrPromise = "",
        fields: Sequence[str],
        **kwargs: Any,
    ) -> None:
        assert len(fields) > 1, "Provide 2 or more fields for this constraint"
        self.fields = fields
        super().__init__(message=message, **kwargs)

    def get_message(self, values: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        if self._message:
            return super().get_message(values, **kwargs)
        return {
            api_settings.NON_FIELD_ERRORS_KEY: [
                gettext(
                    "The following fields are mutually inclusive,"
                    " you must provide them all at once or none of them: %(fields)s"
                )
                % {"fields": ", ".join(f'"{field}"' for field in self.fields)}
            ]
        }

    def check(self, values: dict[str, Any]) -> None:
        fields = [field in values for field in self.fields]
        if any(fields) and not all(fields):
            raise serializers.ValidationError(self.get_message(values))


class Dependency(Constraint):
    def __init__(
        self,
        *,
        message: StrOrPromise = "",
        fields: Sequence[str],
        depends_on: Sequence[str],
        **kwargs: Any,
    ) -> None:
        self.fields = fields
        self.depends_on = depends_on
        super().__init__(message=message, **kwargs)

    def get_message(self, values: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        if self._message:
            return super().get_message(values, **kwargs)
        missing = kwargs["missing"]
        message = {}
        for field, dependencies in missing.items():
            message[field] = [
                ngettext(
                    "This query parameter also requires the following"
                    " parameter to be present: %(params)s",
                    "This query parameter also requires the following"
                    " parameters to be present: %(params)s",
                    len(dependencies),
                )
                % {"params": ", ".join(f'"{field}"' for field in dependencies)}
            ]
        return message

    def check(self, values: dict[str, Any]) -> None:
        missing = defaultdict(list)
        for field in self.fields:
            for dependency in self.depends_on:
                if field in values and dependency not in values:
                    missing[field].append(dependency)
        if missing:
            raise serializers.ValidationError(self.get_message(values, missing=missing))
