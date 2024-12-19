from __future__ import annotations

import functools
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
