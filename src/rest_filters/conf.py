from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from rest_framework.settings import api_settings

from rest_filters.utils import notset


class Blank(str, enum.Enum):
    """
    Determines how empty query parameters are handled.

    For example: ``?value=``
    """

    KEEP = "keep"
    """
    Keep empty query parameter as a blank string.
    """

    OMIT = "omit"
    """
    Treat this parameter as if it was not provided.
    """


class Multi(str, enum.Enum):
    """
    Determines what to do in the case of multivalued query parameters.

    For example: ``?value=hello&value=world``
    """

    ALLOW = "allow"
    """
    Allow multi value query parameters. All values will be collected into
    a list. Notice that resulting value will always be a list, even if there is
    a single parameter.

    This mode is not compatible with DRF's ``ListField`` due to an implementation
    detail. Use :py:class:`rest_filters.fields.ListField` instead to get correct
    behavior.
    """

    DISALLOW = "disallow"
    """
    Disallow multi value query parameters. If a parameter is provided more than
    once, an error message will be displayed.
    """

    FIRST = "first"
    """
    Allow multi value query parameters, but only use **the first value**. Other
    values are discarded.
    """

    LAST = "last"
    """
    Allow multi value query parameters, but only use **the last value**. Other
    values are discarded.
    """


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

        from rest_filters import Blank

        REST_FILTERS = {
            "BLANK": Blank.KEEP,
            "KNOWN_PARAMETERS": ["page", "page_size"],
        }
    """

    BLANK: Blank = Blank.OMIT
    """
    Determines how empty query parameters are handled. Default is
    :py:attr:`rest_filters.Blank.OMIT`, which behaves as if query parameter
    was not provided. Setting this to :py:attr:`rest_filters.Blank.KEEP` will
    cause empty values to be parsed by the related field.
    """
    MULTI: Multi = Multi.DISALLOW
    """
    Determines how multi-value query parameters are handled. See
    :py:class:`rest_filters.Multi` for available options. By default, multiple
    value query parameters are not allowed and an error message will be
    displayed.
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

    def __getattribute__(self, /, __name: str) -> Any:
        user_settings = getattr(settings, "REST_FILTERS", {})
        value = user_settings.get(__name, super().__getattribute__(__name))
        if value is notset and __name == "KNOWN_PARAMETERS":
            # Can't use this as the default factory since it would access
            # DRF settings at import time.
            return get_default_known_parameters()
        return value


app_settings = AppSettings()
