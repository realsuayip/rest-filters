from typing import Any

from django.db.models import Q

import pytest

from rest_filters.utils import fill_q_template, merge_errors


@pytest.mark.parametrize(
    "template, result",
    [
        (
            Q("username"),
            Q(username="admin"),
        ),
        (
            ~Q("username"),
            ~Q(username="admin"),
        ),
        (
            Q("username") & Q("email"),
            Q(username="admin") & Q(email="admin"),
        ),
        (
            ~(Q("username") & Q("email")),
            ~(Q(username="admin") & Q(email="admin")),
        ),
        (
            Q("username") | ~Q("email"),
            Q(username="admin") | ~Q(email="admin"),
        ),
    ],
)
def test_fill_q_template(template: Q, result: Q) -> None:
    assert fill_q_template(template, value="admin") == result


def test_fill_q_template_case_value_specified() -> None:
    with pytest.raises(ValueError) as ctx:
        fill_q_template(
            Q(username="admin"),
            value="admin",
        )
    assert ctx.value.args == (
        "Q objects should not specify values in templates, got"
        " Q(username='admin'), expected Q('username'). If you would like to do"
        " more complex queries, use `method` argument.",
    )


@pytest.mark.parametrize(
    "source, errors, merged",
    [
        (
            {"non_field_errors": ["some error"]},
            {"non_field_errors": ["some other error"]},
            {"non_field_errors": ["some error", "some other error"]},
        ),
        (
            {"non_field_errors": ["some error"]},
            {"non_field_errors": ("some other error",)},
            {"non_field_errors": ["some error", "some other error"]},
        ),
        (
            {"field1": ["some error"]},
            {"field2": ["some other error"]},
            {
                "field1": ["some error"],
                "field2": ["some other error"],
            },
        ),
        (
            {"field1": ["some error"]},
            {"field1": "some other error"},
            {
                "field1": ["some error", "some other error"],
            },
        ),
        (
            {"field1": ["some error"]},
            {
                "field1": {
                    "error": "detail",
                }
            },
            {
                "field1": [
                    "some error",
                    {
                        "error": "detail",
                    },
                ],
            },
        ),
        (
            {"field1": "some error"},
            {"field1": "some other error"},
            {
                "field1": "some error",
            },
        ),
        (
            {},
            {"field1": "some other error"},
            {
                "field1": "some other error",
            },
        ),
        (
            {"errors": {"field1": ["hello"]}},
            {"errors": {"field1": ["world"]}},
            {
                "errors": {
                    "field1": ["hello", "world"],
                },
            },
        ),
        (
            {"errors": None},
            {"errors": ["world"]},
            {
                "errors": None,
            },
        ),
    ],
)
def test_merge_errors(
    source: dict[str, Any],
    errors: dict[str, Any],
    merged: dict[str, Any],
) -> None:
    merge_errors(source, errors)
    assert source == merged
