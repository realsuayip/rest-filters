import enum

from rest_framework import VERSION as DRF_VERSION, serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.fields import empty

import pytest

from rest_filters.fields import (
    CSVField,
    ListField,
    StrictBooleanField,
    VerboseChoiceField,
)


def test_csv_field() -> None:
    f1 = CSVField(child=serializers.CharField())
    f2 = CSVField(child=serializers.IntegerField())
    a, b, c, d, e = (
        f1.run_validation("hello"),
        f1.run_validation("hello,world"),
        f2.run_validation("1"),
        f2.run_validation("1,2,3"),
        f1.run_validation('hello,world,"hello, world"'),
    )

    assert a == ["hello"]
    assert b == ["hello", "world"]
    assert c == [1]
    assert d == [1, 2, 3]
    assert e == ["hello", "world", "hello, world"]


def test_list_field_skip() -> None:
    f1 = ListField(child=serializers.IntegerField(required=False))
    assert f1.run_validation([1, empty, 2]) == [1, 2]


def test_verbose_choice_field() -> None:
    f = VerboseChoiceField(choices=["hello", "world"])
    assert f.run_validation("hello") == "hello"

    with pytest.raises(serializers.ValidationError) as ctx:
        f.run_validation("jupiter")
    assert ctx.value.detail == [
        ErrorDetail(
            string="'jupiter' is not a valid choice, available choices are:"
            " 'hello', 'world'",
            code="invalid_choice",
        )
    ]


@pytest.mark.skipif(DRF_VERSION < "3.15", reason="not supported for DRF 3.14")
def test_verbose_choice_field_case_enum() -> None:
    class Status(int, enum.Enum):
        OPEN = 0
        CLOSED = 1

    f = VerboseChoiceField(choices=Status)
    assert f.run_validation("0") == Status.OPEN
    assert f.run_validation("1") == Status.CLOSED

    with pytest.raises(serializers.ValidationError) as ctx:
        f.run_validation("2")
    assert ctx.value.detail == [
        ErrorDetail(
            string="'2' is not a valid choice, available choices are: '0', '1'",
            code="invalid_choice",
        )
    ]


@pytest.mark.skipif(DRF_VERSION < "3.15", reason="not supported for DRF 3.14")
def test_verbose_choice_field_case_bare_enum() -> None:
    class Status(enum.Enum):
        OPEN = 0
        CLOSED = 1

    f = VerboseChoiceField(choices=Status)
    assert f.run_validation(Status.OPEN) == Status.OPEN
    assert f.run_validation(Status.CLOSED) == Status.CLOSED
    assert f.run_validation("0") == Status.OPEN
    assert f.run_validation("1") == Status.CLOSED

    with pytest.raises(serializers.ValidationError) as ctx:
        f.run_validation("2")
    assert ctx.value.detail == [
        ErrorDetail(
            string="'2' is not a valid choice, available choices are: '0', '1'",
            code="invalid_choice",
        )
    ]


def test_strict_boolean_field() -> None:
    f = StrictBooleanField()

    assert f.run_validation("true") is True
    assert f.run_validation("false") is False

    with pytest.raises(serializers.ValidationError) as ctx:
        f.run_validation("0")
    assert ctx.value.detail == [
        ErrorDetail(
            string="'0' is not a valid choice, available choices are: 'true', 'false'",
            code="invalid",
        )
    ]

    with pytest.raises(serializers.ValidationError) as ctx:
        f.run_validation("null")
    assert ctx.value.detail == [
        ErrorDetail(
            string="'null' is not a valid choice, available choices are:"
            " 'true', 'false'",
            code="invalid",
        )
    ]


def test_strict_boolean_field_allow_null() -> None:
    f = StrictBooleanField(allow_null=True)

    assert f.run_validation("true") is True
    assert f.run_validation("false") is False
    assert f.run_validation("null") is None
