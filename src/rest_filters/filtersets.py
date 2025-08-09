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
from rest_framework.settings import api_settings
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
        """
        The following parameters can be used as class attributes in
        ``FilterSet.Meta``:

        :param fields: A subset of available query parameters that will be used
         in this FilterSet. Use this to disable certain query parameters.
        :param known_parameters: Overrides
         :py:attr:`rest_filters.conf.AppSettings.KNOWN_PARAMETERS`
        :param handle_unknown_parameters: Overrides
         :py:attr:`rest_filters.conf.AppSettings.HANDLE_UNKNOWN_PARAMETERS`
        :param constraints: A list of constraint instances that are going to be
         enforced for this FilterSet.
        :param combinators: A dictionary that contains the query combination
         operator for given groups. The default operator for groups is
         ``operator.and_``.
        :param blank: Overrides :py:attr:`rest_filters.conf.AppSettings.BLANK`
        """
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
        """Django REST framework ``Request`` object."""
        self.queryset = queryset
        self.view = view
        """View instance for this request."""

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
                "The following fields are not valid: %(fields)s,"
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
        if entry.expression is None:
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
        """
        Resolve Entry for the given group.

        :param group: Name of the group that is currently being resolved.
        :param entries: Query parameters belonging to this group, with their
         corresponding Entry.
        """
        combinator = self.options.combinators.get(group, operator.and_)
        expressions = [
            entry.expression
            for entry in entries.values()
            if entry.expression is not None
        ]
        if expressions:
            expression = functools.reduce(combinator, expressions)
        else:
            expression = None
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
        """
        Returns the final QuerySet object. At this point, all the filters are
        applied. Override this method to perform operations on QuerySet that
        are otherwise not possible, such as ``order_by()`` and ``distinct()``
        calls.

        :param queryset: Filtered QuerySet object.
        :param values: Parsed query parameters.
        """
        return queryset

    def get_fields(self) -> dict[str, Filter]:
        """
        Resolve filters that are going to be used in this FilterSet. You may
        override this method to dynamically add filters.

        .. danger::

            Make sure additional Filter instances are initialized inside this
            method, using global variables will lead to dangling references.
        """
        return self._fields

    def get_default(self, param: str, default: Any) -> Any:
        """
        Dynamically determine the default value for the given param.

        :param param: Parameter name.
        :param default: Default value that is otherwise going to be used.
        :return: Default value.
        """
        return default

    def get_serializer(self, param: str, serializer: AnyField | None) -> AnyField:
        """
        Dynamically resolve the serializer field for the given param.

        :param param: Parameter name.
        :param serializer: Serializer field that is otherwise going to be used.
        :return: Serializer field.
        """
        return serializer  # type: ignore[return-value]

    def get_serializer_context(self, param: str) -> dict[str, Any]:
        """
        Get serializer context for the given param. By default, this will use
        ``view.get_serializer_context()``. The context will also include this
        FilterSet instance.

        :param param: Parameter name.
        :return: Context dictionary.
        """
        context: dict[str, Any] = self.view.get_serializer_context()  # type: ignore[attr-defined]
        context["filterset"] = self
        return context

    def run_validation(
        self, value: str | _Empty, serializer: AnyField, param: str
    ) -> Any:
        """
        Run validation for the given param.

        :param value: Value provided by the user. This will be ``empty`` if the
         parameter is missing.
        :param serializer: Serializer field that is going to be used for
         validation.
        :param param: Parameter name.
        :return: Parsed query parameter value.
        """
        return serializer.run_validation(value)

    def get_constraints(self) -> Sequence[Constraint]:
        """
        Resolve constraint objects that are going to be used in this FilterSet.
        You may override this method to dynamically add constraints.

        .. danger::

            Make sure additional Constraint instances are initialized inside
            this method, using global variables will lead to dangling
            references.
        """
        return self._constraints

    def handle_constraints(self, valuedict: dict[str, Any]) -> dict[str, Any]:
        errors: dict[str, Any] = {}
        constraints = self.get_constraints()
        for constraint in constraints:
            constraint.filterset = self
            try:
                constraint.check(valuedict)
            except serializers.ValidationError as err:
                detail = err.detail
                if not isinstance(detail, dict):
                    detail = {api_settings.NON_FIELD_ERRORS_KEY: detail}
                merge_errors(errors, detail)
            finally:
                constraint.filterset = None
        return errors

    def handle_unknown_parameters(
        self, unknown: list[str], known: list[str]
    ) -> dict[str, Any]:
        """
        Creates error messages for unknown parameters.

        :param unknown: Unknown parameters the user supplied.
        :param known: Known parameters.
        :return: An error dictionary.
        """
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
        """
        Raises ``ValidationError`` for given errors. You may override this
        method to change the error format.
        """
        raise serializers.ValidationError(errordict)
