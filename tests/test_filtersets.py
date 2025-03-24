import operator
from typing import Any

from django.db.models import F, Q, Value
from django.db.models.functions import Concat

from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.views import APIView

import pytest

from rest_filters import Filter, FilterSet
from rest_filters.constraints import MutuallyExclusive
from rest_filters.filters import Entry
from rest_filters.filtersets import Options
from rest_filters.utils import notset
from tests.test_filters import get_filterset_instance
from tests.testapp.models import User


def test_filterset_options() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

        class Meta:
            fields = ("username",)
            known_parameters = ("page", "page_size")
            combinators = {"group": operator.or_}
            constraints = (MutuallyExclusive(fields=["username", "created"]),)

    options = SomeFilterSet.options
    assert isinstance(options, Options)

    assert options.fields == ("username",)
    assert options.known_parameters == ("page", "page_size")
    assert options.combinators == {"group": operator.or_}

    assert len(options.constraints) == 1
    assert isinstance(options.constraints[0], MutuallyExclusive)
    assert options.constraints[0].fields == ["username", "created"]


def test_filterset_options_no_meta() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

    options = SomeFilterSet.options
    assert isinstance(options, Options)

    assert options.fields is notset
    assert options.known_parameters == []
    assert options.combinators == {}
    assert options.constraints == []


def test_filterset_options_partial_meta() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

        class Meta:
            known_parameters = ("page", "page_size")

    options = SomeFilterSet.options
    assert isinstance(options, Options)

    assert options.fields is notset
    assert options.known_parameters == ("page", "page_size")
    assert options.combinators == {}
    assert options.constraints == []


def test_filterset_compiled_fields_default():
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))
        created = Filter(
            serializers.DateField(help_text="some date"),
            children=[
                Filter(
                    param="date",
                    lookup="created__date",
                    children=[
                        Filter(
                            param="gte",
                            lookup="created__date__gte",
                        ),
                    ],
                )
            ],
        )

    compiled_fields = SomeFilterSet.compiled_fields
    assert compiled_fields == {
        "username": SomeFilterSet.username,
        "created": SomeFilterSet.created,
    }


def test_filterset_compiled_fields_case_omit():
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))
        created = Filter(
            serializers.DateField(help_text="some date"),
            children=[
                Filter(
                    param="date",
                    lookup="created__date",
                    children=[
                        Filter(
                            param="gte",
                            lookup="created__date__gte",
                        ),
                    ],
                )
            ],
        )

        class Meta:
            fields = ("username",)

    compiled_fields = SomeFilterSet.compiled_fields
    assert compiled_fields == {
        "username": SomeFilterSet.username,
    }


def test_filterset_compiled_fields_case_select_child() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))
        created = Filter(
            serializers.DateField(help_text="some date"),
            children=[
                Filter(
                    param="date",
                    lookup="created__date",
                    children=[
                        Filter(
                            param="gte",
                            lookup="created__date__gte",
                        ),
                    ],
                )
            ],
        )

        class Meta:
            fields = ("created.date.gte",)

    created = SomeFilterSet.created
    compiled_fields = SomeFilterSet.compiled_fields
    assert compiled_fields == {"created": created}

    assert created.namespace is True
    assert created.children[0].namespace is True
    assert created.children[0].children[0].namespace is False


def test_filterset_compiled_fields_case_remove_child() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))
        created = Filter(
            serializers.DateField(help_text="some date"),
            children=[
                Filter(
                    param="date",
                    lookup="created__date",
                    children=[
                        Filter(
                            param="gte",
                            lookup="created__date__gte",
                        ),
                    ],
                )
            ],
        )

        class Meta:
            fields = ("created",)

    created = SomeFilterSet.created
    compiled_fields = SomeFilterSet.compiled_fields
    assert compiled_fields == {"created": created}

    assert created.namespace is False
    assert created.children == []


def test_filterset_compiled_fields_case_remove_child_partial() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))
        created = Filter(
            serializers.DateField(help_text="some date"),
            children=[
                Filter(
                    param="date",
                    lookup="created__date",
                ),
                Filter(param="year", lookup="created__year"),
            ],
        )

        class Meta:
            fields = ("created", "created.year")

    created = SomeFilterSet.created
    compiled_fields = SomeFilterSet.compiled_fields
    assert compiled_fields == {"created": created}

    assert created.namespace is False
    assert len(created.children) == 1
    assert created.children[0].get_param_name() == "created.year"


def test_filterset_compiled_fields_bad_meta_fields() -> None:
    with pytest.raises(
        ValueError,
        match=r"Following fields are not valid: 'bad_value', 'another_bad',"
        " available fields: 'username', 'created.date', 'created.year', 'created'",
    ):

        class SomeFilterSet(FilterSet[Any]):
            username = Filter(serializers.CharField(min_length=3))
            created = Filter(
                serializers.DateField(help_text="some date"),
                children=[
                    Filter(
                        param="date",
                        lookup="created__date",
                    ),
                    Filter(param="year", lookup="created__year"),
                ],
            )

            class Meta:
                fields = (
                    "created",
                    "created.year",
                    "bad_value",
                    "another_bad",
                )


def test_filterset_init_copies_compiled_fields() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(min_length=3))

    compiled = SomeFilterSet.compiled_fields["username"]

    instance = get_filterset_instance(SomeFilterSet)
    fields = instance.fields
    copied = fields["username"]

    assert copied is not compiled


def test_filterset_init_copies_constraints() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

        class Meta:
            constraints = [
                MutuallyExclusive(fields=["username", "username.icontains"]),
            ]

    compiled = SomeFilterSet.options.constraints[0]

    instance = get_filterset_instance(SomeFilterSet)
    constraints = instance.constraints
    copied = constraints[0]

    assert copied is not compiled


def test_filterset_get_group_entry() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet)
    entry = instance.get_group_entry(
        "group",
        {
            "username": Entry(value="hello", expression=Q(username="hello")),
            "username.icontains": Entry(
                value="hello", expression=Q(username__icontains="hello")
            ),
        },
    )
    assert entry == Entry(
        group="group",
        value={"username": "hello", "username.icontains": "hello"},
        expression=Q(username="hello") & Q(username__icontains="hello"),
    )


def test_filterset_get_default_group_expression_case_custom_combinator() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

        class Meta:
            combinators = {"group": operator.or_}

    instance = get_filterset_instance(SomeFilterSet)
    entry = instance.get_group_entry(
        "group",
        {
            "username": Entry(value="hello", expression=Q(username="hello")),
            "username.icontains": Entry(
                value="hello", expression=Q(username__icontains="hello")
            ),
        },
    )
    assert entry == Entry(
        group="group",
        value={"username": "hello", "username.icontains": "hello"},
        expression=Q(username="hello") | Q(username__icontains="hello"),
    )


def test_filterset_get_default_group_expression_case_aliases() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

        class Meta:
            combinators = {"group": operator.or_}

    instance = get_filterset_instance(SomeFilterSet)
    entry = instance.get_group_entry(
        "group",
        {
            "username": Entry(
                value="hello",
                expression=Q(username="hello"),
                aliases={"some_alias": Value("some")},
            ),
            "username.icontains": Entry(
                value="hello",
                expression=Q(username__icontains="hello"),
                aliases={"other_alias": Value("öther")},
            ),
            "username.startswith": Entry(
                value="hello2",
                expression=Q(username__startswith="hello2"),
            ),
        },
    )
    assert entry == Entry(
        group="group",
        aliases={
            "some_alias": Value("some"),
            "other_alias": Value("öther"),
        },
        value={
            "username": "hello",
            "username.icontains": "hello",
            "username.startswith": "hello2",
        },
        expression=Q(username="hello")
        | Q(username__icontains="hello")
        | Q(username__startswith="hello2"),
    )


@pytest.mark.django_db
def test_filterset_add_to_queryset() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet)
    outcome = User.objects.filter(Q(username__icontains="hello"))
    queryset = instance.add_to_queryset(
        User.objects.all(),
        Entry(value="hello", expression=Q(username__icontains="hello")),
    )
    assert str(queryset.query) == str(outcome.query)


@pytest.mark.django_db
def test_filterset_add_to_queryset_case_alias() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet)
    outcome = User.objects.alias(
        name=Concat(Value("user"), F("username")),
    ).filter(Q(name__icontains="hello"))

    queryset = instance.add_to_queryset(
        User.objects.all(),
        Entry(
            value="hello",
            aliases={"name": Concat(Value("user"), F("username"))},
            expression=Q(name__icontains="hello"),
        ),
    )
    assert str(queryset.query) == str(outcome.query)


def test_filterset_filter_group() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet)
    outcome = User.objects.filter(Q(username="hello") & Q(username__icontains="hello"))

    queryset = instance.filter_group(
        User.objects.all(),
        "group",
        {
            "username": Entry(
                value="hello",
                expression=Q(username="hello"),
            ),
            "username.icontains": Entry(
                value="hello",
                expression=Q(username__icontains="hello"),
            ),
        },
    )
    assert str(queryset.query) == str(outcome.query)


def test_get_group_entry() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        first_name = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet)
    entry = instance.get_group_entry(
        "group",
        {
            "username": Entry(
                value="hello",
                expression=Q(username="hello"),
                aliases={
                    "some_alias": Value("hello"),
                },
            ),
            "first_name.icontains": Entry(
                value="john",
                expression=Q(first_name__icontains="john"),
                aliases={
                    "some_other_alias": Value("john"),
                },
            ),
        },
    )
    assert entry == Entry(
        group="group",
        aliases={
            "some_alias": Value("hello"),
            "some_other_alias": Value("john"),
        },
        value={
            "username": "hello",
            "first_name.icontains": "john",
        },
        expression=Q(username="hello") & Q(first_name__icontains="john"),
    )


def test_get_group_entry_case_combinator() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        first_name = Filter(serializers.CharField())

        class Meta:
            combinators = {
                "group": operator.or_,
            }

    instance = get_filterset_instance(SomeFilterSet)
    entry = instance.get_group_entry(
        "group",
        {
            "username": Entry(
                value="hello",
                expression=Q(username="hello"),
                aliases={
                    "some_alias": Value("hello"),
                },
            ),
            "first_name.icontains": Entry(
                value="john",
                expression=Q(first_name__icontains="john"),
                aliases={
                    "some_other_alias": Value("john"),
                },
            ),
        },
    )
    assert entry == Entry(
        group="group",
        aliases={
            "some_alias": Value("hello"),
            "some_other_alias": Value("john"),
        },
        value={
            "username": "hello",
            "first_name.icontains": "john",
        },
        expression=Q(username="hello") | Q(first_name__icontains="john"),
    )


def test_get_group_entry_case_no_alias() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        first_name = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet)
    entry = instance.get_group_entry(
        "group",
        {
            "username": Entry(
                value="hello",
                expression=Q(username="hello"),
            ),
            "first_name.icontains": Entry(
                value="john",
                expression=Q(first_name__icontains="john"),
            ),
        },
    )
    assert entry == Entry(
        group="group",
        aliases=None,
        value={
            "username": "hello",
            "first_name.icontains": "john",
        },
        expression=Q(username="hello") & Q(first_name__icontains="john"),
    )


@pytest.mark.django_db
def test_filter_queryset() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="names")
        first_name = Filter(serializers.CharField(), group="names")
        last_name = Filter(serializers.CharField())

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello&first_name=john&last_name=doe",
    )
    expected = User.objects.filter(last_name="doe").filter(
        Q(username="hello") & Q(first_name="john"),
    )
    queryset = instance.filter_queryset()
    assert str(queryset.query) == str(expected.query)


@pytest.mark.django_db
def test_filter_queryset_case_related_field_chain() -> None:
    class SomeFilterSet(FilterSet[Any]):
        company_name = Filter(
            serializers.CharField(),
            field="following_companies__name",
        )
        company_address = Filter(
            serializers.CharField(),
            field="following_companies__address",
        )

    instance = get_filterset_instance(
        SomeFilterSet,
        query="company_name=apple&company_address=california",
    )
    queryset = instance.filter_queryset()
    query = str(queryset.query)

    assert query.count('INNER JOIN "testapp_company"') == 2
    assert query.count('INNER JOIN "testapp_user_following_companies"') == 2
    assert query.count("INNER JOIN") == 4


@pytest.mark.django_db
def test_filter_queryset_case_related_field_group() -> None:
    class SomeFilterSet(FilterSet[Any]):
        company = Filter(
            serializers.CharField(),
            children=[
                Filter(param="name", field="following_companies__name"),
                Filter(param="address", field="following_companies__address"),
            ],
            group="company",
            namespace=True,
        )

    instance = get_filterset_instance(
        SomeFilterSet,
        query="company.name=apple&company.address=california",
    )
    queryset = instance.filter_queryset()
    query = str(queryset.query)

    assert query.count('INNER JOIN "testapp_company"') == 1
    assert query.count('INNER JOIN "testapp_user_following_companies"') == 1
    assert query.count("INNER JOIN") == 2


@pytest.mark.django_db
def test_filter_queryset_case_related_mixed() -> None:
    class SomeFilterSet(FilterSet[Any]):
        company = Filter(
            serializers.CharField(),
            children=[
                Filter(param="name", field="following_companies__name"),
                Filter(param="address", field="following_companies__address"),
            ],
            group="company",
            namespace=True,
        )
        company_id = Filter(
            serializers.IntegerField(),
            field="following_companies",
        )

    instance = get_filterset_instance(
        SomeFilterSet,
        query="company.name=apple&company.address=california&company_id=3",
    )
    queryset = instance.filter_queryset()
    query = str(queryset.query)

    assert query.count('INNER JOIN "testapp_company"') == 1
    assert query.count('INNER JOIN "testapp_user_following_companies"') == 2
    assert query.count("INNER JOIN") == 3


def test_user_overrideable_method_defaults() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet)

    # .get_queryset()
    qs = User.objects.all()
    queryset = instance.get_queryset(qs, {})
    assert queryset is qs

    # .get_default()
    default = instance.get_default("param", 47)
    assert default == 47

    # .get_serializer()
    serializer = instance.get_serializer("param", None)
    assert serializer is None

    s = serializers.CharField()
    serializer = instance.get_serializer("param", s)
    assert serializer is s

    # .get_serializer_context()
    context = instance.get_serializer_context("param")
    assert isinstance(context["request"], Request)
    assert context["format"]
    assert isinstance(context["view"], APIView)
    assert context["filterset"] is instance

    # .get_constraints()
    constraints = instance.get_constraints()
    assert constraints is instance.constraints

    # .run_validation()
    class MyField(serializers.IntegerField):
        def run_validation(self, data: Any = ...) -> Any:
            ret = super().run_validation(data)
            return ret + 1

    f = MyField()
    value = instance.run_validation("1", f, "param")
    assert value == 2
