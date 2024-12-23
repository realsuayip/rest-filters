from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext

from rest_framework.settings import api_settings

if TYPE_CHECKING:
    from rest_filters.filtersets import FilterSet


__all__ = [
    "Constraint",
    "MutuallyExclusive",
    "MutuallyInclusive",
]


StrOrPromise = str


class Constraint:
    def __init__(
        self,
        *,
        fields: Sequence[str],
        message: StrOrPromise = "",
        method: str | None = None,
    ) -> None:
        self.fields = fields
        self.message = message
        self.method = method
        self.filterset: FilterSet[Any] | None = None

    def get_message(self, **kwargs: Any) -> dict[str, Any]:
        message = self.message or gettext(
            "%(constraint)s failed for fields: %(fields)s"
        ) % {
            "constraint": self.__class__.__name__,
            "fields": ", ".join(f'"{field}"' for field in self.fields),
        }
        return {api_settings.NON_FIELD_ERRORS_KEY: [message]}

    def check(self, **kwargs: Any) -> bool:
        assert self.method, "Missing method for constraint"
        assert self.filterset, "Missing filterset for constraint"
        return getattr(self.filterset, self.method)(**kwargs)  # type: ignore[no-any-return]


class MutuallyExclusive(Constraint):
    def __init__(
        self,
        *,
        fields: Sequence[str],
        **kwargs: Any,
    ) -> None:
        assert len(fields) > 1, "Provide 2 or more fields for this constraint"
        super().__init__(fields=fields, **kwargs)

    def get_message(self, **kwargs: Any) -> dict[str, Any]:
        if self.message:
            return super().get_message(**kwargs)
        return {
            api_settings.NON_FIELD_ERRORS_KEY: [
                gettext(
                    "Following fields are mutually exclusive,"
                    " you may only provide one of them: %(fields)s"
                )
                % {
                    "fields": ", ".join(
                        f'"{field}"' for field in self.fields if field in kwargs
                    )
                }
            ]
        }

    def check(self, **kwargs: Any) -> bool:
        return sum(field in kwargs for field in self.fields) <= 1


class MutuallyInclusive(Constraint):
    def __init__(
        self,
        *,
        fields: Sequence[str],
        **kwargs: Any,
    ) -> None:
        assert len(fields) > 1, "Provide 2 or more fields for this constraint"
        super().__init__(fields=fields, **kwargs)

    def get_message(self, **kwargs: Any) -> dict[str, Any]:
        if self.message:
            return super().get_message(**kwargs)
        return {
            api_settings.NON_FIELD_ERRORS_KEY: [
                gettext(
                    "Following fields are mutually inclusive,"
                    " you must provide them all at once or none of them: %(fields)s"
                )
                % {"fields": ", ".join(f'"{field}"' for field in self.fields)}
            ]
        }

    def check(self, **kwargs: Any) -> bool:
        fields = [field in kwargs for field in self.fields]
        return all(fields) if any(fields) else True
