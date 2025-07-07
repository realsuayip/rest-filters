from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from django.conf import settings


@dataclass(frozen=True)
class AppSettings:
    BLANK: Literal["keep"] | Literal["omit"] = "omit"
    HANDLE_UNKNOWN_PARAMETERS: bool = True

    def __getattribute__(self, __name: str) -> Any:
        user_settings = getattr(settings, "REST_FILTERS", {})
        return user_settings.get(__name, super().__getattribute__(__name))


app_settings = AppSettings()
