from __future__ import annotations

import copy
import functools
import itertools
import operator
from collections import defaultdict
from collections.abc import Sequence
from difflib import get_close_matches
from typing import Any, Generic, TypeVar

from django.db import models
from django.db.models import QuerySet
from django.utils.translation import gettext

from rest_framework import serializers
from rest_framework.fields import empty
from rest_framework.request import Request
from rest_framework.views import APIView

from rest_filters.constraints import Constraint
from rest_filters.filters import Entry, Filter
from rest_filters.utils import merge_errors

_MT_co = TypeVar("_MT_co", bound=models.Model, covariant=True)
notset = object()


class Options:
    def __init__(
        self,
        *,
        fields: Sequence[str],
        known_parameters: Sequence[str],
        constraints: Sequence[Constraint],
        combinators: dict[str, Any],
    ) -> None:
        if known_parameters is notset:
            known_parameters = []
        if constraints is notset:
            constraints = []
        if combinators is notset:
            combinators = {}

        self.fields = fields
        self.known_parameters = known_parameters
        self.constraints = constraints
        self.combinators = combinators


class FilterSet(Generic[_MT_co]):
    options: Options
    compiled_fields: dict[str, Filter]

    def __init__(
        self, request: Request, queryset: QuerySet[_MT_co], view: APIView
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
        params, children = zip(
            *[cls._visit(fields, child) for child in f.children],
            strict=True,
        )
        params, children = (
            list(itertools.chain.from_iterable(params)),
            [child for child in children if child is not None],
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
        if cls.options.fields is notset:
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

    def get_fields(self) -> dict[str, Filter]:
        return self.fields

    def get_default(self, param: str, default: Any) -> Any:
        return default

    def get_serializer(self, param: str) -> serializers.Field | None:
        return None

    def get_constraints(self) -> Sequence[Constraint]:
        return self.constraints

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
