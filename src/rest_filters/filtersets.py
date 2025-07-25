from __future__ import annotations

import copy
import functools
import itertools
import operator
from collections import defaultdict
from collections.abc import Sequence
from difflib import get_close_matches
from typing import TYPE_CHECKING, Any, Generic, Literal, final

from django.db.models import QuerySet
from django.utils.translation import gettext

from rest_framework import serializers
from rest_framework.fields import empty
from rest_framework.request import Request
from rest_framework.views import APIView

from rest_filters.conf import app_settings
from rest_filters.constraints import Constraint
from rest_filters.filters import Entry, Filter
from rest_filters.utils import AnyField, NotSet, _MT_co, merge_errors, notset

if TYPE_CHECKING:
    from rest_framework.fields import _Empty


@final
class Options:
    __slots__ = (
        "_blank",
        "_extend_known_parameters",
        "_handle_unknown_parameters",
        "_known_parameters",
        "combinators",
        "constraints",
        "fields",
    )

    def __init__(
        self,
        *,
        fields: list[str] | tuple[str] | NotSet = notset,
        known_parameters: list[str] | tuple[str] | NotSet = notset,
        extend_known_parameters: list[str] | tuple[str] | NotSet = notset,
        handle_unknown_parameters: bool | NotSet = notset,
        constraints: Sequence[Constraint] | NotSet = notset,
        combinators: dict[str, Any] | NotSet = notset,
        blank: Literal["keep", "omit"] | NotSet = notset,
    ) -> None:
        self._known_parameters = known_parameters
        self._extend_known_parameters = extend_known_parameters
        self._handle_unknown_parameters = handle_unknown_parameters
        self._blank = blank

        if constraints is notset:
            constraints = []
        if combinators is notset:
            combinators = {}

        self.fields = fields
        self.constraints = constraints
        self.combinators = combinators

    @property
    def known_parameters(self) -> tuple[str] | list[str]:
        params = self._known_parameters
        if params is notset:
            params = app_settings.KNOWN_PARAMETERS
        if self._extend_known_parameters is not notset:
            params = (*params, *self._extend_known_parameters)
        return params

    @property
    def handle_unknown_parameters(self) -> bool:
        if self._handle_unknown_parameters is notset:
            return app_settings.HANDLE_UNKNOWN_PARAMETERS
        return self._handle_unknown_parameters

    @property
    def blank(self) -> Literal["keep", "omit"]:
        if self._blank is notset:
            return app_settings.BLANK
        return self._blank


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

        self._fields = copy.deepcopy(self.compiled_fields)
        self._constraints = copy.deepcopy(self.options.constraints)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        meta_fields = (
            "fields",
            "constraints",
            "combinators",
            "known_parameters",
            "extend_known_parameters",
            "handle_unknown_parameters",
            "blank",
        )
        if meta := getattr(cls, "Meta", None):
            opts = {field: getattr(meta, field, notset) for field in meta_fields}
            options = Options(**opts)
        else:
            options = Options()
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

    def get_groups(self) -> tuple[dict[str, dict[str, Entry]], dict[str, Any]]:
        params = self.request.query_params
        fields = self.get_fields()
        groupdict: dict[str, dict[str, Entry]]
        groupdict, valuedict, errordict = defaultdict(dict), {}, {}
        known = [*self.options.known_parameters]
        for _, field in fields.items():
            try:
                field._filterset = self
                entries, errors = field.resolve(params)
            finally:
                field._filterset = None
            known.extend((*entries, *errors))
            for param, entry in entries.items():
                if entry is not None:
                    groupdict[entry.group][param] = entry
                    valuedict[param] = entry.value
            for param, error in errors.items():
                errordict[param] = error
                valuedict[param] = empty
        merge_errors(errordict, self.handle_constraints(valuedict))
        if self.options.handle_unknown_parameters:
            unknown = [field for field in params if field not in known]
            if unknown:
                merge_errors(errordict, self.handle_unknown_parameters(unknown, known))
        if errordict:
            self.handle_errors(errordict)
        return dict(groupdict), valuedict

    def add_to_queryset(
        self, queryset: QuerySet[_MT_co], entry: Entry
    ) -> QuerySet[_MT_co]:
        if entry.expression is notset:
            return queryset
        if entry.aliases:
            queryset = queryset.alias(**entry.aliases)
        return queryset.filter(entry.expression)

    def filter_group(
        self,
        queryset: QuerySet[_MT_co],
        group: str,
        entries: dict[str, Entry],
    ) -> QuerySet[_MT_co]:
        return self.add_to_queryset(queryset, self.get_group_entry(group, entries))

    def get_group_entry(self, group: str, entries: dict[str, Entry]) -> Entry:
        combinator = self.options.combinators.get(group, operator.and_)
        expressions = [
            entry.expression
            for entry in entries.values()
            if entry.expression is not notset
        ]
        if expressions:
            expression = functools.reduce(combinator, expressions)
        else:
            expression = notset
        return Entry(
            group=group,
            aliases=functools.reduce(
                operator.or_,
                (
                    entry.aliases
                    for entry in entries.values()
                    if entry.aliases is not None
                ),
                {},
            )
            or None,
            value={name: entry.value for name, entry in entries.items()},
            expression=expression,
        )

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
        return self._fields

    def get_default(self, param: str, default: Any) -> Any:
        return default

    def get_serializer(self, param: str, serializer: AnyField | None) -> AnyField:
        return serializer  # type: ignore[return-value]

    def get_serializer_context(self, param: str) -> dict[str, Any]:
        context: dict[str, Any] = self.view.get_serializer_context()  # type: ignore[attr-defined]
        context["filterset"] = self
        return context

    def run_validation(
        self, value: str | _Empty, serializer: AnyField, param: str
    ) -> Any:
        return serializer.run_validation(value)

    def get_constraints(self) -> Sequence[Constraint]:
        return self._constraints

    def handle_constraints(self, valuedict: dict[str, Any]) -> dict[str, Any]:
        errors: dict[str, Any] = {}
        constraints = self.get_constraints()
        for constraint in constraints:
            constraint.filterset = self
            try:
                if not constraint.check(valuedict):
                    message = constraint.get_message(valuedict)
                    merge_errors(errors, message)
            finally:
                constraint.filterset = None
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
                        'This query parameter does not exist. Did you mean "%(param)s"?'
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
