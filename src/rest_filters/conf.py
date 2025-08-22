
"""
Copyright (c) 2025, Şuayip Üzülmez

All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

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
    """
    There are a few settings that change how ``rest-filters`` behaves globally.
    Most of these settings can also be changed on a per-FilterSet basis.

    You can use these settings by adding the ``REST_FILTERS`` setting to your
    Django configuration file. For example:

    .. code-block:: python

        REST_FILTERS = {
            "BLANK": "keep",
            "KNOWN_PARAMETERS": ["page", "page_size"],
        }
    """

    BLANK: Literal["keep"] | Literal["omit"] = "omit"
    """
    Determines how empty query parameters are handled. Default is ``omit``
    which behaves as if query parameter was not provided. Setting this to
    ``keep`` will cause empty values to be parsed by the related field.
    """
    KNOWN_PARAMETERS: list[str] = notset  # type: ignore[assignment]
    """
    A list of query parameters that are not defined in FilterSet but otherwise
    used by other mechanisms, such as pagination.

    By default, the following query parameters are marked as known:

    - page
    - page_size
    - cursor
    - ``api_settings.ORDERING_PARAM``
    - ``api_settings.VERSION_PARAM``
    - ``api_settings.URL_FORMAT_OVERRIDE``
    """
    HANDLE_UNKNOWN_PARAMETERS: bool = True
    """
    Decides whether to handle unknown parameters.
    """
    DEFAULT_GROUP: str = "chain"
    """
    The default group for filters. By default, this is set to the reserved
    group ``chain``, which will chain ``filter()`` calls for each resolved
    query expression.
    """

    def __getattribute__(self, __name: str) -> Any:
        user_settings = getattr(settings, "REST_FILTERS", {})
        value = user_settings.get(__name, super().__getattribute__(__name))
        if value is notset:
            if __name == "KNOWN_PARAMETERS":
                # Can't use this as the default factory since it would access
                # DRF settings at import time.
                return get_default_known_parameters()
        return value


app_settings = AppSettings()
