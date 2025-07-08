import datetime
from typing import Any, TypeVar
from unittest.mock import MagicMock, call

from django.db.models import F, Q
from django.db.models.functions import Length
from django.http import QueryDict

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.fields import empty
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

import pytest

from rest_filters import Filter, FilterSet
from rest_filters.filters import Entry
from rest_filters.utils import AnyField
from tests.testapp.views import UserView

T = TypeVar("T", bound=FilterSet[Any])


def get_filterset_instance(klass: type[T], *, query: str = "") -> T:
    factory = APIRequestFactory()
    request = Request(factory.get(f"/?{query}"))
    view = UserView(format_kwarg="format")
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


def test_filter_group_is_valid_identifier() -> None:
    with pytest.raises(ValueError, match="must be valid Python"):
        Filter(group="not-a-valid-identifier")


def test_filter_blank_invalid_choice() -> None:
    with pytest.raises(ValueError, match="blank must either be 'keep' or 'omit'"):
        Filter(blank="empty")  # type: ignore[arg-type]

    f1 = Filter(blank="keep")
    f2 = Filter(blank="omit")

    assert f1.blank == "keep"
    assert f2.blank == "omit"


def test_filter_child_binding() -> None:
    child1, child2 = Filter(param="child1"), Filter(param="child2")
    parent = Filter(children=[child1, child2])

    assert child1.parent == parent
    assert child2.parent == parent


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
    with pytest.raises(AssertionError, match="Could not resolve FilterSet"):
        f.get_param_name()


def test_namespace_filter_without_children() -> None:
    with pytest.raises(
        ValueError, match="Namespace filters are required to have child filters"
    ):
        Filter(namespace=True)


def test_filter_repr() -> None:
    f = Filter(serializers.DateTimeField(), param="created")
    assert (
        repr(f) == "Filter(_field=None, lookup='', template=None, _group=None,"
        " aliases=None, negate=False, _blank=None, method=None,"
        " _param='created', _serializer=DateTimeField(), _filterset=None,"
        " namespace=False, children=[])"
    )


def test_filter_descriptor_sets_name() -> None:
    class SomeFilterSet(FilterSet[Any]):
        created = Filter(serializers.DateTimeField())

    assert SomeFilterSet.created.name == "created"


def test_filter_get_group() -> None:
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

    assert SomeFilterSet.username.get_db_field() == "username"
    assert SomeFilterSet.f2.get_db_field() == "created"
    assert SomeFilterSet.f3.get_db_field() == Length("username")

    assert SomeFilterSet.modified.get_db_field() == "modified"
    assert SomeFilterSet.modified.children[0].get_db_field() == "modified"

    assert SomeFilterSet.first_name.get_db_field() == "first_name"
    assert SomeFilterSet.first_name.children[0].get_db_field() == "last_name"
    assert SomeFilterSet.first_name.children[1].get_db_field() == Length("last_name")

    assert SomeFilterSet.last_name.get_db_field() == Length("last_name")
    assert SomeFilterSet.last_name.children[0].get_db_field() == Length("last_name")


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

    f = SomeFilterSet

    assert f.username.get_param_name() == "username"
    assert f.email.get_param_name() == "mail"

    assert f.modified.get_param_name() == "updated"
    assert f.modified.children[0].get_param_name() == "updated.gte"

    assert f.created.get_param_name() == "created"
    assert f.created.children[0].get_param_name() == "created.gte"
    assert f.created.children[1].get_param_name() == "created.lte"

    assert f.created.children[2].get_param_name() == "created.year"
    assert f.created.children[2].children[0].get_param_name() == "created.year.gte"
    assert f.created.children[2].children[1].get_param_name() == "created.year.lte"


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

    f = SomeFilterSet
    query_dict = QueryDict("username=kate&created.gte=2024-01-01&first_name=Katie")

    assert f.username.get_query_value(query_dict) == "kate"

    assert f.name.get_query_value(query_dict) == "Katie"
    assert f.surname.get_query_value(query_dict) is empty

    assert f.created.get_query_value(query_dict) is empty
    assert f.created.children[0].get_query_value(query_dict) == "2024-01-01"


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

    f = SomeFilterSet

    with pytest.raises(
        ValueError, match="Serializer could not be resolved for 'username'"
    ):
        f.username.get_serializer()

    assert isinstance(f.modified.get_serializer(), serializers.DateTimeField)
    assert isinstance(f.created.get_serializer(), serializers.DateTimeField)
    assert isinstance(f.created.children[0].get_serializer(), serializers.DateTimeField)
    assert isinstance(f.created.children[1].get_serializer(), serializers.DateField)


def test_filter_get_filterset() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(required=False))
        created = Filter(
            serializers.DateTimeField(required=False),
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
    filterset.filter_queryset()

    fields = filterset.get_fields()
    assert fields["username"].get_filterset() == filterset
    assert fields["created"].get_filterset() == filterset
    assert fields["created"].children[0].get_filterset() == filterset

    with pytest.raises(AssertionError, match="Could not resolve FilterSet"):
        SomeFilterSet.compiled_fields["username"].get_filterset()

    with pytest.raises(AssertionError, match="Could not resolve FilterSet"):
        filterset.compiled_fields["username"].get_filterset()


def test_filter_resolve_serializer() -> None:
    f = serializers.CharField(required=False)

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            f,
            children=[
                Filter(param="icontains", lookup="icontains"),
            ],
        )

    filterset = get_filterset_instance(SomeFilterSet)
    filterset.filter_queryset()
    fields = filterset.get_fields()

    field = fields["username"]
    resolved1 = field.resolve_serializer()
    resolved2 = field.children[0].resolve_serializer()

    assert resolved1 == resolved2
    assert not f.context
    assert not SomeFilterSet.compiled_fields["username"]._serializer.context

    for resolved in [resolved1, resolved2]:
        assert resolved != f
        assert resolved == field._serializer
        assert isinstance(resolved, serializers.CharField)
        assert resolved.required is False
        assert resolved.context


def test_filter_resolve_serializer_dynamic_only() -> None:
    f = serializers.CharField(required=False)

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            children=[
                Filter(param="icontains", lookup="icontains"),
            ],
        )

        def get_serializer(
            self, param: str, serializer: AnyField | None
        ) -> AnyField | None:
            if param in ("username", "username.icontains"):
                return f
            return super().get_serializer(param, serializer)

    filterset = get_filterset_instance(SomeFilterSet)
    filterset.filter_queryset()
    fields = filterset.get_fields()

    field = fields["username"]
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
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(children=[Filter(param="icontains", lookup="icontains")])

        def get_serializer(
            self, param: str, serializer: AnyField | None
        ) -> AnyField | None:
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
        serializers.CharField(required=False),
        serializers.CharField(required=False, min_length=27),
    )

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(current)

        def get_serializer(
            self, param: str, serializer: AnyField | None
        ) -> AnyField | None:
            return replacement

    filterset = get_filterset_instance(SomeFilterSet)
    filterset.filter_queryset()
    field = filterset.get_fields()["username"]

    resolved = field.resolve_serializer()

    assert resolved != replacement
    assert resolved != current
    assert resolved != field._serializer

    assert isinstance(resolved, serializers.CharField)
    assert resolved.min_length == 27
    assert resolved.context

    assert not current.context
    assert not replacement.context
    assert not SomeFilterSet.compiled_fields["username"]._serializer.context


def test_filter_resolve_serializer_replacement_attr_changed() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(required=False))

        def get_serializer(
            self, param: str, serializer: AnyField | None
        ) -> AnyField | None:
            serializer.max_length = 25
            return serializer

    filterset = get_filterset_instance(SomeFilterSet)
    filterset.filter_queryset()

    field = filterset.get_fields()["username"]
    resolved = field.resolve_serializer()

    assert resolved == field._serializer
    assert resolved.context
    assert resolved.max_length == 25

    assert not SomeFilterSet.compiled_fields["username"]._serializer.context


def test_filter_resolve_serializer_replacement_failed_to_resolve() -> None:
    f = serializers.CharField(required=False)

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(f)

        def get_serializer(
            self, param: str, serializer: AnyField | None
        ) -> AnyField | None:
            return None

    filterset = get_filterset_instance(SomeFilterSet)

    with pytest.raises(
        ValueError,
        match="Serializer could not be resolved for 'username'",
    ):
        filterset.filter_queryset()
    assert not f.context
    assert not SomeFilterSet.compiled_fields["username"]._serializer.context


def test_filter_run_validation() -> None:
    class SomeFilterSet(FilterSet[Any]):
        name = Filter(serializers.CharField())
        username = Filter(serializers.CharField())

        def run_validation(self, value: str, serializer: AnyField, param: str) -> Any:
            if param == "name":
                return super().run_validation(value, serializer, param)
            return value.replace("1", "X")

    filterset = get_filterset_instance(SomeFilterSet, query="name=a&username=b")
    filterset.get_groups()

    fields = filterset.get_fields()

    name = fields["name"]
    username = fields["username"]
    assert name.run_validation("abc123", serializers.CharField()) == "abc123"
    assert username.run_validation("abc123", serializers.CharField()) == "abcX23"


def test_filter_parse_value() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(required=False))

    filterset = get_filterset_instance(SomeFilterSet)
    filterset.get_groups()

    username = filterset.get_fields()["username"]
    username.run_validation = MagicMock()

    username.parse_value("123")
    username.parse_value(empty)
    username.parse_value("")

    username.run_validation.assert_has_calls(
        calls=[
            call("123", username._serializer),
            call(empty, username._serializer),
            call(empty, username._serializer),
        ]
    )


def test_filter_parse_value_case_blank_keep() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(required=False), blank="keep")

    filterset = get_filterset_instance(SomeFilterSet)
    filterset.get_groups()

    username = filterset.get_fields()["username"]
    username.run_validation = MagicMock()

    username.parse_value("")
    username.run_validation.assert_called_once_with("", username._serializer)


def test_filter_parse_value_initial_string_parsing() -> None:
    class SomeFilterSet(FilterSet[Any]):
        created = Filter(serializers.DateTimeField(required=False))

    filterset = get_filterset_instance(SomeFilterSet)
    filterset.get_groups()

    created = filterset.get_fields()["created"]
    created.run_validation = MagicMock()

    created.parse_value(" 2017-01-01\t\n\r")
    created.run_validation.assert_called_once_with("2017-01-01", created._serializer)

    with pytest.raises(
        serializers.ValidationError,
        match="Null characters are not allowed",
    ):
        created.parse_value("2017-01-01\0")


def test_entry_repr() -> None:
    entry = Entry(
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
    [
        # Field names
        (
            Filter(field="username"),
            Entry(value="value", expression=Q(username="value")),
        ),
        (
            Filter(field="username", lookup="icontains"),
            Entry(value="value", expression=Q(username__icontains="value")),
        ),
        (
            Filter(field="username", lookup="icontains", negate=True),
            Entry(value="value", expression=~Q(username__icontains="value")),
        ),
        # Templates
        (
            Filter(template=Q("username") | Q("email")),
            Entry(value="value", expression=Q(username="value") | Q(email="value")),
        ),
        (
            Filter(template=Q("username__icontains") | Q("email__contains")),
            Entry(
                value="value",
                expression=Q(username__icontains="value") | Q(email__contains="value"),
            ),
        ),
        (
            Filter(template=Q("username") | Q("email"), negate=True),
            Entry(
                value="value",
                expression=~(Q(username="value") | Q(email="value")),
            ),
        ),
        # Field expressions
        (
            Filter(param="username", field=Length("username")),
            Entry(
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
                value="value",
                expression=Q(_default_alias_username="value"),
                aliases={
                    "_default_alias_username": F("username"),
                    "my_email_alias": F("email"),
                },
            ),
        ),
    ],
)
def test_filter_resolve_entry_attrs(f: Filter, entry: Entry) -> None:
    assert f.resolve_entry_attrs("value") == entry


def test_filter_resolve_entry_attrs_child() -> None:
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
    entry = f.children[0].resolve_entry_attrs(5)
    assert entry == Entry(
        group="user_group",
        value=5,
        aliases={"_default_alias_username.min_length": Length("username")},
        expression=Q(**{"_default_alias_username.min_length__gte": 5}),
    )


def test_filter_resolve_entry() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(required=False),
            children=[
                Filter(param="icontains", lookup="icontains"),
            ],
        )

    filterset = get_filterset_instance(SomeFilterSet)
    filterset.get_groups()

    username = filterset.get_fields()["username"]
    username.resolve_entry_attrs = MagicMock(side_effect=username.resolve_entry_attrs)

    entry = username.resolve_entry(QueryDict("username=hello"))
    username.resolve_entry_attrs.assert_called_once_with("hello")

    assert entry == Entry(value="hello", expression=Q(username="hello"))


def test_filter_resolve_entry_case_method() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(required=False),
            children=[
                Filter(
                    param="icontains",
                    method="get_username_icontains",
                ),
            ],
            method="get_username",
        )
        created = Filter(serializers.DateField(required=False), method="get_created")

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
    filterset.get_groups()
    query = QueryDict("username=hello&username.icontains=heyo&created=2025-01-01")

    fields = filterset.get_fields()
    username, created = fields["username"], fields["created"]
    username.resolve_entry_attrs = MagicMock(side_effect=username.resolve_entry_attrs)

    username_entry = username.resolve_entry(query)
    username.resolve_entry_attrs.assert_not_called()
    assert username_entry == Entry(value="hello", expression=Q(username="hello"))

    username_contains_entry = username.children[0].resolve_entry(query)
    assert username_contains_entry == Entry(
        value="heyo", expression=Q(username__icontains="heyo")
    )

    created_entry = created.resolve_entry(query)
    assert created_entry == Entry(
        group="my-group",
        aliases={"dummy": F("created")},
        value=datetime.date(2025, 1, 1),
        expression=Q(dummy__gte=datetime.date(2025, 1, 1)),
    )


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
        )
        created = Filter(
            serializers.DateField(),
            namespace=True,
            children=[
                Filter(param="gte", lookup="gte"),
                Filter(
                    serializers.DateField(required=False),
                    param="date",
                    lookup="date",
                    children=[
                        Filter(param="gte", lookup="date__gte"),
                    ],
                ),
            ],
        )

        def get_username_icontains(self, param: str, value: str) -> Q:
            return Q(username__icontains=value)

        def handle_errors(self, errordict: dict[str, Any]) -> None:
            # do not raise errors for testing purposes
            pass

    filterset = get_filterset_instance(SomeFilterSet)
    filterset.get_groups()

    fields = filterset.get_fields()
    username, created = fields["username"], fields["created"]
    query = QueryDict("username.icontains=hello&created.gte=invalid")

    # Partial case
    entries, errors = username.resolve(query)
    assert entries == {
        "username.icontains": Entry(
            value="hello", expression=Q(username__icontains="hello")
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
        "username": Entry(value="abc", expression=Q(username="abc")),
        "username.icontains": Entry(
            value="hello", expression=Q(username__icontains="hello")
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
            value=datetime.date(2024, 1, 1),
            expression=Q(created__date__gte=datetime.date(2024, 1, 1)),
        ),
    }
    assert errors == {
        "created.gte": [
            ErrorDetail(string="This field is required.", code="required"),
        ],
    }


def test_filter_get_all_children():
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
