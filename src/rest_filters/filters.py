from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Literal

from django.db.models import Q
from django.db.models.expressions import BaseExpression, Combinable
from django.http.request import QueryDict

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import SkipField, empty

from rest_filters.utils import AnyField, fill_q_template

if TYPE_CHECKING:
    from rest_framework.fields import _Empty

    from rest_filters.filtersets import FilterSet


class Entry:
    """
    Each Filter ultimately resolves to an Entry object, which contains
    information on how to modify a QuerySet.

    Attributes of Entry objects within the same group are combined to create a
    new Entry instance, representing the cumulative changes to the QuerySet
    made by all filters in that group.
    """

    def __init__(
        self,
        *,
        group: str = "chain",
        aliases: dict[str, Any] | None = None,
        value: Any,
        expression: Any,
    ):
        """
        :param group: Group of this Entry.
        :param aliases: Annotations that are going to be applied to QuerySet.
         These annotations can be referenced in the expression.
        :param value: Parsed value of the query parameter. If groups combined
         multiple query parameters, this will be a dictionary of
         ``{name: value}`` pairs.
        :param expression: Resolved query expression of this Entry.
        """
        self.group = group
        self.aliases = aliases
        self.value = value
        self.expression = expression

    def __repr__(self) -> str:
        return "Entry(group=%r, aliases=%r, value=%r, expression=%r)" % (
            self.group,
            self.aliases,
            self.value,
            self.expression,
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Entry):
            return NotImplemented
        return (
            self.group == other.group
            and self.aliases == other.aliases
            and self.value == other.value
            and self.expression == other.expression
        )


class Filter:
    def __init__(
        self,
        f: AnyField | None = None,
        /,
        *,
        field: str | BaseExpression | Combinable | None = None,
        lookup: str = "",
        template: Q | None = None,
        group: str | None = None,
        negate: bool = False,
        method: str | None = None,
        aliases: dict[str, Any] | None = None,
        param: str | None = None,
        children: list[Filter] | None = None,
        namespace: bool = False,
        blank: Literal["keep", "omit"] | None = None,
        noop: bool = False,
    ) -> None:
        """
        A data descriptor for query parameters.

        :param f: The serializer field that will parse this query parameter. This can
         be left empty if ``FilterSet.get_serializer`` is used to dynamically resolve
         serializer field. A child filter may also omit this, in which case parent
         serializer field is used.
        :param field: A string (field name) or Django expression that determines the
         database field/expression that is going to be filtered against. Child filters
         will inherit this value.
        :param lookup: The lookup that will be used with the resolved database field.
        :param template: A ``Q`` object that determines query expression for this
         parameter. For example ``Q("username") | Q("email")`` will match username or
         email field.
        :param group: Group identifier for this filter. Child filters will inherit their
         parent's group (if set).
        :param negate: Set this to ``True`` to negate the resolved query expression.
        :param method: A method on current FilterSet class that is going to determine
         the query expression for this filter.
        :param aliases: Additional expressions that are going to be added to the
         QuerySet.
        :param param: The name of this query parameter.
        :param children: A list of filters that reside under the namespace of this
         filter.
        :param namespace: When enabled, marks this filter as *namespace* and disables
         it. Only the child filters belonging to this filter will be available.
        :param blank: Determines :py:attr:`rest_filters.conf.AppSettings.BLANK` behavior
         for this filter.
        :param noop: Set this to ``True`` to disable query expression resolution. In
         this mode, the query parameter won't do any filtering, however its value will
         be validated and available.
        """

        self._field = field
        self.lookup = lookup
        self.template = template

        if group is not None and not group.isidentifier():
            raise ValueError("Group names must be valid Python identifiers")
        if blank is not None and blank not in ("keep", "omit"):
            raise ValueError("blank must either be 'keep' or 'omit'")
        if template and lookup:
            raise ValueError(
                "'template' and 'lookup' cannot be used together. Add lookup to"
                " your template instead, for example: Q('username__icontains')"
            )
        if template and field:
            raise ValueError("'template' and 'field' cannot be used together")
        if negate and method:
            raise ValueError(
                "'method' and 'negate' cannot be used together. Negate the"
                " expression in your method instead."
            )

        self._group = group
        self.aliases = aliases

        self.negate = negate
        self.noop = noop

        self._blank = blank
        self.method = method
        self._param = param
        self._serializer = f
        self._filterset: FilterSet[Any] | None = None

        self.namespace = namespace
        self.parent: Filter | None = None
        self.children = children or []
        for child in self.children:
            child.bind(self)

        if not self.children and self.namespace:
            raise ValueError("Namespace filters are required to have child filters")

    def __repr__(self) -> str:
        args = []
        for name in (
            "_field",
            "lookup",
            "template",
            "_group",
            "aliases",
            "negate",
            "noop",
            "_blank",
            "method",
            "_param",
            "_serializer",
            "_filterset",
            "namespace",
            "children",
        ):
            attr = getattr(self, name)
            args.append("%s=%r" % (name, attr))
        return "%s(%s)" % (self.__class__.__name__, ", ".join(args))

    def __set_name__(self, owner: FilterSet[Any], name: str) -> None:
        self.name = name

    @property
    def blank(self) -> Literal["keep", "omit"]:
        if self._blank is None:
            filterset = self.get_filterset()
            return filterset.options.blank
        return self._blank

    def bind(self, parent: Filter) -> None:
        self.parent = parent

        self._param = self._param or self.lookup
        if not self._param:
            raise ValueError(
                "Either 'param' or 'lookup' parameter needs to"
                " be specified for child filters"
            )

    def get_group(self) -> str:
        if self._group is not None:
            return self._group
        elif self.parent is not None:
            return self.parent.get_group()
        return "chain"

    def get_db_field(self) -> str | BaseExpression | Combinable:
        if self.parent and self._field is None:
            return self.parent.get_db_field()
        return self._field or self.name

    def get_param_name(self) -> str:
        try:
            name = self._param or self.name
        except AttributeError as e:
            raise AssertionError("Could not resolve FilterSet") from e
        if self.parent is not None:
            namespace = self.parent.get_param_name()
            return f"{namespace}.{name}"
        return name

    def get_query_value(self, query_dict: QueryDict) -> str | _Empty:
        param = self.get_param_name()
        return query_dict.get(param, empty)

    def get_serializer(self) -> AnyField:
        if self._serializer is not None:
            return self._serializer
        elif self.parent is not None:
            try:
                return self.parent.get_serializer()
            except ValueError:
                pass
        raise ValueError(
            "Serializer could not be resolved for %r" % self.get_param_name()
        )

    def get_filterset(self) -> FilterSet[Any]:
        if self.parent:
            return self.parent.get_filterset()
        assert self._filterset is not None, "Could not resolve FilterSet"
        return self._filterset

    def resolve_serializer(self) -> AnyField:
        filterset, param = self.get_filterset(), self.get_param_name()
        try:
            serializer = self.get_serializer()
        except ValueError:
            dynamic = filterset.get_serializer(param, None)
            if dynamic is None:
                raise
            serializer = copy.deepcopy(dynamic)
        else:
            replacement = filterset.get_serializer(param, serializer)
            if replacement is None:
                raise ValueError(
                    "Serializer could not be resolved for %r" % self.get_param_name()
                )
            if replacement is not serializer:
                serializer = copy.deepcopy(replacement)

        serializer.default = filterset.get_default(param, serializer.default)
        serializer._context = filterset.get_serializer_context(param)  # type: ignore[attr-defined]
        return serializer

    def run_validation(self, value: str | _Empty, serializer: AnyField) -> Any:
        filterset, param = self.get_filterset(), self.get_param_name()
        return filterset.run_validation(value, serializer, param)

    def parse_value(self, value: str | _Empty) -> Any:
        if value is not empty:
            value = serializers.CharField(allow_blank=True).run_validation(value)
            if value == "" and self.blank == "omit":
                value = empty
        serializer = self.resolve_serializer()
        return self.run_validation(value, serializer)

    def resolve_entry_attrs(self, value: Any) -> Entry:
        if self.template is not None:
            template = ~self.template if self.negate else self.template
            expression = fill_q_template(template, value=value)
        else:
            lhs = self.get_db_field()
            if isinstance(lhs, (BaseExpression, Combinable)):
                alias = "_default_alias_%s" % self.get_param_name()
                if self.aliases is not None:
                    self.aliases[alias] = lhs
                else:
                    self.aliases = {alias: lhs}
                lhs = alias
            if self.lookup:
                lhs = f"{lhs}__{self.lookup}"
            expression = Q(**{lhs: value}, _negated=self.negate)
        return Entry(
            group=self.get_group(),
            aliases=self.aliases,
            value=value,
            expression=expression,
        )

    def resolve_entry(self, query_dict: QueryDict) -> Entry | None:
        try:
            value = self.parse_value(self.get_query_value(query_dict))
        except SkipField:
            return None
        if self.noop:
            return Entry(group=self.get_group(), value=value, expression=None)
        if self.method is not None:
            param = self.get_param_name()
            result = getattr(self.get_filterset(), self.method)(param, value)
            if isinstance(result, Entry):
                return result
            return Entry(group=self.get_group(), value=value, expression=result)
        return self.resolve_entry_attrs(value)

    def get_all_children(self) -> list[Filter]:
        children = []
        for child in self.children:
            children.append(child)
            children.extend(child.get_all_children())
        return children

    def resolve(
        self, query_dict: QueryDict
    ) -> tuple[dict[str, Entry | None], dict[str, Any]]:
        entries, errors = {}, {}
        for instance in [self, *self.get_all_children()]:
            if instance.namespace:
                continue
            param = instance.get_param_name()
            try:
                entry = instance.resolve_entry(query_dict)
            except ValidationError as err:
                errors[param] = err.detail
            else:
                entries[param] = entry
        return entries, errors
