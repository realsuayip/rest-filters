from rest_framework import serializers
from rest_framework.fields import empty

from rest_filters.fields import CSVField, ListField


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
