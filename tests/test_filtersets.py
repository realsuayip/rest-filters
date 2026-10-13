import datetime
import operator
from collections.abc import Callable
from typing import Any

from django.db.models import F, Q, Value
from django.db.models.functions import Concat

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.request import Request
from rest_framework.views import APIView

import pytest

from rest_filters import Blank, Filter, FilterSet, Multi
from rest_filters.constraints import Constraint, MutuallyExclusive
from rest_filters.filters import Entry
from rest_filters.filtersets.base import Entries, Options
from rest_filters.utils import notset
from tests.test_filters import get_filterset_instance
from tests.testapp.models import User
from tests.testapp.views import UserView


def test_filterset_options() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

        class Meta:
            fields = ("username",)
            known_parameters = ("page", "page_size")
            extend_known_parameters = ("version",)
            handle_unknown_parameters = True
            combinators = {"group": operator.or_}
            constraints = (MutuallyExclusive(fields=["username", "created"]),)
            blank = Blank.KEEP
            multi = Multi.FIRST
            default_group = "custom"

    options = SomeFilterSet._options
    assert isinstance(options, Options)

    assert options.fields == ("username",)
    assert tuple(options.known_parameters) == ("page", "page_size", "version")
    assert options.handle_unknown_parameters is True
    assert options.combinators == {"group": operator.or_}
    assert options.blank == Blank.KEEP
    assert options.multi == Multi.FIRST
    assert options.default_group == "custom"

    assert len(options.constraints) == 1
    assert isinstance(options.constraints[0], MutuallyExclusive)
    assert options.constraints[0].fields == ["username", "created"]


def test_filterset_options_no_meta() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

    options = SomeFilterSet._options
    assert isinstance(options, Options)

    assert options.fields is notset
    assert options.known_parameters == [
        "page",
        "page_size",
        "cursor",
        "ordering",
        "version",
        "format",
    ]
    assert options.combinators == {}
    assert options.constraints == []
    assert options.blank == Blank.OMIT
    assert options.default_group == "chain"
    assert options.multi == Multi.DISALLOW
    assert options.noop is False


def test_filterset_options_partial_meta() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

        class Meta:
            known_parameters = ("page", "page_size")

    options = SomeFilterSet._options
    assert isinstance(options, Options)

    assert options.fields is notset
    assert tuple(options.known_parameters) == ("page", "page_size")
    assert options.combinators == {}
    assert options.constraints == []


def test_filterset_inherits_meta_when_not_defined() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

        class Meta:
            fields = ("username",)
            noop = True

    class Child(Parent):
        first_name = Filter(serializers.CharField())

    assert Child._options.fields == ("username",)
    assert Child._options.noop is True
    assert list(Child._compiled_fields) == ["username"]


def test_filterset_local_meta_replaces_inherited_options() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

        class Meta:
            fields = ("username",)
            noop = True

    class Child(Parent):
        class Meta:
            fields = ("created",)

    assert Child._options.fields == ("created",)
    assert Child._options.noop is False
    assert list(Child._compiled_fields) == ["created"]


def test_filterset_explicit_meta_inheritance_preserves_other_options() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

        class Meta:
            fields = ("username",)
            noop = True

    class Child(Parent):
        class Meta(Parent.Meta):
            fields = ("created",)

    assert Child._options.fields == ("created",)
    assert Child._options.noop is True
    assert list(Child._compiled_fields) == ["created"]


def test_filterset_compiled_fields_default() -> None:
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

    compiled_fields = SomeFilterSet._compiled_fields
    assert list(compiled_fields) == ["username", "created"]


def test_filterset_compiled_fields_inheritance() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())

    class Child(Parent):
        created = Filter(serializers.DateField())

    class Grandchild(Child):
        pass

    assert Parent._declared_fields == {"username": Parent.username}
    assert Child._declared_fields == {
        "username": Parent.username,
        "created": Child.created,
    }
    assert Grandchild._declared_fields == Child._declared_fields
    assert Child._declared_fields is not Parent._declared_fields
    assert Grandchild._declared_fields is not Child._declared_fields
    assert list(Child._compiled_fields) == ["username", "created"]
    assert list(Grandchild._compiled_fields) == ["username", "created"]
    assert Child._compiled_fields["username"] is not Parent.username


def test_filterset_merged_registry_keeps_local_overrides_separate_from_base() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

    class Child(Parent):
        username = Filter(serializers.IntegerField())
        created = None  # type: ignore[assignment]

    assert Parent._declared_fields == {
        "username": Parent.username,
        "created": Parent.created,
    }
    assert Child._declared_fields == {"username": Child.username}
    assert Child._declared_fields["username"] is not Parent._declared_fields["username"]


def test_filterset_reusing_filter_does_not_rename_parent_or_sibling() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())

    class Renamed(Parent):
        username = None  # type: ignore[assignment]
        other = Parent.username

    class Sibling(Parent):
        pass

    assert Renamed._compiled_fields["other"].get_param_name() == "other"
    assert Parent._compiled_fields["username"].get_param_name() == "username"
    assert Sibling._compiled_fields["username"].get_param_name() == "username"


def test_filterset_reusing_filter_keeps_both_inherited_and_local_names() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())

    class Child(Parent):
        other = Parent.username

    fields = Child._compiled_fields
    assert list(fields) == ["username", "other"]
    assert fields["username"] is not fields["other"]
    assert fields["username"].get_param_name() == "username"
    assert fields["other"].get_param_name() == "other"


def test_filterset_reusing_filter_in_same_class_keeps_independent_names() -> None:
    shared = Filter(serializers.CharField())

    class SomeFilterSet(FilterSet[Any]):
        first = shared
        second = shared

    fields = SomeFilterSet._compiled_fields
    assert list(fields) == ["first", "second"]
    assert fields["first"] is not fields["second"]
    assert fields["first"].get_param_name() == "first"
    assert fields["second"].get_param_name() == "second"


def test_filterset_reusing_root_with_children_keeps_independent_trees() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            children=[
                Filter(lookup="icontains"),
            ],
        )

    class Child(Parent):
        other = Parent.username

    username = Child._compiled_fields["username"]
    other = Child._compiled_fields["other"]
    assert username.children[0] is not other.children[0]
    assert username.children[0].parent is username
    assert other.children[0].parent is other
    assert username.children[0].get_param_name() == "username.icontains"
    assert other.children[0].get_param_name() == "other.icontains"


def test_filterset_compiled_fields_inherited_overrides() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())

    class Child(Parent):
        username = Filter(serializers.IntegerField())

    class Removed(Parent):
        username = None  # type: ignore[assignment]

    assert list(Child._compiled_fields) == ["username"]
    assert isinstance(
        Child._compiled_fields["username"].get_serializer(),
        serializers.IntegerField,
    )
    assert Removed._compiled_fields == {}


def test_filterset_multiple_inheritance_preserves_left_base_filter_removal() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())
        created = Filter(serializers.DateField())

    class Removed(Parent):
        username = None  # type: ignore[assignment]

    class Other(Parent):
        pass

    class Child(Removed, Other):
        pass

    assert Child.username is None
    assert list(Child._compiled_fields) == ["created"]


def test_filterset_left_inherited_filter_wins_over_right_base_removal() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())

    class Left(Parent):
        pass

    class Right(Parent):
        username = None  # type: ignore[assignment]

    class Child(Left, Right):
        pass

    assert list(Child._compiled_fields) == ["username"]


def test_filterset_collecting_fields_does_not_invoke_or_remove_descriptor() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())

    class Shadow:
        def __get__(self, instance: Any, owner: Any) -> Any:
            raise AssertionError("Collection should not invoke descriptors")

    class Shadowed(Parent):
        username = Shadow()

    class Other(Parent):
        pass

    class Child(Shadowed, Other):
        pass

    assert list(Child._compiled_fields) == ["username"]


def test_filterset_left_base_shadow_blocks_filter_declared_only_on_right() -> None:
    class Parent(FilterSet[Any]):
        x = Filter(serializers.CharField())

    class Left(Parent):
        y: Any = None

    class Right(Parent):
        y = Filter(serializers.CharField())

    class Child(Left, Right):
        pass

    assert list(Child._compiled_fields) == ["x"]


def test_filterset_right_declaration_overrides_ancestral_removal() -> None:
    class Parent(FilterSet[Any]):
        x = Filter(serializers.CharField())
        z: Any = None

    class Left(Parent):
        pass

    class Right(Parent):
        z = Filter(serializers.CharField())

    class Child(Left, Right):
        pass

    assert list(Child._compiled_fields) == ["x", "z"]


def test_filterset_local_override_preserves_inherited_field_position() -> None:
    class Parent(FilterSet[Any]):
        x = Filter(serializers.CharField())
        y = Filter(serializers.CharField())
        z = Filter(serializers.CharField())

    class Child(Parent):
        x = Filter(serializers.IntegerField())
        extra = Filter(serializers.CharField())

    assert list(Child._compiled_fields) == ["x", "y", "z", "extra"]
    assert isinstance(
        Child._compiled_fields["x"].get_serializer(),
        serializers.IntegerField,
    )


@pytest.mark.parametrize(
    "value",
    (
        False,
        "disabled",
        0,
    ),
)
def test_filterset_non_none_value_does_not_remove_inherited_filter(value: Any) -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())

    class Child(Parent):
        username = value

    assert list(Child._compiled_fields) == ["username"]


def test_filterset_compiled_fields_multiple_inheritance() -> None:
    class Left(FilterSet[Any]):
        username = Filter(serializers.CharField())

    class Right(FilterSet[Any]):
        username = Filter(serializers.IntegerField())
        created = Filter(serializers.DateField())

    class Child(Left, Right):
        pass

    assert set(Child._compiled_fields) == {"username", "created"}
    assert isinstance(
        Child._compiled_fields["username"].get_serializer(),
        serializers.CharField,
    )


def test_filterset_compiled_fields_inherited_children_are_independent() -> None:
    class Parent(FilterSet[Any]):
        created = Filter(
            serializers.DateField(),
            children=[
                Filter(lookup="gte"),
                Filter(lookup="lte"),
            ],
        )

    class Child(Parent):
        class Meta:
            fields = ("created.gte",)

    class Sibling(Parent):
        pass

    compiled = Child._compiled_fields["created"]
    assert compiled.namespace is True
    assert [child.get_param_name() for child in compiled.children] == ["created.gte"]

    assert Parent.created.namespace is False
    assert len(Parent.created.children) == 2
    assert len(Sibling._compiled_fields["created"].children) == 2


def test_filterset_compilation_preserves_nested_declarations() -> None:
    class SomeFilterSet(FilterSet[Any]):
        created = Filter(
            serializers.DateField(),
            children=[
                Filter(
                    lookup="date",
                    children=[
                        Filter(lookup="gte"),
                        Filter(lookup="lte"),
                    ],
                ),
            ],
        )

        class Meta:
            fields = ("created.date.gte",)

    declared = SomeFilterSet._declared_fields["created"]
    compiled = SomeFilterSet._compiled_fields["created"]

    assert compiled.namespace is True  # created
    assert compiled.children[0].namespace is True  # created.date
    assert [child.lookup for child in compiled.children[0].children] == ["gte"]

    assert declared.namespace is False  # created
    assert declared.children[0].namespace is False  # created.date
    assert [child.lookup for child in declared.children[0].children] == ["gte", "lte"]


def test_filterset_compiled_fields_can_restore_parent_exclusions() -> None:
    class Parent(FilterSet[Any]):
        created = Filter(
            serializers.DateField(),
            children=[Filter(lookup="gte"), Filter(lookup="lte")],
        )
        username = Filter(serializers.CharField())

        class Meta:
            fields = ("created.gte",)

    class Child(Parent):
        class Meta:
            fields = ("created", "created.lte", "username")

    assert list(Parent._declared_fields) == ["created", "username"]
    assert Child._declared_fields == Parent._declared_fields
    assert Child._declared_fields is not Parent._declared_fields
    assert Child._declared_fields["created"] is Parent.created
    assert list(Child._compiled_fields) == ["created", "username"]
    created = Child._compiled_fields["created"]
    assert created.namespace is False
    assert [child.get_param_name() for child in created.children] == ["created.lte"]

    assert len(Parent.created.children) == 2
    assert Parent.created.namespace is False
    assert Parent._compiled_fields["created"].namespace is True
    assert len(Parent._compiled_fields["created"].children) == 1


def test_filterset_compiled_fields_diamond_uses_left_parent_registry() -> None:
    class Parent(FilterSet[Any]):
        username = Filter(serializers.CharField())

    class Left(Parent):
        pass

    class Right(Parent):
        username = Filter(serializers.IntegerField())

    class Child(Left, Right):
        pass

    assert isinstance(
        Child._compiled_fields["username"].get_serializer(),
        serializers.CharField,
    )


def test_filterset_compiled_fields_case_omit() -> None:
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

    compiled_fields = SomeFilterSet._compiled_fields
    assert list(compiled_fields) == ["username"]


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

    created = SomeFilterSet._compiled_fields["created"]
    compiled_fields = SomeFilterSet._compiled_fields
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

    created = SomeFilterSet._compiled_fields["created"]
    compiled_fields = SomeFilterSet._compiled_fields
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

    created = SomeFilterSet._compiled_fields["created"]
    compiled_fields = SomeFilterSet._compiled_fields
    assert compiled_fields == {"created": created}

    assert created.namespace is False
    assert len(created.children) == 1
    assert created.children[0].get_param_name() == "created.year"


@pytest.mark.parametrize(
    "selected_fields",
    (
        ("created",),
        ("created.date",),
    ),
)
def test_filterset_compilation_omits_empty_namespace_and_subclass_can_restore_it(
    selected_fields: tuple[str, ...],
) -> None:
    class Parent(FilterSet[Any]):
        created = Filter(
            serializers.DateField(),
            namespace=True,
            children=[
                Filter(
                    lookup="date",
                    namespace=True,
                    children=[
                        Filter(lookup="gte"),
                    ],
                ),
            ],
        )

        class Meta:
            fields = selected_fields

    class Child(Parent):
        class Meta:
            fields = ("created.date.gte",)

    assert Parent._compiled_fields == {}
    assert len(Parent._declared_fields["created"].children) == 1
    assert len(Parent._declared_fields["created"].children[0].children) == 1
    assert list(Child._compiled_fields) == ["created"]

    instance = get_filterset_instance(
        Child,
        query="created.date.gte=2026-01-01",
    )
    assert instance.get_groups()[1] == {
        "created.date.gte": datetime.date(2026, 1, 1),
    }


def test_filterset_invalid_fields_error_lists_unselected_parents() -> None:
    with pytest.raises(
        ValueError,
        match="The following fields are not valid",
    ) as ctx:

        class SomeFilterSet(FilterSet[Any]):
            username = Filter(serializers.CharField())
            created = Filter(
                serializers.DateField(),
                children=[
                    Filter(
                        lookup="date",
                        children=[
                            Filter(lookup="gte"),
                        ],
                    ),
                ],
            )

            class Meta:
                fields = ("typo",)

    assert str(ctx.value) == (
        "The following fields are not valid: 'typo', available fields: "
        "'username', 'created.date.gte', 'created.date', 'created'"
    )


def test_filterset_compiled_fields_bad_meta_fields() -> None:
    with pytest.raises(
        ValueError,
        match=r"The following fields are not valid: 'bad_value', 'another_bad',"
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

    compiled = SomeFilterSet._compiled_fields["username"]

    instance = get_filterset_instance(SomeFilterSet)
    fields = instance._fields
    copied = fields["username"]

    assert copied is not compiled


def test_filterset_init_copies_constraints() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

        class Meta:
            constraints = [
                MutuallyExclusive(fields=["username", "username.icontains"]),
            ]

    compiled = SomeFilterSet._options.constraints[0]

    instance = get_filterset_instance(SomeFilterSet)
    constraints = instance._constraints
    copied = constraints[0]

    assert copied is not compiled


def test_filterset_get_group_entry() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet)
    entry = instance.get_group_entry(
        "group",
        {
            "username": Entry(
                group="chain", value="hello", expression=Q(username="hello")
            ),
            "username.icontains": Entry(
                group="chain", value="hello", expression=Q(username__icontains="hello")
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
            "username": Entry(
                group="chain", value="hello", expression=Q(username="hello")
            ),
            "username.icontains": Entry(
                group="chain", value="hello", expression=Q(username__icontains="hello")
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
                group="chain",
                value="hello",
                expression=Q(username="hello"),
                aliases={"some_alias": Value("some")},
            ),
            "username.icontains": Entry(
                group="chain",
                value="hello",
                expression=Q(username__icontains="hello"),
                aliases={"other_alias": Value("öther")},
            ),
            "username.startswith": Entry(
                group="chain",
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
        Entry(group="chain", value="hello", expression=Q(username__icontains="hello")),
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
            group="chain",
            value="hello",
            aliases={"name": Concat(Value("user"), F("username"))},
            expression=Q(name__icontains="hello"),
        ),
    )
    assert str(queryset.query) == str(outcome.query)


def test_filterset_add_to_queryset_case_noop() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    original = User.objects.all()
    instance = get_filterset_instance(SomeFilterSet)
    queryset = instance.add_to_queryset(
        original,
        Entry(group="chain", value="hello", expression=None),
    )
    assert queryset is original
    assert "WHERE" not in str(queryset.query)


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
                group="chain",
                value="hello",
                expression=Q(username="hello"),
            ),
            "username.icontains": Entry(
                group="chain",
                value="hello",
                expression=Q(username__icontains="hello"),
            ),
        },
    )
    assert str(queryset.query) == str(outcome.query)


@pytest.mark.django_db
def test_get_combinator() -> None:
    g = {}

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            group="names",
        )
        first_name = Filter(
            serializers.CharField(),
            group="names",
        )

        def get_combinator(self, group: str, entries: Entries) -> Callable[..., Any]:
            g[group] = entries
            return operator.or_

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello&first_name=john",
    )
    queryset = instance.filter_queryset()
    expected = User.objects.filter(
        Q(username="hello") | Q(first_name="john"),
    )
    assert g == {
        "names": {
            "username": Entry(
                group="names",
                aliases=None,
                value="hello",
                expression=Q(username="hello"),
            ),
            "first_name": Entry(
                group="names",
                aliases=None,
                value="john",
                expression=Q(first_name="john"),
            ),
        }
    }
    assert str(queryset.query) == str(expected.query)


def test_get_group_entry() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        first_name = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet)
    entry = instance.get_group_entry(
        "group",
        {
            "username": Entry(
                group="chain",
                value="hello",
                expression=Q(username="hello"),
                aliases={
                    "some_alias": Value("hello"),
                },
            ),
            "first_name.icontains": Entry(
                group="chain",
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
                group="chain",
                value="hello",
                expression=Q(username="hello"),
                aliases={
                    "some_alias": Value("hello"),
                },
            ),
            "first_name.icontains": Entry(
                group="chain",
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
                group="chain",
                value="hello",
                expression=Q(username="hello"),
            ),
            "first_name.icontains": Entry(
                group="chain",
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


def test_get_group_entry_case_noop() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())
        first_name = Filter(serializers.CharField(), noop=True)

    instance = get_filterset_instance(SomeFilterSet)
    entry = instance.get_group_entry(
        "group",
        {
            "username": Entry(
                group="chain",
                value="hello",
                expression=Q(username="hello"),
            ),
            "first_name": Entry(
                group="chain",
                value="john",
                expression=Q(),
            ),
        },
    )
    assert entry == Entry(
        group="group",
        value={
            "username": "hello",
            "first_name": "john",
        },
        expression=Q(username="hello"),
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


@pytest.mark.django_db
def test_filter_queryset_case_namespace() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="names.username")
        first_name = Filter(serializers.CharField(), group="names.first_name")
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
def test_filter_queryset_case_namespace_with_single_group() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="names.g")
        first_name = Filter(serializers.CharField(), group="names.g")
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
@pytest.mark.parametrize(
    "sibling_group",
    (
        "personal.ab",
        "personal.ab.detail",
    ),
)
def test_filter_queryset_namespace_excludes_similarly_named_sibling(
    sibling_group: str,
) -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            group="personal.a",
        )
        first_name = Filter(
            serializers.CharField(),
            group="personal.a.detail",
        )
        last_name = Filter(
            serializers.CharField(),
            group=sibling_group,
        )

        class Meta:
            combinators = {"@personal.a": operator.or_}

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello&first_name=john&last_name=doe",
    )
    sql, params = instance.filter_queryset().query.sql_with_params()

    assert sql.split(" WHERE ", 1)[1] == (
        '(("testapp_user"."username" = %s OR "testapp_user"."first_name" = %s) '
        'AND "testapp_user"."last_name" = %s)'
    )
    assert params == ("hello", "john", "doe")


@pytest.mark.django_db
def test_filter_queryset_deep_namespace_combines_child_groups() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            group="personal.details.names.user",
        )
        first_name = Filter(
            serializers.CharField(),
            group="personal.details.names.first",
        )
        last_name = Filter(
            serializers.CharField(),
            group="personal.details.other",
        )

        class Meta:
            combinators = {"@personal.details.names": operator.or_}

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello&first_name=john&last_name=doe",
    )
    sql, params = instance.filter_queryset().query.sql_with_params()

    assert sql.split(" WHERE ", 1)[1] == (
        '(("testapp_user"."username" = %s OR "testapp_user"."first_name" = %s) '
        'AND "testapp_user"."last_name" = %s)'
    )
    assert params == ("hello", "john", "doe")


@pytest.mark.django_db
def test_filter_queryset_deep_namespace_combines_own_group_and_child() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            group="personal.details.names",
        )
        first_name = Filter(
            serializers.CharField(),
            group="personal.details.names.first",
        )
        last_name = Filter(
            serializers.CharField(),
            group="personal.details.other",
        )

        class Meta:
            combinators = {"@personal.details.names": operator.or_}

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello&first_name=john&last_name=doe",
    )
    sql, params = instance.filter_queryset().query.sql_with_params()

    assert sql.split(" WHERE ", 1)[1] == (
        '(("testapp_user"."username" = %s OR "testapp_user"."first_name" = %s) '
        'AND "testapp_user"."last_name" = %s)'
    )
    assert params == ("hello", "john", "doe")


@pytest.mark.django_db
def test_filter_queryset_case_namespace_complex() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="personal")
        first_name = Filter(serializers.CharField(), group="personal.detail")
        last_name = Filter(serializers.CharField(), group="personal.detail")

        class Meta:
            combinators = {
                "@personal": operator.or_,
            }

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello&first_name=john&last_name=doe",
    )
    expected = User.objects.filter(
        Q(username="hello") | (Q(first_name="john") & Q(last_name="doe")),
    )
    queryset = instance.filter_queryset()
    assert str(queryset.query) == str(expected.query)


@pytest.mark.django_db
def test_filter_queryset_case_namespace_complex2() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="personal.info")

        role1 = Filter(serializers.CharField(), field="role", group="personal.role")
        role2 = Filter(serializers.CharField(), field="role", group="personal.role")

        location1 = Filter(
            serializers.CharField(), field="location", group="personal.location"
        )
        location2 = Filter(
            serializers.CharField(), field="location", group="personal.location"
        )

        class Meta:
            combinators = {
                "personal.role": operator.or_,
                "personal.location": operator.or_,
            }

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello"
        "&role1=some_role"
        "&role2=some_other_role"
        "&location1=some_location"
        "&location2=some_other_location",
    )
    expected = User.objects.filter(
        Q(username="hello")
        & (Q(role="some_role") | Q(role="some_other_role"))
        & (Q(location="some_location") | Q(location="some_other_location"))
    )
    queryset = instance.filter_queryset()
    assert str(queryset.query) == str(expected.query)


@pytest.mark.django_db
def test_filter_queryset_case_namespace_complex3() -> None:
    seen = []

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="personal.info")

        role1 = Filter(serializers.CharField(), field="role", group="personal.s.role")
        role2 = Filter(serializers.CharField(), field="role", group="personal.s.role")

        location1 = Filter(
            serializers.CharField(), field="location", group="personal.s.location"
        )
        location2 = Filter(
            serializers.CharField(), field="location", group="personal.s.location"
        )

        class Meta:
            combinators = {
                "@personal": operator.or_,
                "@personal.s": operator.and_,
                "personal.s.role": operator.or_,
                "personal.s.location": operator.or_,
            }

        def get_group_entry(self, group: str, value: Any) -> Entry:
            seen.append(group)
            return super().get_group_entry(group, value)

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello"
        "&role1=some_role"
        "&role2=some_other_role"
        "&location1=some_location"
        "&location2=some_other_location",
    )
    expected = User.objects.filter(
        Q(username="hello")
        | (
            (Q(role="some_role") | Q(role="some_other_role"))
            & (Q(location="some_location") | Q(location="some_other_location"))
        )
    )
    queryset = instance.filter_queryset()
    assert str(queryset.query) == str(expected.query)
    assert seen == [
        "personal.info",
        "personal.s.role",
        "personal.s.location",
        "@personal.s",
        "@personal",
    ]


@pytest.mark.django_db
def test_filter_queryset_case_namespace_complex4() -> None:
    seen = []

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="personal.x")
        first_name = Filter(serializers.CharField(), group="personal.x.z")

        def get_group_entry(self, group: str, entries: dict[str, Entry]) -> Entry:
            seen.append(group)
            return super().get_group_entry(group, entries)

    instance = get_filterset_instance(
        SomeFilterSet, query="username=hello&first_name=john"
    )
    instance.filter_queryset()
    assert seen == [
        "personal.x",
        "personal.x.z",
        "@personal.x",
    ]


@pytest.mark.django_db
def test_filter_queryset_case_namespace_complex5() -> None:
    seen = []

    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="personal.x")
        first_name = Filter(serializers.CharField(), group="personal.x.z")

        def get_group_entry(self, group: str, entries: dict[str, Entry]) -> Entry:
            seen.append(group)
            return super().get_group_entry(group, entries)

    instance = get_filterset_instance(SomeFilterSet, query="username=hello")
    instance.filter_queryset()
    assert seen == ["personal.x"]


def test_filter_queryset_case_noop() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="names", noop=True)
        first_name = Filter(serializers.CharField(), group="names", noop=True)
        last_name = Filter(serializers.CharField(), noop=True)

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello&first_name=john&last_name=doe",
    )

    queryset = instance.filter_queryset()
    assert queryset is UserView.queryset
    assert "WHERE" not in str(queryset.query)


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
    assert constraints is instance._constraints

    # .run_validation()
    class MyField(serializers.IntegerField):
        def run_validation(self, data: Any = ...) -> Any:
            ret = super().run_validation(data)
            return ret + 1

    f = MyField()
    value = instance.run_validation("1", f, "param")
    assert value == 2


def test_get_groups() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(
            serializers.CharField(),
            aliases={
                "random_alias": F("username"),
            },
            required=True,
        )
        created = Filter(
            serializers.DateField(),
            children=[
                Filter(lookup="gte"),
                Filter(lookup="lte"),
            ],
            group="created_g",
        )
        first_name = Filter(
            serializers.CharField(allow_blank=True),
            children=[
                Filter(
                    lookup="exact",
                    blank=Blank.KEEP,
                )
            ],
        )
        last_name = Filter(serializers.CharField())

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello"
        "&created.gte=2023-01-01"
        "&created.lte=2023-01-01"
        "&first_name.exact=",
    )

    groupdict, valuedict = instance.get_groups()
    assert groupdict == {
        "chain": {
            "username": Entry(
                group="chain",
                aliases={
                    "random_alias": F("username"),
                },
                value="hello",
                expression=Q(username="hello"),
            ),
            "first_name.exact": Entry(
                group="chain",
                aliases=None,
                value="",
                expression=Q(first_name__exact=""),
            ),
        },
        "created_g": {
            "created.gte": Entry(
                group="created_g",
                aliases=None,
                value=datetime.date(2023, 1, 1),
                expression=Q(created__gte=datetime.date(2023, 1, 1)),
            ),
            "created.lte": Entry(
                group="created_g",
                aliases=None,
                value=datetime.date(2023, 1, 1),
                expression=Q(created__lte=datetime.date(2023, 1, 1)),
            ),
        },
    }
    assert valuedict == {
        "username": "hello",
        "created.gte": datetime.date(2023, 1, 1),
        "created.lte": datetime.date(2023, 1, 1),
        "first_name.exact": "",
    }

    instance = get_filterset_instance(
        SomeFilterSet,
        query="first_name.exact=",
    )
    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()
    assert ctx.value.detail == {
        "username": [
            ErrorDetail(
                string="This field is required.",
                code="required",
            )
        ]
    }


def test_handle_unknown_parameters() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField())

    instance = get_filterset_instance(SomeFilterSet)
    r = instance.handle_unknown_parameters(
        ["unknown", "goes", "here", "phoenix"],
        ["known", "go", "there", "where"],
    )
    assert r == {
        "unknown": ["This query parameter does not exist. Did you mean 'known'?"],
        "goes": ["This query parameter does not exist. Did you mean 'go'?"],
        "here": [
            "This query parameter does not exist. Did you mean one of these:"
            " 'where', 'there'?"
        ],
        "phoenix": ["This query parameter does not exist."],
    }


def test_get_groups_all_errors_are_merged() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), required=True)

        first_name = Filter(serializers.CharField())
        last_name = Filter(serializers.CharField())

        created = Filter(serializers.DateField())

        class Meta:
            constraints = [
                MutuallyExclusive(
                    fields=[
                        "first_name",
                        "last_name",
                    ]
                )
            ]

    instance = get_filterset_instance(
        SomeFilterSet,
        query="first_name=hello&last_name=world&creates=2024-01-01",
    )
    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()
    assert ctx.value.detail == {
        "username": [ErrorDetail(string="This field is required.", code="required")],
        "non_field_errors": [
            ErrorDetail(
                string="The following fields are mutually exclusive, you may only"
                " provide one of them: 'first_name', 'last_name'",
                code="invalid",
            )
        ],
        "creates": [
            ErrorDetail(
                string="This query parameter does not exist. Did you mean 'created'?",
                code="invalid",
            )
        ],
    }


def test_get_groups_all_errors_are_merged_custom_unknown_parameter_impl() -> None:
    class SomeFilterSet(FilterSet[Any]):
        first_name = Filter(serializers.CharField())
        last_name = Filter(serializers.CharField())

        class Meta:
            constraints = [MutuallyExclusive(fields=["first_name", "last_name"])]

        def handle_unknown_parameters(
            self, unknown: list[str], known: list[str]
        ) -> dict[str, Any]:
            s = super().handle_unknown_parameters(unknown, known)
            return {
                "non_field_errors": [
                    f"{key}: {''.join(value)}" for key, value in s.items()
                ]
            }

    instance = get_filterset_instance(
        SomeFilterSet,
        query="first_name=hello&last_name=world&unknown1=u&unknown2=u",
    )
    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()

    assert ctx.value.detail == {
        "non_field_errors": [
            ErrorDetail(
                string="The following fields are mutually exclusive, you may only"
                " provide one of them: 'first_name', 'last_name'",
                code="invalid",
            ),
            ErrorDetail(
                string="unknown1: This query parameter does not exist.", code="invalid"
            ),
            ErrorDetail(
                string="unknown2: This query parameter does not exist.", code="invalid"
            ),
        ]
    }


def test_get_groups_all_errors_are_merged_custom_constraint_impl() -> None:
    class CustomConstraint(Constraint):
        def check(self, values: dict[str, Any]) -> None:
            raise serializers.ValidationError({"first_name": ["Constraint failed"]})

    class SomeFilterSet(FilterSet[Any]):
        first_name = Filter(serializers.CharField(), required=True)

        class Meta:
            constraints = [CustomConstraint()]

    instance = get_filterset_instance(
        SomeFilterSet,
        query="",
    )
    with pytest.raises(serializers.ValidationError) as ctx:
        instance.get_groups()
    assert ctx.value.detail == {
        "first_name": [
            ErrorDetail(string="This field is required.", code="required"),
            ErrorDetail(string="Constraint failed", code="invalid"),
        ]
    }


def test_get_groups_considers_known_parameters() -> None:
    class SomeFilterSet(FilterSet[Any]):
        first_name = Filter(serializers.CharField())

        class Meta:
            known_parameters = ["page"]

    instance = get_filterset_instance(
        SomeFilterSet,
        query="first_name=hello&page=1",
    )
    _, valuedict = instance.get_groups()
    assert valuedict == {"first_name": "hello"}


def test_get_groups_noop() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="names", noop=True)
        first_name = Filter(serializers.CharField(), group="names", noop=True)
        last_name = Filter(serializers.CharField(), noop=True)

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello&first_name=john&last_name=doe",
    )

    groupdict, valuedict = instance.get_groups()
    assert groupdict == {
        "names": {
            "username": Entry(
                group="names", aliases=None, value="hello", expression=None
            ),
            "first_name": Entry(
                group="names", aliases=None, value="john", expression=None
            ),
        },
        "chain": {
            "last_name": Entry(
                group="chain", aliases=None, value="doe", expression=None
            )
        },
    }

    assert valuedict == {
        "username": "hello",
        "first_name": "john",
        "last_name": "doe",
    }


def test_get_groups_noop_via_filterset() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="names")
        first_name = Filter(serializers.CharField(), group="names")
        last_name = Filter(serializers.CharField())

        class Meta:
            noop = True

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello&first_name=john&last_name=doe",
    )

    groupdict, valuedict = instance.get_groups()
    assert groupdict == {
        "names": {
            "username": Entry(
                group="names", aliases=None, value="hello", expression=None
            ),
            "first_name": Entry(
                group="names", aliases=None, value="john", expression=None
            ),
        },
        "chain": {
            "last_name": Entry(
                group="chain", aliases=None, value="doe", expression=None
            )
        },
    }

    assert valuedict == {
        "username": "hello",
        "first_name": "john",
        "last_name": "doe",
    }


def test_get_groups_noop_via_filterset_partial() -> None:
    class SomeFilterSet(FilterSet[Any]):
        username = Filter(serializers.CharField(), group="names")
        first_name = Filter(serializers.CharField(), group="names", noop=False)
        last_name = Filter(serializers.CharField())

        class Meta:
            noop = True

    instance = get_filterset_instance(
        SomeFilterSet,
        query="username=hello&first_name=john&last_name=doe",
    )

    groupdict, valuedict = instance.get_groups()
    assert groupdict == {
        "names": {
            "username": Entry(
                group="names", aliases=None, value="hello", expression=None
            ),
            "first_name": Entry(
                group="names",
                aliases=None,
                value="john",
                expression=Q(first_name="john"),
            ),
        },
        "chain": {
            "last_name": Entry(
                group="chain", aliases=None, value="doe", expression=None
            )
        },
    }

    assert valuedict == {
        "username": "hello",
        "first_name": "john",
        "last_name": "doe",
    }
