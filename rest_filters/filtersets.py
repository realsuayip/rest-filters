from __future__ import annotations

import copy
import functools
import itertools
import operator
from collections import defaultdict
from collections.abc import Sequence
from difflib import get_close_matches
from typing import TYPE_CHECKING, Any, Generic

from django.db.models import QuerySet
from django.utils.translation import gettext

from rest_framework import serializers
from rest_framework.fields import empty
from rest_framework.request import Request
from rest_framework.views import APIView

from rest_filters.constraints import Constraint
from rest_filters.filters import Entry, Filter
from rest_filters.utils import AnyField, NotSet, _MT_co, merge_errors, notset

if TYPE_CHECKING:
    from rest_framework.fields import _Empty


class Options:
    def __init__(
        self,
        *,
        fields: Sequence[str] | NotSet,
        known_parameters: Sequence[str] | NotSet,
        constraints: Sequence[Constraint] | NotSet,
        combinators: dict[str, Any] | NotSet,
    ) -> None:
        if isinstance(known_parameters, NotSet):
            known_parameters = []
        if isinstance(constraints, NotSet):
            constraints = []
        if isinstance(combinators, NotSet):
            combinators = {}

        self.fields = fields
        self.known_parameters = known_parameters
        self.constraints = constraints
        self.combinators = combinators


class FilterSet(Generic[_MT_co]):
    options: Options
    compiled_fields: dict[str, Filter]

    def __init__(
        self,
        request: Request,
        queryset: QuerySet[_MT_co],
        view: APIView,
    ) -> None:
        self.request = request
        self.queryset = queryset
        self.view = view

        self.fields = copy.deepcopy(self.compiled_fields)
        self.constraints = copy.deepcopy(self.options.constraints)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        meta_fields = (
            "fields",
            "constraints",
            "combinators",
            "known_parameters",
        )
        if meta := getattr(cls, "Meta", None):
            opts = {field: getattr(meta, field, notset) for field in meta_fields}
            options = Options(**opts)
        else:
            opts = {field: notset for field in meta_fields}
            options = Options(**opts)
        cls.options = options
        cls.compiled_fields = cls._compile_fields()

    @classmethod
    def _visit(
        cls, fields: Sequence[str], f: Filter
    ) -> tuple[list[str], Filter | None]:
        param = f.get_param_name()
        keep = param in fields
        if not f.children:
            if keep:
                return [param], f
            return [param], None
        visits = [cls._visit(fields, child) for child in f.children]
        p, c = zip(*visits, strict=True)
        params, children = (
            list(itertools.chain.from_iterable(p)),
            [child for child in c if child is not None],
        )
        if children:
            f.children = children
            if not keep:
                f.namespace = True
        elif keep:
            f.children = []
        else:
            return params, None
        params.append(param)
        return params, f

    @classmethod
    def _compile_fields(cls) -> dict[str, Filter]:
        fields = {
            name: field
            for name, field in vars(cls).items()
            if isinstance(field, Filter)
        }
        if isinstance(cls.options.fields, NotSet):
            return fields
        ret, available = {}, []
        for name, field in fields.items():
            params, f = cls._visit(cls.options.fields, field)
            available.extend(params)
            if f is not None:
                ret[name] = f
        unknown = [field for field in cls.options.fields if field not in available]
        if unknown:
            raise ValueError(
                "Following fields are not valid: %(fields)s,"
                " available fields: %(available)s"
                % {
                    "fields": ", ".join((repr(item) for item in unknown)),
                    "available": ", ".join(repr(item) for item in available),
                }
            )
        return ret

    def get_groups(self) -> tuple[dict[str, dict[str, Entry]], dict[str, Any]]:
        params = self.request.query_params
        fields = self.get_fields()
        groupdict: dict[str, dict[str, Entry]]
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
        if errordict:
            self.handle_errors(errordict)
        return groupdict, valuedict

    def add_to_queryset(
        self, queryset: QuerySet[_MT_co], entry: Entry
    ) -> QuerySet[_MT_co]:
        if entry.aliases:
            queryset = queryset.alias(**entry.aliases)
        return queryset.filter(entry.expression)

    def filter_group(
        self,
        queryset: QuerySet[_MT_co],
        name: str,
        entries: dict[str, Entry],
    ) -> QuerySet[_MT_co]:
        merge = getattr(self, f"merge_{name}", None)
        if merge is not None:
            entry = merge(entries)
            return self.add_to_queryset(queryset, entry)
        return self.add_to_queryset(
            queryset,
            self.get_default_group_expression(name, entries),
        )

    def get_default_group_expression(
        self, group: str, entries: dict[str, Entry]
    ) -> Any:
        combinator = self.options.combinators.get(group, operator.and_)
        expressions = (entry.expression for entry in entries.values())
        return functools.reduce(combinator, expressions)

    def filter_queryset(self) -> QuerySet[_MT_co]:
        queryset = self.queryset
        groupdict, valuedict = self.get_groups()

        for entry in groupdict.pop("chain", {}).values():
            queryset = self.add_to_queryset(queryset, entry)

        for name, entries in groupdict.items():
            queryset = self.filter_group(queryset, name, entries)
        return self.get_queryset(queryset, valuedict)

    def get_queryset(
        self,
        queryset: QuerySet[_MT_co],
        values: dict[str, Any],
    ) -> QuerySet[_MT_co]:
        return queryset

    def get_fields(self) -> dict[str, Filter]:
        return self.fields

    def get_default(self, param: str, default: Any) -> Any:
        return default

    def get_serializer(
        self, param: str, serializer: AnyField | None
    ) -> AnyField | None:
        return serializer

    def get_serializer_context(self, param: str) -> dict[str, Any]:
        context: dict[str, Any] = self.view.get_serializer_context()  # type: ignore[attr-defined]
        context["filterset"] = self
        return context

    def run_validation(
        self, value: str | _Empty, serializer: AnyField, param: str
    ) -> Any:
        return serializer.run_validation(value)

    def get_constraints(self) -> Sequence[Constraint]:
        return self.constraints

    def handle_constraints(self, valuedict: dict[str, Any]) -> dict[str, Any]:
        errors: dict[str, Any] = {}
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
