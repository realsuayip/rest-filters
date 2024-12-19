from __future__ import annotations

import functools
import operator
from collections import defaultdict
from collections.abc import Sequence
from difflib import get_close_matches
from typing import Any, Generic, Literal, TypeVar

from django.db import models
from django.db.models import Q, QuerySet
from django.http.request import QueryDict
from django.utils.translation import gettext

from rest_framework import filters, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import SkipField, empty
from rest_framework.request import Request
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from rest_filters.utils import fill_q_template, merge_errors

_MT_co = TypeVar("_MT_co", bound=models.Model, covariant=True)

StrOrPromise = str


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


class Constraint:
    def __init__(
        self,
        *,
        fields: Sequence[str],
        message: StrOrPromise = "",
        method: str | None = None,
    ) -> None:
        self.fields = fields
        self.message = message
        self.method = method
        self.filterset: FilterSet | None = None

    def get_message(self, **kwargs: Any) -> dict[str, Any]:
        message = self.message or gettext(
            "%(constraint)s failed for fields: %(fields)s"
        ) % {
            "constraint": self.__class__.__name__,
            "fields": ", ".join(f'"{field}"' for field in self.fields),
        }
        return {api_settings.NON_FIELD_ERRORS_KEY: [message]}

    def check(self, **kwargs: Any) -> bool:
        assert self.method, "Missing method for constraint"
        assert self.filterset, "Missing filterset for constraint"
        return getattr(self.filterset, self.method)(**kwargs)


class MutuallyExclusive(Constraint):
    def __init__(
        self,
        *,
        fields: Sequence[str],
        **kwargs: Any,
    ) -> None:
        assert len(fields) > 1, "Provide 2 or more fields for this constraint"
        super().__init__(fields=fields, **kwargs)

    def get_message(self, **kwargs: Any) -> dict[str, Any]:
        if self.message:
            return super().get_message(**kwargs)
        return {
            api_settings.NON_FIELD_ERRORS_KEY: [
                gettext(
                    "Following fields are mutually exclusive,"
                    " you may only provide one of them: %(fields)s"
                )
                % {
                    "fields": ", ".join(
                        f'"{field}"' for field in self.fields if field in kwargs
                    )
                }
            ]
        }

    def check(self, **kwargs: Any) -> bool:
        return sum(field in kwargs for field in self.fields) <= 1


class MutuallyInclusive(Constraint):
    def __init__(
        self,
        *,
        fields: Sequence[str],
        **kwargs: Any,
    ) -> None:
        assert len(fields) > 1, "Provide 2 or more fields for this constraint"
        super().__init__(fields=fields, **kwargs)

    def get_message(self, **kwargs: Any) -> dict[str, Any]:
        if self.message:
            return super().get_message(**kwargs)
        return {
            api_settings.NON_FIELD_ERRORS_KEY: [
                gettext(
                    "Following fields are mutually inclusive,"
                    " you must provide them all at once or none of them: %(fields)s"
                )
                % {"fields": ", ".join(f'"{field}"' for field in self.fields)}
            ]
        }

    def check(self, **kwargs: Any) -> bool:
        fields = [field in kwargs for field in self.fields]
        return all(fields) if any(fields) else True


class Options:
    def __init__(
        self,
        *,
        fields: Sequence[str] | None = None,
        known_parameters: Sequence[str] | None = None,
        constraints: Sequence[Constraint] | None = None,
        combinators: dict[str, Any] | None = None,
    ) -> None:
        self.fields = fields  # todo not functional
        self.known_parameters = known_parameters or []
        self.constraints = constraints or []
        self.combinators = combinators or {}


class FilterSet(Generic[_MT_co]):
    def __init__(
        self, request: Request, queryset: QuerySet[_MT_co], view: APIView
    ) -> None:
        self.request = request
        self.queryset = queryset
        self.view = view
        self.options = self.get_options()

    def get_options(self) -> Options:
        if meta := getattr(self, "Meta", None):
            args = ("fields", "known_parameters", "constraints", "combinators")
            return Options(**{arg: getattr(meta, arg, None) for arg in args})
        return Options()

    def get_groups(self) -> dict[str, dict[str, Entry]]:
        params = self.request.query_params
        fields = self.get_fields()
        groupdict, valuedict, errordict = defaultdict(dict), {}, {}
        known = [*self.options.known_parameters]
        for _, field in fields.items():
            field._filterset = self
            entries, errors = field.resolve(params)
            known.extend((*entries, *errors))
            for param, entry in entries.items():
                if entry is not None:
                    groupdict[entry.group][param] = entry
                    valuedict[param] = entry.value
            for param, error in errors.items():
                errordict[param] = error
                valuedict[param] = empty
        unknown = [field for field in params if field not in known]
        merge_errors(errordict, self.handle_constraints(valuedict))
        errordict |= self.handle_unknown_parameters(unknown, known)
        self.handle_errors(errordict)
        return groupdict

    def filter_group(
        self,
        queryset: QuerySet[_MT_co],
        name: str,
        entries: dict[str, Entry],
    ) -> QuerySet[_MT_co]:
        merge = getattr(self, f"merge_{name}", None)
        if merge is not None:
            entry = merge(entries)
            return queryset.filter(entry.expression)
        return queryset.filter(self.get_default_group_expression(name, entries))

    def get_default_group_expression(
        self, group: str, entries: dict[str, Entry]
    ) -> Any:
        combinator = self.options.combinators.get(group, operator.and_)
        expressions = (entry.expression for entry in entries.values())
        return functools.reduce(combinator, expressions)

    def get_queryset(self) -> QuerySet[_MT_co]:
        queryset = self.queryset
        groupdict = self.get_groups()

        for entry in groupdict.pop("chain", {}).values():
            queryset = queryset.filter(entry.expression)

        for name, entries in groupdict.items():
            queryset = self.filter_group(queryset, name, entries)
        return queryset

    @classmethod
    def get_fields(cls) -> dict[str, Filter]:
        return {
            name: attr for name, attr in vars(cls).items() if isinstance(attr, Filter)
        }

    def get_default(self, param: str, default: Any) -> Any:
        return default

    def get_serializer(self, param: str) -> serializers.Field | None:
        return None

    def get_constraints(self) -> Sequence[Constraint]:
        return self.options.constraints

    def handle_constraints(self, valuedict: dict[str, Any]) -> dict[str, Any]:
        errors = {}
        constraints = self.get_constraints()
        for constraint in constraints:
            constraint.filterset = self
            if not constraint.check(**valuedict):
                message = constraint.get_message(**valuedict)
                merge_errors(errors, message)
        return errors

    def handle_unknown_parameters(
        self, unknown: list[str], known: list[str]
    ) -> dict[str, Any]:
        fields = {}
        for param in unknown:
            matches = get_close_matches(param, known)
            if not matches:
                fields[param] = [gettext("This query parameter does not exist.")]
            elif len(matches) == 1:
                fields[param] = [
                    gettext(
                        "This query parameter does not exist."
                        ' Did you mean "%(param)s"?'
                    )
                    % {"param": matches[0]}
                ]
            else:
                possibilities = ", ".join(f'"{match}"' for match in matches)
                fields[param] = [
                    gettext(
                        "This query parameter does not exist."
                        " Did you mean one of these: %(possibilities)s?"
                    )
                    % {"possibilities": possibilities}
                ]
        return fields

    def handle_errors(self, errordict: dict[str, Any]) -> None:
        raise serializers.ValidationError(errordict)


class FilterBackend(filters.BaseFilterBackend):
    def get_filterset_class(self, request, queryset, view):
        # todo def get_filterset_class
        return view.filterset_classes.get(view.action)

    def get_filterset(self, request, queryset, view):
        klass = self.get_filterset_class(request, queryset, view)
        return klass(request, queryset, view)

    def filter_queryset(self, request, queryset, view):
        filterset = self.get_filterset(request, queryset, view)
        return filterset.get_queryset()
