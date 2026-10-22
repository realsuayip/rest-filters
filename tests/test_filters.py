import datetime
from typing import Any, ClassVar, TypeVar, cast
from unittest.mock import MagicMock, call

from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Length
from django.http import QueryDict
from django.test.utils import isolate_apps

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.fields import empty
from rest_framework.test import APIRequestFactory

import pytest

from rest_filters import Blank, Filter, FilterSet, Multi
from rest_filters.fields import CSVField, ListField
from rest_filters.filters import Entry
from rest_filters.utils import AnyField, notset
from tests.testapp.views import UserView

T = TypeVar("T", bound=FilterSet[Any])


def get_filterset_instance(klass: type[T], *, query: str = "") -> T:
    factory = APIRequestFactory()
    view = UserView(format_kwarg="format")
    request = view.initialize_request(factory.get(f"/?{query}"))
    view.setup(request)
    return klass(request, view.queryset, view)


def test_filter_defaults() -> None:
    f = Filter()

    assert f.lookup == ""
    assert f.negate is False
    assert f.namespace is False
    assert f.children == []

    assert f.parent is None
    assert f.aliases is None
    assert f.template is None
    assert f.method is None
    assert f.required is False


@pytest.mark.parametrize(
    "group",
    (
        "not-a-valid-identifier",
        "2invalid",
        "invalid.2",
        "invalid$",
        "@invalid",
        "invalid.@",
        ".invalid",
        "..invalid",
        "invalid.",
        "invalid..",
    ),
)
def test_filter_group_is_valid_identifier(group: str) -> None:
    with pytest.raises(ValueError, match="must be valid Python"):
        Filter(group=group)


def test_filter_group_chain_used_as_subgroup() -> None:
    with pytest.raises(
        ValueError, match="Reserved group 'chain' cannot be used as namespace"
    ):
        Filter(group="chain.hello")


def test_filter_blank_invalid_choice() -> None:
    with pytest.raises(ValueError, match="'empty' is not valid blank value"):
        Filter(blank="empty")  # type: ignore[arg-type]

    f1 = Filter(blank=Blank.KEEP)
    f2 = Filter(blank=Blank.OMIT)

    assert f1.blank == Blank.KEEP
    assert f2.blank == Blank.OMIT


def test_filter_template_and_field_provided() -> None:
    with pytest.raises(ValueError, match="cannot be used") as ctx:
        Filter(
            field="username",
            template=Q("hello"),
        )
    assert ctx.value.args == ("'template' and 'field' cannot be used together",)


def test_filter_template_and_lookup_provided() -> None:
    with pytest.raises(ValueError, match="cannot be used") as ctx:
        Filter(
            lookup="icontains",
            template=Q("username"),
        )
    assert ctx.value.args == (
        "'template' and 'lookup' cannot be used together. Add lookup to"
        " your template instead, for example: Q('username__icontains')",
    )


def test_filter_negate_and_method_provided() -> None:
    with pytest.raises(ValueError, match="cannot be used") as ctx:
        Filter(
            negate=True,
            method="my_method",
        )
    assert ctx.value.args == (
        "'method' and 'negate' cannot be used together. Negate the expression"
        " in your method instead.",
    )


def test_filter_multi_bad_value() -> None:
    with pytest.raises(
        ValueError,
        match="'unknown' is not valid multi value",
    ):
        Filter(
            serializers.ListField(),
            multi="unknown",  # type: ignore[arg-type]
        )


def test_filter_with_bad_list_field_raises_warning() -> None:
    with pytest.warns(
        UserWarning,
        match=r"Use of `rest_framework.fields.ListField` is not recommended"
        r" for Filter, use `rest_filters.fields.ListField` instead for"
        r" predictable behavior",
    ):
        Filter(serializers.ListField())


def test_filter_child_binding() -> None:
    child1, child2 = Filter(param="child1"), Filter(param="child2")
    parent = Filter(children=[child1, child2])

    assert child1.parent == parent
    assert child2.parent == parent


def test_filter_child_rebinding_to_another_parent_is_rejected() -> None:
    child = Filter(lookup="gte")
    parent = Filter(children=[child])

    with pytest.raises(
        ValueError,
        match="This child filter already belongs to another parent",
    ):
        Filter(children=[child])

    assert child.parent is parent
    assert parent.children == [child]


def test_filter_child_binding_to_same_parent_is_allowed() -> None:
    child = Filter(lookup="gte")
    parent = Filter(children=[child])

    child.bind(parent)

    assert child.parent is parent


def test_filter_child_binding_param_required_for_child() -> None:
    with pytest.raises(
        ValueError,
        match="Either 'param' or 'lookup' parameter needs to"
        " be specified for child filters",
    ):
        Filter(children=[Filter()])


def test_filter_child_binding_param_defaults_to_lookup() -> None:
    f = Filter(
        param="age",
        children=[Filter(lookup="gte")],
    )
    assert f.children[0]._param == "gte"
    assert f.children[0].get_param_name() == "age.gte"


def test_filter_name_resolution_failure_message() -> None:
    f = Filter()
    with pytest.raises(
        AttributeError,
        match="Could not resolve name of this Filter instance,"
        r" did you instantiate it outside a FilterSet body\?",
    ):
        f.get_param_name()


def test_filter_filterset_resolution_failure_message() -> None:
    f = Filter()
    with pytest.raises(
        AttributeError,
        match="Could not resolve FilterSet for this Filter",
    ):
        f.get_filterset()


def test_namespace_filter_without_children() -> None:
    with pytest.raises(
        ValueError, match="Namespace filters are required to have child filters"
    ):
        Filter(namespace=True)


def test_filter_repr() -> None:
    f = Filter(serializers.DateTimeField(), param="created")
    assert (
        repr(f) == "Filter("
        "_field=None,"
        " lookup='',"
        " template=None,"
        " _group=None,"
        " aliases=None,"
        " negate=False,"
        " _noop=None,"
        " _blank=None,"
        " _multi=None,"
        " method=None,"
        " _param='created',"
        " _serializer=DateTimeField(),"
        " _filterset=None,"
        " namespace=False,"
        " children=[]"
        ")"
    )


def test_filter_compilation_sets_name() -> None:
    class SomeFilterSet(FilterSet[Any]):
        created = Filter(serializers.DateTimeField())

    assert SomeFilterSet._compiled_fields["created"].name == "created"
    assert not hasattr(SomeFilterSet.created, "name")


def test_filter_get_group() -> None:
    class SomeFilterSet(FilterSet[Any]):
        pass

    filterset = get_filterset_instance(SomeFilterSet)

    f1, f2 = (
        Filter(),
        Filter(group="f2_group"),
    )
    f3_child_1, f3_child_2, f4_child_1 = (
        Filter(param="a"),
        Filter(param="b", group="f3_child_2"),
        Filter(param="c"),
    )

    f3 = Filter(children=[f3_child_1, f3_child_2], group="f3_parent_group")
    f4 = Filter(children=[f4_child_1])

    for f in (f1, f2, f3, f4, f3_child_1, f3_child_2, f4_child_1):
        f._filterset = filterset

    assert f1.get_group() == "chain"
    assert f2.get_group() == "f2_group"

    assert f3.get_group() == "f3_parent_group"
    assert f3_child_1.get_group() == "f3_parent_group"
    assert f3_child_2.get_group() == "f3_child_2"

    assert f4.get_group() == "chain"
    assert f4_child_1.get_group() == "chain"


def test_filter_get_db_field() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter()
        f2 = Filter(field="created")
        f3 = Filter(field=Length("username"))

        modified = Filter(
            children=[
                Filter(param="gte"),
            ]
        )
        first_name = Filter(
            children=[
                Filter(param="ln", field="last_name"),
                Filter(param="len", field=Length("last_name")),
            ]
        )
        last_name = Filter(
            field=Length("last_name"),
            children=[
                Filter(param="xy"),
            ],
        )

    fields = SomeFilterSet._compiled_fields

    assert fields["username"].get_db_field() == "username"
    assert fields["f2"].get_db_field() == "created"
    assert fields["f3"].get_db_field() == Length("username")

    assert fields["modified"].get_db_field() == "modified"
    assert fields["modified"].children[0].get_db_field() == "modified"

    assert fields["first_name"].get_db_field() == "first_name"
    assert fields["first_name"].children[0].get_db_field() == "last_name"
    assert fields["first_name"].children[1].get_db_field() == Length("last_name")

    assert fields["last_name"].get_db_field() == Length("last_name")
    assert fields["last_name"].children[0].get_db_field() == Length("last_name")


def test_filter_get_param_name() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter()
        email = Filter(param="mail")
        modified = Filter(
            param="updated",
            children=[
                Filter(param="gte"),
            ],
        )
        created = Filter(
            children=[
                Filter(param="gte"),
                Filter(param="lte"),
                Filter(
                    param="year",
                    children=[
                        Filter(param="gte"),
                        Filter(param="lte"),
                    ],
                ),
            ]
        )

    f = SomeFilterSet._compiled_fields

    assert f["username"].get_param_name() == "username"
    assert f["email"].get_param_name() == "mail"

    assert f["modified"].get_param_name() == "updated"
    assert f["modified"].children[0].get_param_name() == "updated.gte"

    assert f["created"].get_param_name() == "created"
    assert f["created"].children[0].get_param_name() == "created.gte"
    assert f["created"].children[1].get_param_name() == "created.lte"

    assert f["created"].children[2].get_param_name() == "created.year"
    assert f["created"].children[2].children[0].get_param_name() == "created.year.gte"
    assert f["created"].children[2].children[1].get_param_name() == "created.year.lte"


def test_filter_get_query_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter()
        name = Filter(param="first_name")
        surname = Filter(param="last_name")
        created = Filter(
            children=[
                Filter(param="gte"),
            ],
        )

    f = SomeFilterSet._compiled_fields
    query_dict = QueryDict("username=kate&created.gte=2024-01-01&first_name=Katie")

    assert f["username"].get_query_value(query_dict) == ["kate"]

    assert f["name"].get_query_value(query_dict) == ["Katie"]
    assert f["surname"].get_query_value(query_dict) == []

    assert f["created"].get_query_value(query_dict) == []
    assert f["created"].children[0].get_query_value(query_dict) == ["2024-01-01"]


def test_filter_get_serializer() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter()
        modified = Filter(serializers.DateTimeField())
        created = Filter(
            serializers.DateTimeField(),
            children=[
                Filter(param="gte"),
                Filter(serializers.DateField(), param="year"),
            ],
        )

    f = SomeFilterSet._compiled_fields

    with pytest.raises(
        ValueError, match="Serializer could not be resolved for 'username'"
    ):
        f["username"].get_serializer()

    assert isinstance(f["modified"].get_serializer(), serializers.DateTimeField)
    assert isinstance(f["created"].get_serializer(), serializers.DateTimeField)
    assert isinstance(
        f["created"].children[0].get_serializer(), serializers.DateTimeField
    )
    assert isinstance(f["created"].children[1].get_serializer(), serializers.DateField)


def test_filter_child_inherits_parent_serializer_override() -> None:
    class CustomFilter(Filter):
        def get_serializer(self) -> AnyField:
            return serializers.IntegerField(min_value=5)

    class SomeFilterSet(FilterSet[Any]):
        username = CustomFilter(
            serializers.CharField(),
            children=[
                Filter(lookup="gte"),
            ],
        )

        class Meta:
            noop = True

    instance = get_filterset_instance(SomeFilterSet, query="username.gte=6")
    assert instance.get_groups()[1] == {"username.gte": 6}


def test_filter_deep_child_inherits_parent_override_without_declaration() -> None:
    class CustomFilter(Filter):
        def get_serializer(self) -> AnyField:
            return serializers.IntegerField(min_value=5)

    class SomeFilterSet(FilterSet[Any]):
        username = CustomFilter(
            children=[
                Filter(
                    param="length",
                    children=[
                        Filter(
                            param="range",
                            children=[Filter(lookup="gte")],
                        ),
                    ],
                ),
            ],
        )

        class Meta:
            noop = True

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username.length.range.gte=6",
    )
    assert instance.get_groups()[1] == {"username.length.range.gte": 6}


def test_filter_deep_child_uses_parent_override_validation() -> None:
    class CustomFilter(Filter):
        def get_serializer(self) -> AnyField:
            return serializers.IntegerField(min_value=5)

    class SomeFilterSet(FilterSet[Any]):
        username = CustomFilter(
            serializers.CharField(),
            children=[
                Filter(
                    param="length",
                    children=[
                        Filter(
                            param="range",
                            children=[Filter(lookup="gte")],
                        ),
                    ],
                ),
            ],
        )

        class Meta:
            noop = True

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username.length.range.gte=4",
    )
    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()
    assert ctx.value.detail == {
        "username.length.range.gte": [
            ErrorDetail(
                string="Ensure this value is greater than or equal to 5.",
                code="min_value",
            ),
        ],
    }


def test_filter_root_serializer_override_does_not_modify_shared_serializer() -> None:
    supplied = serializers.IntegerField(default=5)

    class CustomFilter(Filter):
        def get_serializer(self) -> AnyField:
            return supplied

    class SomeFilterSet(FilterSet[Any]):
        username = CustomFilter()

        class Meta:
            noop = True

        def get_default(self, param: str, default: Any) -> Any:
            return 10

    instance = get_filterset_instance(SomeFilterSet)
    assert instance.get_groups()[1] == {"username": 10}
    assert supplied.default == 5
    assert supplied.required is False
    assert supplied.context == {}


def test_filter_resolve_deeply_inherited_serializer_copies_once() -> None:
    copies = []

    class CountingCharField(serializers.CharField):
        def __deepcopy__(self, memo: dict[int, Any]) -> "CountingCharField":
            copies.append(self)
            return super().__deepcopy__(memo)

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            CountingCharField(),
            children=[
                Filter(
                    lookup="first",
                    children=[
                        Filter(
                            lookup="second",
                            children=[
                                Filter(lookup="third"),
                            ],
                        ),
                    ],
                ),
            ],
        )

    instance = get_filterset_instance(SomeFilterSet)
    root = instance.get_fields()["username"]
    root._filterset = instance
    copies.clear()

    parent_serializer = root.resolve_serializer()
    assert copies == []

    resolved = [parent_serializer]
    for child in root.get_all_children():
        copies.clear()
        serializer = child.resolve_serializer()
        assert len(copies) == 1
        assert all(serializer is not previous for previous in resolved)
        resolved.append(serializer)

    resolved[-1].required = True
    assert all(serializer.required is False for serializer in resolved[:-1])


def test_filter_get_filterset() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(
            serializers.DateTimeField(),
            children=[
                Filter(param="gte"),
                Filter(
                    param="year",
                    children=[
                        Filter(param="gte"),
                    ],
                ),
            ],
        )

    filterset = get_filterset_instance(SomeFilterSet)

    fields = filterset.get_fields()
    for f in fields.values():
        # simulate what `get_groups` does
        f._filterset = filterset
    assert fields["username"].get_filterset() == filterset
    assert fields["created"].get_filterset() == filterset
    assert fields["created"].children[0].get_filterset() == filterset

    with pytest.raises(AttributeError, match="Could not resolve FilterSet"):
        SomeFilterSet._compiled_fields["username"].get_filterset()

    with pytest.raises(AttributeError, match="Could not resolve FilterSet"):
        filterset._compiled_fields["username"].get_filterset()


def test_filter_resolve_serializer() -> None:
    f = serializers.CharField()

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            f,
            children=[
                Filter(param="icontains", lookup="icontains"),
            ],
        )

    filterset = get_filterset_instance(SomeFilterSet)
    fields = filterset.get_fields()

    field = fields["username"]
    field._filterset = filterset
    resolved1 = field.resolve_serializer()
    resolved2 = field.children[0].resolve_serializer()

    assert resolved1 is not resolved2
    assert not f.context
    assert not SomeFilterSet._compiled_fields["username"]._serializer.context  # type: ignore[union-attr]

    assert resolved1 is field._serializer
    assert resolved2 is not field._serializer

    for resolved in [resolved1, resolved2]:
        assert resolved is not f
        assert isinstance(resolved, serializers.CharField)
        assert resolved.required is False
        assert resolved.context


def test_filter_resolve_serializer_dynamic_only() -> None:
    f = serializers.CharField()

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            children=[
                Filter(param="icontains", lookup="icontains"),
            ],
        )

        def get_serializer(self, param: str, serializer: AnyField | None) -> AnyField:
            if param in ("username", "username.icontains"):
                return f
            return super().get_serializer(param, serializer)  # pragma: no cover

    filterset = get_filterset_instance(SomeFilterSet)
    fields = filterset.get_fields()

    field = fields["username"]
    field._filterset = filterset
    resolved1 = field.resolve_serializer()
    resolved2 = field.children[0].resolve_serializer()

    assert not f.context

    for resolved in [resolved1, resolved2]:
        assert resolved != f
        assert isinstance(resolved, serializers.CharField)
        assert resolved.required is False
        assert resolved.context


def test_filter_resolve_serializer_dynamic_failed_to_resolve() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter()

    filterset = get_filterset_instance(SomeFilterSet)
    with pytest.raises(
        ValueError,
        match="Serializer could not be resolved for 'username'",
    ):
        filterset.filter_queryset()


def test_filter_resolve_serializer_dynamic_failed_to_resolve_case_nested() -> None:
    # Don't support serializer inheritance when serializers are resolved
    # using methods.
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(children=[Filter(param="icontains", lookup="icontains")])

        def get_serializer(self, param: str, serializer: AnyField | None) -> AnyField:
            if param == "username":
                return serializers.CharField()
            return super().get_serializer(param, serializer)

    filterset = get_filterset_instance(SomeFilterSet)
    with pytest.raises(
        ValueError,
        match=r"Serializer could not be resolved for 'username\.icontains'",
    ):
        filterset.filter_queryset()


def test_filter_resolve_serializer_replacement() -> None:
    current, replacement = (
        serializers.CharField(),
        serializers.CharField(min_length=27),
    )

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(current)

        def get_serializer(self, param: str, serializer: AnyField | None) -> AnyField:
            return replacement

    filterset = get_filterset_instance(SomeFilterSet)
    field = filterset.get_fields()["username"]
    field._filterset = filterset

    resolved = field.resolve_serializer()

    assert resolved != replacement
    assert resolved != current
    assert resolved != field._serializer

    assert isinstance(resolved, serializers.CharField)
    assert resolved.min_length == 27
    assert resolved.context

    assert not current.context
    assert not replacement.context
    assert not SomeFilterSet._compiled_fields["username"]._serializer.context  # type: ignore[union-attr]


def test_filter_resolve_serializer_replacement_attr_changed() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

        def get_serializer(self, param: str, serializer: AnyField | None) -> AnyField:
            serializer = cast("serializers.CharField", serializer)
            serializer.max_length = 25
            return serializer

    filterset = get_filterset_instance(SomeFilterSet)

    field = filterset.get_fields()["username"]
    field._filterset = filterset
    resolved = cast("serializers.CharField", field.resolve_serializer())

    assert resolved == field._serializer
    assert resolved.context
    assert resolved.max_length == 25

    assert not SomeFilterSet._compiled_fields["username"]._serializer.context  # type: ignore[union-attr]


def test_filter_resolve_serializer_replacement_failed_to_resolve() -> None:
    f = serializers.CharField()

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(f)

        def get_serializer(self, param: str, serializer: AnyField | None) -> AnyField:
            return None  # type: ignore[return-value]

    filterset = get_filterset_instance(SomeFilterSet)

    with pytest.raises(
        ValueError,
        match="Serializer could not be resolved for 'username'",
    ):
        filterset.filter_queryset()
    assert not f.context
    assert not SomeFilterSet._compiled_fields["username"]._serializer.context  # type: ignore[union-attr]


def test_filter_run_validation() -> None:
    class SomeFilterSet(FilterSet[Any]):
        name = Filter(serializers.CharField())
        username = Filter(serializers.CharField())

        def run_validation(self, value: str, serializer: AnyField, param: str) -> Any:  # type: ignore[override]
            if param == "name":
                return super().run_validation(value, serializer, param)
            return value.replace("1", "X")

    filterset = get_filterset_instance(SomeFilterSet, query="name=a&username=b")

    fields = filterset.get_fields()

    name = fields["name"]
    username = fields["username"]
    name._filterset = username._filterset = filterset
    assert name.run_validation("abc123", serializers.CharField()) == "abc123"
    assert username.run_validation("abc123", serializers.CharField()) == "abcX23"


def test_filter_parse_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    filterset = get_filterset_instance(SomeFilterSet)

    username = filterset.get_fields()["username"]
    username._filterset = filterset
    username.run_validation = MagicMock()  # type: ignore[method-assign]

    username.parse_value(["123"])
    username.parse_value([])
    username.parse_value([""])

    username.run_validation.assert_has_calls(
        calls=[
            call("123", username._serializer),
            call(empty, username._serializer),
            call(empty, username._serializer),
        ]
    )


def test_filter_parse_value_case_blank_keep() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), blank=Blank.KEEP)

    filterset = get_filterset_instance(SomeFilterSet)

    username = filterset.get_fields()["username"]
    username._filterset = filterset
    username.run_validation = MagicMock()  # type: ignore[method-assign]

    username.parse_value([""])
    username.run_validation.assert_called_once_with("", username._serializer)


def test_filter_parse_value_preserves_raw_input() -> None:
    class SomeFilterSet(FilterSet[Any]):
        created = Filter(serializers.DateTimeField())

    filterset = get_filterset_instance(SomeFilterSet)

    created = filterset.get_fields()["created"]
    created._filterset = filterset
    created.run_validation = MagicMock()  # type: ignore[method-assign]

    created.parse_value([" 2017-01-01\t\n\r"])
    created.run_validation.assert_called_once_with(
        " 2017-01-01\t\n\r",
        created._serializer,
    )

    created.run_validation.reset_mock()
    created.parse_value(["2017-01-01\0"])
    created.run_validation.assert_called_once_with(
        "2017-01-01\0",
        created._serializer,
    )


def test_filter_preserves_whitespace_for_untrimmed_strings() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(trim_whitespace=False))

    filterset = get_filterset_instance(
        SomeFilterSet,
        query="username=%20hello%20",
    )
    groups, _ = filterset.get_groups()
    assert groups["chain"]["username"].value == " hello "


def test_filter_preserves_whitespace_in_choices() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.ChoiceField(choices=[" hello "]))

    filterset = get_filterset_instance(
        SomeFilterSet,
        query="username=%20hello%20",
    )
    groups, _ = filterset.get_groups()
    assert groups["chain"]["username"].value == " hello "


def test_filter_preserves_whitespace_in_csv_items() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            CSVField(child=serializers.CharField(trim_whitespace=False)),
            lookup="in",
        )

    filterset = get_filterset_instance(
        SomeFilterSet,
        query="username=%20alice%20,%20bob%20",
    )
    groups, _ = filterset.get_groups()
    assert groups["chain"]["username"].value == [" alice ", " bob "]


def test_multi_allow_preserves_whitespace_in_items() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            ListField(child=serializers.CharField(trim_whitespace=False)),
            multi=Multi.ALLOW,
            lookup="in",
        )

    filterset = get_filterset_instance(
        SomeFilterSet,
        query="username=%20alice%20&username=%20%20",
    )
    groups, _ = filterset.get_groups()
    assert groups["chain"]["username"].value == [" alice ", "  "]


def test_filter_parse_value_case_bad_multi() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

        class Meta:
            multi = "uknown"

    filterset = get_filterset_instance(SomeFilterSet)

    username = filterset.get_fields()["username"]
    username._filterset = filterset

    with pytest.raises(
        ValueError,
        match="'uknown' is not a valid multi choice",
    ):
        username.parse_value(["123"])


def test_multi_disallow() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), multi=Multi.DISALLOW)

    instance = get_filterset_instance(
        SomeFilterSet, query="username=alice&username=bob"
    )
    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()
    assert ctx.value.detail == {
        "username": [
            ErrorDetail(
                string="This query parameter does not allow"
                " specifying multiple values.",
                code="invalid",
            )
        ]
    }


def test_multi_disallow_single_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), multi=Multi.DISALLOW)

    instance = get_filterset_instance(SomeFilterSet, query="username=alice")
    groups, _ = instance.get_groups()
    assert groups == {
        "chain": {
            "username": Entry(
                group="chain",
                value="alice",
                expression=Q(username="alice"),
            )
        }
    }


def test_multi_disallow_no_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), multi=Multi.DISALLOW)

    instance = get_filterset_instance(SomeFilterSet, query="")
    groups, _ = instance.get_groups()
    assert groups == {}


def test_multi_first() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), multi=Multi.FIRST)

    instance = get_filterset_instance(
        SomeFilterSet, query="username=alice&username=bob"
    )
    groups, _ = instance.get_groups()
    assert groups == {
        "chain": {
            "username": Entry(
                group="chain",
                value="alice",
                expression=Q(username="alice"),
            )
        }
    }


def test_multi_last() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), multi=Multi.LAST)

    instance = get_filterset_instance(
        SomeFilterSet, query="username=alice&username=bob"
    )
    groups, _ = instance.get_groups()
    assert groups == {
        "chain": {
            "username": Entry(
                group="chain",
                value="bob",
                expression=Q(username="bob"),
            )
        }
    }


def test_multi_allow_single_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            ListField(child=serializers.CharField()),
            multi=Multi.ALLOW,
            lookup="in",
        )

    instance = get_filterset_instance(SomeFilterSet, query="username=alice")
    groups, _ = instance.get_groups()
    assert groups == {
        "chain": {
            "username": Entry(
                group="chain",
                value=["alice"],
                expression=Q(username__in=["alice"]),
            )
        }
    }


def test_multi_allow_multiple_values() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            ListField(child=serializers.CharField()),
            multi=Multi.ALLOW,
            lookup="in",
        )

    instance = get_filterset_instance(
        SomeFilterSet, query="username=alice&username=bob"
    )
    groups, _ = instance.get_groups()
    assert groups == {
        "chain": {
            "username": Entry(
                group="chain",
                value=["alice", "bob"],
                expression=Q(username__in=["alice", "bob"]),
            )
        }
    }


def test_multi_allow_no_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            ListField(child=serializers.CharField()),
            multi=Multi.ALLOW,
            lookup="in",
        )

    instance = get_filterset_instance(SomeFilterSet, query="")
    groups, _ = instance.get_groups()
    assert groups == {}


def test_multi_allow_blank_keep() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            ListField(child=serializers.CharField(allow_blank=True)),
            multi=Multi.ALLOW,
            lookup="in",
            blank=Blank.KEEP,
        )

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=alice&username=&username=bob",
    )
    groups, _ = instance.get_groups()
    assert groups == {
        "chain": {
            "username": Entry(
                group="chain",
                value=["alice", "", "bob"],
                expression=Q(username__in=["alice", "", "bob"]),
            )
        }
    }


def test_multi_allow_blank_omit_child_not_required() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            ListField(
                child=serializers.CharField(
                    allow_blank=True,
                    required=False,
                )
            ),
            multi=Multi.ALLOW,
            lookup="in",
            blank=Blank.OMIT,
        )

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=alice&username=&username=bob",
    )
    groups, _ = instance.get_groups()
    assert groups == {
        "chain": {
            "username": Entry(
                group="chain",
                value=["alice", "bob"],
                expression=Q(username__in=["alice", "bob"]),
            )
        }
    }


def test_multi_allow_blank_omit_child_not_required_filter_required() -> None:
    # child filters allowed to be empty, but if all of them are empty, the
    # entire field is empty, which is not allowed when required=True
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            ListField(
                child=serializers.CharField(
                    allow_blank=True,
                    required=False,
                ),
            ),
            multi=Multi.ALLOW,
            lookup="in",
            blank=Blank.OMIT,
            required=True,
        )

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=&username=",
    )
    with pytest.raises(serializers.ValidationError, match=r"This field is required\."):
        instance.get_groups()


def test_multi_allow_correct_error_index_when_skipped() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            ListField(
                child=serializers.CharField(
                    allow_blank=True,
                    required=False,
                    min_length=3,
                ),
            ),
            multi=Multi.ALLOW,
            lookup="in",
            blank=Blank.OMIT,
            required=True,
        )

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello&username=&username=w",
    )
    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()
    assert ctx.value.detail == {  # type: ignore[comparison-overlap]
        "username": {
            2: [  # not 1
                ErrorDetail(
                    string="Ensure this field has at least 3 characters.",
                    code="min_length",
                )
            ]
        }
    }


def test_entry_repr() -> None:
    entry = Entry(
        group="chain",
        aliases={
            "field": F("field"),
        },
        value=1.25,
        expression=Q(field=1.25),
    )
    assert (
        repr(entry) == "Entry(group='chain',"
        " aliases={'field': F(field)},"
        " value=1.25,"
        " expression=<Q: (AND: ('field', 1.25))>)"
    )


@pytest.mark.parametrize(
    "f,entry",
    (
        # Field names
        (
            Filter(field="username"),
            Entry(group="chain", value="value", expression=Q(username="value")),
        ),
        (
            Filter(field="username", lookup="icontains"),
            Entry(
                group="chain",
                value="value",
                expression=Q(username__icontains="value"),
            ),
        ),
        (
            Filter(field="username", lookup="icontains", negate=True),
            Entry(
                group="chain",
                value="value",
                expression=~Q(username__icontains="value"),
            ),
        ),
        # Templates
        (
            Filter(template=Q("username") | Q("email")),
            Entry(
                group="chain",
                value="value",
                expression=Q(username="value") | Q(email="value"),
            ),
        ),
        (
            Filter(template=Q("username__icontains") | Q("email__contains")),
            Entry(
                group="chain",
                value="value",
                expression=Q(username__icontains="value") | Q(email__contains="value"),
            ),
        ),
        (
            Filter(template=Q("username") | Q("email"), negate=True),
            Entry(
                group="chain",
                value="value",
                expression=~(Q(username="value") | Q(email="value")),
            ),
        ),
        # Field expressions
        (
            Filter(param="username", field=Length("username")),
            Entry(
                group="chain",
                value="value",
                expression=Q(_default_alias_username="value"),
                aliases={
                    "_default_alias_username": Length("username"),
                },
            ),
        ),
        (
            Filter(param="username", field=Length("username"), lookup="gte"),
            Entry(
                group="chain",
                value="value",
                expression=Q(_default_alias_username__gte="value"),
                aliases={
                    "_default_alias_username": Length("username"),
                },
            ),
        ),
        (
            Filter(
                param="username_length",
                field=Length("username"),
                lookup="gte",
                negate=True,
            ),
            Entry(
                group="chain",
                value="value",
                expression=~Q(_default_alias_username_length__gte="value"),
                aliases={
                    "_default_alias_username_length": Length("username"),
                },
            ),
        ),
        (
            Filter(param="username", field=F("username")),
            Entry(
                group="chain",
                value="value",
                expression=Q(_default_alias_username="value"),
                aliases={
                    "_default_alias_username": F("username"),
                },
            ),
        ),
        (
            Filter(
                param="username",
                field=F("username"),
                aliases={"my_email_alias": F("email")},
            ),
            Entry(
                group="chain",
                value="value",
                expression=Q(_default_alias_username="value"),
                aliases={
                    "_default_alias_username": F("username"),
                    "my_email_alias": F("email"),
                },
            ),
        ),
    ),
)
def test_filter_resolve_entry_attrs(f: Filter, entry: Entry) -> None:
    class SomeFilterSet(FilterSet[Any]):
        pass

    filterset = get_filterset_instance(SomeFilterSet)
    f.name = "username"
    f._filterset = filterset
    assert f.resolve_entry_attrs("value") == entry


def test_filter_resolve_entry_attrs_reserved_q_argument_names() -> None:
    class SomeFilterSet(FilterSet[Any]):
        pass

    filterset = get_filterset_instance(SomeFilterSet)
    connector = Filter(field="_connector", param="_connector", group="chain")
    connector._filterset = filterset
    entry = connector.resolve_entry_attrs("AND")
    assert entry.expression == Q(("_connector", "AND"))

    negated = Filter(
        field="_negated",
        param="_negated",
        group="chain",
        negate=True,
    )
    negated._filterset = filterset
    entry = negated.resolve_entry_attrs(False)
    assert entry.expression == ~Q(("_negated", False))


def test_filter_resolve_entry_attrs_child() -> None:
    class SomeFilterSet(FilterSet[Any]):
        pass

    f = Filter(
        group="user_group",
        param="username",
        children=[
            Filter(
                param="min_length",
                field=Length("username"),
                lookup="gte",
            )
        ],
    )
    f._filterset = get_filterset_instance(SomeFilterSet)
    entry = f.children[0].resolve_entry_attrs(5)
    assert entry == Entry(
        group="user_group",
        value=5,
        aliases={"_default_alias_username.min_length": Length("username")},
        expression=Q(**{"_default_alias_username.min_length__gte": 5}),
    )


def test_filter_child_inherits_aliases_for_its_field() -> None:
    class SomeFilterSet(FilterSet[Any]):
        length = Filter(
            serializers.IntegerField(),
            namespace=True,
            field="username_length",
            aliases={"username_length": Length("username")},
            children=[
                Filter(lookup="gte"),
            ],
        )

    filterset = get_filterset_instance(
        SomeFilterSet,
        query="length.gte=5",
    )
    queryset = filterset.filter_queryset()
    assert str(queryset.query).split(" WHERE ", 1)[1] == (
        'LENGTH("testapp_user"."username") >= 5'
    )


def test_filter_aliases_include_all_ancestors() -> None:
    class SomeFilterSet(FilterSet[Any]):
        length = Filter(
            serializers.IntegerField(),
            aliases={"parent_only": Value(1)},
            namespace=True,
            children=[
                Filter(
                    param="username",
                    namespace=True,
                    aliases={"middle_only": Value(2)},
                    children=[
                        Filter(
                            lookup="gte",
                            aliases={"child_only": Value(3)},
                        ),
                    ],
                ),
            ],
        )

    filterset = get_filterset_instance(
        SomeFilterSet,
        query="length.username.gte=5",
    )
    groups, _ = filterset.get_groups()
    entry = groups["chain"]["length.username.gte"]
    assert entry.aliases == {
        "parent_only": Value(1),
        "middle_only": Value(2),
        "child_only": Value(3),
    }


def test_filter_child_alias_overrides_parent_alias() -> None:
    class SomeFilterSet(FilterSet[Any]):
        length = Filter(
            serializers.IntegerField(),
            aliases={"shared": Value("parent")},
            namespace=True,
            children=[
                Filter(
                    lookup="gte",
                    aliases={"shared": Value("child")},
                ),
            ],
        )

    filterset = get_filterset_instance(SomeFilterSet, query="length.gte=5")
    groups, _ = filterset.get_groups()
    entry = groups["chain"]["length.gte"]
    assert entry.aliases == {"shared": Value("child")}


def test_filter_parent_alias_hook_changes_do_not_leak_to_children() -> None:
    class SomeFilterSet(FilterSet[Any]):
        length = Filter(
            serializers.IntegerField(),
            field="name_length",
            aliases={"name_length": Length("username")},
            children=[
                Filter(lookup="gte"),
            ],
        )

        def get_aliases(self, param: str, aliases: dict[str, Any]) -> dict[str, Any]:
            if param == "length":
                aliases["name_length"] = Length("first_name")
            return aliases

    filterset = get_filterset_instance(
        SomeFilterSet,
        query="length=5&length.gte=3",
    )
    queryset = filterset.filter_queryset()
    assert str(queryset.query).split(" WHERE ", 1)[1] == (
        '(LENGTH("testapp_user"."first_name") = 5 '
        'AND LENGTH("testapp_user"."username") >= 3)'
    )


def test_filter_expression_alias_is_added_after_alias_hook() -> None:
    class SomeFilterSet(FilterSet[Any]):
        length = Filter(serializers.IntegerField(), field=Length("username"))

        def get_aliases(self, param: str, aliases: dict[str, Any]) -> dict[str, Any]:
            assert aliases == {}
            return {"hook_only": Value(1)}

    filterset = get_filterset_instance(SomeFilterSet, query="length=5")
    groups, _ = filterset.get_groups()
    entry = groups["chain"]["length"]
    assert entry.aliases == {
        "hook_only": Value(1),
        "_default_alias_length": Length("username"),
    }


def test_filter_alias_hook_skips_missing_and_noop_filters() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        role = Filter(serializers.CharField())
        ordering = Filter(serializers.CharField(), noop=True)

    filterset = get_filterset_instance(
        SomeFilterSet,
        query="username=alice&ordering=username",
    )
    filterset.get_aliases = MagicMock(return_value={})  # type: ignore[method-assign]
    filterset.get_groups()
    filterset.get_aliases.assert_called_once_with("username", {})


def test_filter_alias_hook_runs_only_for_current_parameter() -> None:
    class SomeFilterSet(FilterSet[Any]):
        length = Filter(
            serializers.IntegerField(),
            aliases={"username_length": Length("username")},
            children=[
                Filter(lookup="gte"),
            ],
        )

        def get_aliases(self, param: str, aliases: dict[str, Any]) -> dict[str, Any]:
            aliases["minimum_length"] = Value(3)
            return aliases

    filterset = get_filterset_instance(SomeFilterSet)
    filterset.get_aliases = MagicMock(side_effect=filterset.get_aliases)  # type: ignore[method-assign]
    parent = filterset.get_fields()["length"]
    child = parent.children[0]
    parent._filterset = filterset

    expected = {
        "username_length": Length("username"),
        "minimum_length": Value(3),
    }
    assert child._get_aliases() == expected
    filterset.get_aliases.assert_called_once_with("length.gte", expected)
    assert parent._get_aliases() == expected
    assert filterset.get_aliases.call_args_list == [
        call("length.gte", expected),
        call("length", expected),
    ]


def test_filter_aliases_can_be_replaced_or_discarded() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            aliases={"original": Value(1)},
        )
        role = Filter(
            serializers.CharField(),
            aliases={"original": Value(2)},
        )

        def get_aliases(self, param: str, aliases: dict[str, Any]) -> dict[str, Any]:
            if param == "username":
                return {"replacement": Value(3)}
            return {}

    filterset = get_filterset_instance(
        SomeFilterSet,
        query="username=alice&role=admin",
    )
    groups, _ = filterset.get_groups()
    username_entry = groups["chain"]["username"]
    role_entry = groups["chain"]["role"]

    assert username_entry.aliases == {"replacement": Value(3)}
    assert role_entry.aliases is None


def test_filter_method_uses_declared_and_filterset_aliases() -> None:
    class SomeFilterSet(FilterSet[Any]):
        length = Filter(
            serializers.IntegerField(),
            aliases={"username_length": Length("username")},
            method="filter_length",
        )

        def get_aliases(self, param: str, aliases: dict[str, Any]) -> dict[str, Any]:
            aliases["minimum_length"] = Value(3)
            return aliases

        def filter_length(self, param: str, value: int) -> Q:
            return Q(username_length__gte=F("minimum_length") + value)

    filterset = get_filterset_instance(SomeFilterSet, query="length=5")
    queryset = filterset.filter_queryset()

    assert str(queryset.query).split(" WHERE ", 1)[1] == (
        'LENGTH("testapp_user"."username") >= (3 + 5)'
    )


def test_filter_method_entry_is_returned_unchanged() -> None:
    result = Entry(
        group="chain",
        aliases={"username_length": Length("username")},
        value=5,
        expression=Q(username_length__gte=5),
    )

    class SomeFilterSet(FilterSet[Any]):
        length = Filter(serializers.IntegerField(), method="filter_length")

        def get_aliases(self, param: str, aliases: dict[str, Any]) -> dict[str, Any]:
            return {}

        def filter_length(self, param: str, value: int) -> Entry:
            return result

    filterset = get_filterset_instance(SomeFilterSet, query="length=5")
    groups, _ = filterset.get_groups()
    entry = groups["chain"]["length"]

    assert entry is result
    assert result.aliases == {"username_length": Length("username")}


def test_filter_resolve_entry() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            children=[
                Filter(param="icontains", lookup="icontains"),
            ],
        )

    filterset = get_filterset_instance(SomeFilterSet)

    username = filterset.get_fields()["username"]
    username._filterset = filterset
    username.resolve_entry_attrs = MagicMock(side_effect=username.resolve_entry_attrs)  # type: ignore[method-assign]

    entry = username.resolve_entry(QueryDict("username=hello"))
    username.resolve_entry_attrs.assert_called_once_with("hello")

    assert entry == Entry(group="chain", value="hello", expression=Q(username="hello"))


def test_filter_resolve_entry_case_method() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            children=[
                Filter(
                    param="icontains",
                    method="get_username_icontains",
                ),
            ],
            method="get_username",
        )
        created = Filter(serializers.DateField(), method="get_created")

        def get_username(self, param: str, value: str) -> Q:
            return Q(username=value)

        def get_username_icontains(self, param: str, value: str) -> Q:
            return Q(username__icontains=value)

        def get_created(self, param: str, value: datetime.date) -> Entry:
            return Entry(
                group="my-group",
                aliases={"dummy": F("created")},
                value=value,
                expression=Q(dummy__gte=value),
            )

    filterset = get_filterset_instance(SomeFilterSet)
    query = QueryDict("username=hello&username.icontains=heyo&created=2025-01-01")

    fields = filterset.get_fields()
    username, created = fields["username"], fields["created"]
    username._filterset = created._filterset = filterset
    username.resolve_entry_attrs = MagicMock(side_effect=username.resolve_entry_attrs)  # type: ignore[method-assign]

    username_entry = username.resolve_entry(query)
    username.resolve_entry_attrs.assert_not_called()
    assert username_entry == Entry(
        group="chain", value="hello", expression=Q(username="hello")
    )

    username_contains_entry = username.children[0].resolve_entry(query)
    assert username_contains_entry == Entry(
        group="chain", value="heyo", expression=Q(username__icontains="heyo")
    )

    created_entry = created.resolve_entry(query)
    assert created_entry == Entry(
        group="my-group",
        aliases={"dummy": F("created")},
        value=datetime.date(2025, 1, 1),
        expression=Q(dummy__gte=datetime.date(2025, 1, 1)),
    )


def test_filter_resolve_entry_case_noop() -> None:
    class SomeFilterSet(FilterSet[Any]):
        ordering = Filter(serializers.CharField(), noop=True)

    filterset = get_filterset_instance(SomeFilterSet)

    ordering = filterset.get_fields()["ordering"]
    ordering._filterset = filterset

    entry = ordering.resolve_entry(QueryDict("ordering=id"))
    assert entry == Entry(group="chain", value="id", expression=None)


def test_filter_resolve_entry_case_noop_with_method() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), method="get_username")

        def get_username(self, param: str, value: str) -> Any:
            if value == "do_nothing":
                return notset
            return Q(username=value)

    filterset = get_filterset_instance(SomeFilterSet)

    ordering = filterset.get_fields()["username"]
    ordering._filterset = filterset

    entry = ordering.resolve_entry(QueryDict("username=jack52"))
    assert entry == Entry(
        group="chain", value="jack52", expression=Q(username="jack52")
    )

    entry2 = ordering.resolve_entry(QueryDict("username=do_nothing"))
    assert entry2 == Entry(group="chain", value="do_nothing", expression=notset)


def test_filter_resolve() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            children=[
                Filter(
                    param="icontains",
                    method="get_username_icontains",
                ),
            ],
            required=True,
        )
        created = Filter(
            serializers.DateField(),
            namespace=True,
            children=[
                Filter(param="gte", lookup="gte"),
                Filter(
                    serializers.DateField(),
                    param="date",
                    lookup="date",
                    children=[
                        Filter(param="gte", lookup="date__gte"),
                    ],
                    required=False,
                ),
            ],
            required=True,
        )

        def get_username_icontains(self, param: str, value: str) -> Q:
            return Q(username__icontains=value)

    filterset = get_filterset_instance(SomeFilterSet)

    fields = filterset.get_fields()
    username, created = fields["username"], fields["created"]
    username._filterset = created._filterset = filterset
    query = QueryDict("username.icontains=hello&created.gte=invalid")

    # Partial case
    entries, errors = username.resolve(query)
    assert entries == {
        "username.icontains": Entry(
            group="chain", value="hello", expression=Q(username__icontains="hello")
        )
    }
    assert errors == {
        "username": [ErrorDetail("This field is required.", code="required")]
    }

    # All resolved
    entries, errors = username.resolve(
        QueryDict("username=abc&username.icontains=hello")
    )
    assert entries == {
        "username": Entry(group="chain", value="abc", expression=Q(username="abc")),
        "username.icontains": Entry(
            group="chain", value="hello", expression=Q(username__icontains="hello")
        ),
    }
    assert errors == {}

    # Some resolved, some was not provided
    entries, errors = created.resolve(query)
    assert entries == {"created.date": None, "created.date.gte": None}
    assert errors == {
        "created.gte": [
            ErrorDetail(
                string="Date has wrong format."
                " Use one of these formats instead: YYYY-MM-DD.",
                code="invalid",
            )
        ]
    }

    # Deep child case
    entries, errors = created.resolve(QueryDict("created.date.gte=2024-01-01"))
    assert entries == {
        "created.date": None,
        "created.date.gte": Entry(
            group="chain",
            value=datetime.date(2024, 1, 1),
            expression=Q(created__date__gte=datetime.date(2024, 1, 1)),
        ),
    }
    assert errors == {
        "created.gte": [
            ErrorDetail(string="This field is required.", code="required"),
        ],
    }


@isolate_apps("tests.testapp")
def test_filter_primary_key_related_field_invalid_uuid() -> None:
    class Company(models.Model):
        id = models.UUIDField(primary_key=True)
        objects: ClassVar[models.Manager["Company"]] = models.Manager()

        class Meta:
            app_label = "testapp"

        def __str__(self) -> str:
            return str(self.id)

    class SomeFilterSet(FilterSet[Any]):
        company = Filter(
            serializers.PrimaryKeyRelatedField(queryset=Company.objects.all()),
            field="following_companies",
        )

    filterset = get_filterset_instance(SomeFilterSet, query="company=not-a-uuid")

    with pytest.raises(serializers.ValidationError) as ctx:
        filterset.get_groups()

    assert ctx.value.detail == {
        "company": [
            ErrorDetail(
                string="“not-a-uuid” is not a valid UUID.",
                code="invalid",
            ),
        ],
    }


def test_filter_get_all_children() -> None:
    f = Filter(
        serializers.IntegerField(),
        param="company",
        children=[
            Filter(
                serializers.CharField(),
                param="name",
                children=[
                    Filter(param="icontains"),
                    Filter(
                        param="attributes",
                        namespace=True,
                        children=[
                            Filter(serializers.IntegerField(), param="length"),
                        ],
                    ),
                ],
            ),
            Filter(serializers.DateTimeField(), param="created"),
        ],
    )
    params = [child.get_param_name() for child in f.get_all_children()]
    assert params == [
        "company.name",
        "company.name.icontains",
        "company.name.attributes",
        "company.name.attributes.length",
        "company.created",
    ]
