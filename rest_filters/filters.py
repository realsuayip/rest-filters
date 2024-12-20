from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from django.db.models import Q
from django.http.request import QueryDict

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import SkipField, empty

from rest_filters.utils import fill_q_template

if TYPE_CHECKING:
    from rest_filters.filtersets import FilterSet


class Entry:
    def __init__(
        self,
        *,
        group: str = "chain",
        aliases: dict[str, Any] | None = None,
        value: Any,
        expression: Any,
    ):
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


class Filter:
    def __init__(
        self,
        f: serializers.Field = None,
        /,
        *,
        field: str | None = None,
        lookup: str = "exact",
        template: Q | None = None,
        group: str | None = None,
        distinct: bool = False,
        negate: bool = False,
        method: str | None = None,
        aliases: dict[str, Any] | None = None,
        param: str | None = None,
        children: list[Filter] | None = None,
        namespace: bool = False,
        blank: Literal["keep", "omit"] = "omit",
    ) -> None:
        self._field = field
        self.lookup = lookup or "exact"
        self.template = template

        # todo needs tons of other checks
        if group is not None and not group.isidentifier():
            raise ValueError("Group names must be valid Python identifiers")

        if blank not in ("keep", "omit"):
            raise ValueError("blank must either be 'keep' or 'omit'")

        self._group = group
        self.aliases = aliases  # not functional

        self.negate = negate
        self.distinct = distinct  # not functional, todo allow list<str> also

        self.blank = blank
        self.method = method
        self._param = param
        self._serializer = f
        self._filterset: FilterSet | None = None

        self.namespace = namespace
        self.parent: Filter | None = None
        self.children = children or []
        for child in self.children:
            child.bind(self)

        if not self.children and self.namespace:
            raise ValueError("Namespace filters are required to have child filters")

    def __repr__(self) -> str:
        return "%s(param=%r, group=%r, serializer=%r)" % (
            self.__class__.__name__,
            self.get_param_name(),
            self.get_group(),
            self.get_serializer(),
        )

    def __set_name__(self, owner: FilterSet, name: str) -> None:
        self.name = name

    def bind(self, parent: Filter) -> None:
        self.parent = parent

        if self._param is None:
            raise ValueError("param needs to be set for child filters")

    def get_group(self) -> str:
        if self._group is not None:
            return self._group
        elif self.parent is not None:
            return self.parent.get_group()
        return "chain"

    def get_field_name(self):
        if self.parent and self._field is None:
            return self.parent.get_field_name()
        return self._field or self.name

    def get_param_name(self) -> str:
        name = self._param or self.name
        if self.parent is not None:
            namespace = self.parent.get_param_name()
            return f"{namespace}.{name}"
        return name

    def get_query_value(self, query_dict: QueryDict) -> str | empty:
        param = self.get_param_name()
        return query_dict.get(param, empty)

    def get_serializer(self) -> serializers.Field:
        if self._serializer is not None:
            return self._serializer
        elif self.parent is not None:
            return self.parent.get_serializer()
        raise ValueError("Serializer field is not set for this filter")

    def get_filterset(self) -> FilterSet:
        if self.parent:
            return self.parent.get_filterset()
        return self._filterset

    def parse_value(self, value: str | empty) -> Any:
        if value is not empty:
            value = serializers.CharField(allow_blank=True).run_validation(value)
            if self.blank == "omit" and value == "":
                value = empty
        filterset, param = self.get_filterset(), self.get_param_name()
        serializer = filterset.get_serializer(param) or self.get_serializer()
        serializer.default = filterset.get_default(param, serializer.default)
        return serializer.run_validation(value)

    def resolve_entry_attrs(self, value: Any) -> Entry:
        if self.template is not None:
            expression = fill_q_template(self.template, value=value)
        else:
            field = self.get_field_name()
            lookup = f"{field}__{self.lookup}"
            expression = Q(**{lookup: value})
        if self.negate:
            expression = ~expression
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
