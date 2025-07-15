from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from django.conf import settings

from rest_framework.settings import api_settings

from rest_filters.utils import notset


def get_default_known_parameters() -> list[str]:
    params = [
        "page",
        "page_size",
        "cursor",
        api_settings.ORDERING_PARAM,
        api_settings.VERSION_PARAM,
    ]
    if format_param := api_settings.URL_FORMAT_OVERRIDE:
        params.append(format_param)
    return params


@dataclass(frozen=True)
class AppSettings:
    BLANK: Literal["keep"] | Literal["omit"] = "omit"
    KNOWN_PARAMETERS: list[str] = notset  # type: ignore[assignment]
    HANDLE_UNKNOWN_PARAMETERS: bool = True

    def __getattribute__(self, __name: str) -> Any:
        user_settings = getattr(settings, "REST_FILTERS", {})
        value = user_settings.get(__name, super().__getattribute__(__name))
        if value is notset:
            if __name == "KNOWN_PARAMETERS":
                # Can't use this as default factory since it would access DRF
                # settings at import time.
                return get_default_known_parameters()
        return value


app_settings = AppSettings()
