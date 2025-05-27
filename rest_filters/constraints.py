from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext

from rest_framework.settings import api_settings

if TYPE_CHECKING:
    from rest_filters.filtersets import FilterSet


__all__ = [
    "Constraint",
    "MethodConstraint",
    "MutuallyExclusive",
    "MutuallyInclusive",
]


StrOrPromise = str


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

    def get_message(self, values: dict[str, Any]) -> dict[str, Any]:
        message = self._message or gettext(
            "Request failed to meet constraint: %(constraint)s"
        ) % {"constraint": self.__class__.__name__}
        return {api_settings.NON_FIELD_ERRORS_KEY: [message]}

    def check(self, values: dict[str, Any]) -> bool:
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

    def check(self, values: dict[str, Any]) -> bool:
        assert self.filterset, "Missing filterset for constraint"
        return getattr(self.filterset, self.method)(values)  # type: ignore[no-any-return]


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

    def get_message(self, values: dict[str, Any]) -> dict[str, Any]:
        if self._message:
            return super().get_message(values)
        return {
            api_settings.NON_FIELD_ERRORS_KEY: [
                gettext(
                    "Following fields are mutually exclusive,"
                    " you may only provide one of them: %(fields)s"
                )
                % {
                    "fields": ", ".join(
                        f'"{field}"' for field in self.fields if field in values
                    )
                }
            ]
        }

    def check(self, values: dict[str, Any]) -> bool:
        return sum(field in values for field in self.fields) <= 1


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

    def get_message(self, values: dict[str, Any]) -> dict[str, Any]:
        if self._message:
            return super().get_message(values)
        return {
            api_settings.NON_FIELD_ERRORS_KEY: [
                gettext(
                    "Following fields are mutually inclusive,"
                    " you must provide them all at once or none of them: %(fields)s"
                )
                % {"fields": ", ".join(f'"{field}"' for field in self.fields)}
            ]
        }

    def check(self, values: dict[str, Any]) -> bool:
        fields = [field in values for field in self.fields]
        return all(fields) if any(fields) else True
