from typing import Any

from django.db.models import Q


def fill_q_template(template: Q, *, value: Any) -> Q:
    conditions = []
    for child in template.children:
        if isinstance(child, Q):
            conditions.append(fill_q_template(child, value=value))
        else:
            if isinstance(child, tuple):
                field, value = child
                raise ValueError(
                    "Q objects should not specify values in templates, got"
                    " Q(%(field)s=%(value)r), expected Q(%(field)r)."
                    " If you would like to do more complex queries, use `method`"
                    " argument." % {"field": field, "value": value}
                )
            conditions.append((child, value))
    return Q(
        *conditions,
        _connector=template.connector,
        _negated=template.negated,
    )


def merge_errors(
    source: dict[str, Any],
    errors: dict[str, Any],
) -> None:
    for key, detail in errors.items():
        if isinstance(source.get(key), list):
            source[key].extend(detail)
        else:
            source[key] = detail
