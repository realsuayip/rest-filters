from __future__ import annotations

import copy
import functools
import itertools
import operator
from collections import defaultdict
from difflib import get_close_matches
from typing import TYPE_CHECKING, Any, TypeAlias, final

from django.utils.translation import gettext

from rest_framework import serializers
from rest_framework.fields import empty
from rest_framework.settings import api_settings

from rest_filters.conf import Blank, app_settings
from rest_filters.filters import Entry, Filter
from rest_filters.utils import (
    AnyField,
    NotSet,
    _get_filterset_schema,
    merge_errors,
    notset,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from django.http import QueryDict

    from rest_framework.views import APIView

    from rest_filters.conf import Multi
    from rest_filters.constraints import Constraint
    from rest_filters.utils import ParsedValue

__all__ = [
    "BaseFilterSet",
]

Entries: TypeAlias = dict[str, Entry]
Groups: TypeAlias = dict[str, Entries]


OPTION_NAMES = (
    "fields",
    "constraints",
    "combinators",
    "default_group",
    "known_parameters",
    "extend_known_parameters",
    "handle_unknown_parameters",
    "blank",
    "multi",
    "noop",
)


@final
class Options:
    __slots__ = (
        "_blank",
        "_default_group",
        "_extend_known_parameters",
        "_handle_unknown_parameters",
        "_known_parameters",
        "_multi",
        "combinators",
        "constraints",
        "fields",
        "noop",
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
        blank: Blank | NotSet = notset,
        multi: Multi | NotSet = notset,
        default_group: str | NotSet = notset,
        noop: bool | NotSet = notset,
    ) -> None:
        """
        The following parameters can be used as class attributes in
        ``FilterSet.Meta``:

        :param fields: A subset of available query parameters that will be used
         in this FilterSet. Use this to disable certain query parameters.
        :param known_parameters: Overrides
         :py:attr:`rest_filters.conf.AppSettings.KNOWN_PARAMETERS`
        :param extend_known_parameters: Extends
         :py:attr:`rest_filters.conf.AppSettings.KNOWN_PARAMETERS`
        :param handle_unknown_parameters: Overrides
         :py:attr:`rest_filters.conf.AppSettings.HANDLE_UNKNOWN_PARAMETERS`
        :param constraints: A list of constraint instances that are going to be
         enforced for this FilterSet.
        :param combinators: A dictionary that contains the query combination
         operator for given groups. The default operator for groups is
         ``operator.and_``.
        :param blank: Overrides :py:attr:`rest_filters.conf.AppSettings.BLANK`
        :param multi: Overrides :py:attr:`rest_filters.conf.AppSettings.MULTI`
        :param default_group:
         Overrides :py:attr:`rest_filters.conf.AppSettings.DEFAULT_GROUP`
        :param noop:
         Default value for the ``noop`` parameter for this FilterSet.
         Set this to ``True`` to disable filtering behavior while keeping
         validation.
        """
        self._known_parameters = known_parameters
        self._extend_known_parameters = extend_known_parameters
        self._handle_unknown_parameters = handle_unknown_parameters
        self._blank = blank
        self._multi = multi
        self._default_group = default_group

        if constraints is notset:
            constraints = []
        if combinators is notset:
            combinators = {}
        if noop is notset:
            noop = False

        self.fields = fields
        self.constraints = constraints
        self.combinators = combinators
        self.noop = noop

    @property
    def known_parameters(self) -> list[str]:
        params = self._known_parameters
        if params is notset:
            params = app_settings.KNOWN_PARAMETERS
        if self._extend_known_parameters is not notset:
            params = (*params, *self._extend_known_parameters)
        return list(params)

    @property
    def handle_unknown_parameters(self) -> bool:
        if self._handle_unknown_parameters is notset:
            return app_settings.HANDLE_UNKNOWN_PARAMETERS
        return self._handle_unknown_parameters

    @property
    def blank(self) -> Blank:
        if self._blank is notset:
            return app_settings.BLANK
        return self._blank

    @property
    def multi(self) -> Multi:
        if self._multi is notset:
            return app_settings.MULTI
        return self._multi

    @property
    def default_group(self) -> str:
        if self._default_group is notset:
            return app_settings.DEFAULT_GROUP
        return self._default_group


class BaseFilterSet:
    options: Options
    compiled_fields: dict[str, Filter]

    def __init__(self) -> None:
        self._fields = copy.deepcopy(self.compiled_fields)
        self._constraints = copy.deepcopy(self.options.constraints)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # https://github.com/python/cpython/issues/114326
        super().__init_subclass__()

        if meta := getattr(cls, "Meta", None):
            opts = {field: getattr(meta, field, notset) for field in OPTION_NAMES}
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
                    "fields": ", ".join(repr(item) for item in unknown),
                    "available": ", ".join(repr(item) for item in available),
                }
            )
        return ret

    def get_groups(self) -> tuple[Groups, dict[str, Any]]:
        params, fields, known_parameters = (
            self.get_query_params(),
            self.get_fields(),
            self.get_known_parameters(),
        )
        groupdict: Groups
        groupdict, valuedict, errordict = defaultdict(dict), {}, {}
        for field in fields.values():
            try:
                field._filterset = self
                entries, errors = field.resolve(params)
            finally:
                field._filterset = None
            known_parameters.extend((*entries, *errors))
            for param, entry in entries.items():
                if entry is not None:
                    groupdict[entry.group][param] = entry
                    valuedict[param] = entry.value
            for param, error in errors.items():
                errordict[param] = error
                valuedict[param] = empty
        merge_errors(errordict, self.handle_constraints(valuedict))
        if self.options.handle_unknown_parameters:
            unknown = [field for field in params if field not in known_parameters]
            if unknown:
                merge_errors(
                    errordict, self.handle_unknown_parameters(unknown, known_parameters)
                )
        if errordict:
            self.handle_errors(errordict)
        return dict(groupdict), valuedict

    def _resolve_group_namespace(
        self,
        root: str,
        groups: Groups,
    ) -> Entry:
        children, ns = {}, []
        for name, entries in groups.items():
            if not name.startswith(root):
                continue
            namespace, *sub = name.split(".")
            if sub:
                namespace += "." + sub[0]
            if namespace == root:
                children[name] = self.get_group_entry(name, entries)
                continue
            ns.append(namespace)
        for child in list(dict.fromkeys(ns)):
            children[child] = self._resolve_group_namespace(child, groups)
        if len(children) == 1:
            return next(iter(children.values()))
        return self.get_group_entry(f"@{root}", children)

    def get_combinator(self, group: str, entries: Entries) -> Callable[..., Any]:
        """
        Resolve the logical operator for the given group.

        :param group: Name of the group that is currently being resolved.
        :param entries: Query parameters belonging to this group, with their
         corresponding Entry.
        :return: A callable that acts like a logical operator,
         such as ``operator.or_`` and ``operator.and_``
        """
        return self.options.combinators.get(group, operator.and_)  # type: ignore[no-any-return]

    def get_group_entry(self, group: str, entries: Entries) -> Entry:
        """
        Resolve Entry for the given group.

        :param group: Name of the group that is currently being resolved.
        :param entries: Query parameters belonging to this group, with their
         corresponding Entry.
        """
        combinator = self.get_combinator(group, entries)
        expressions = [
            entry.expression
            for entry in entries.values()
            if entry.expression is not None
        ]
        expression = functools.reduce(combinator, expressions) if expressions else None
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

    def get_query_params(self) -> QueryDict:
        """
        Override this method in your subclasses to provide query params. The
        return value must be a ``django.http.QueryDict`` instance.

        See :py:attr:`rest_filters.FilterSet` for example implementation.
        """
        raise NotImplementedError

    def get_known_parameters(self) -> list[str]:
        """
        Override this method extend or replace known parameters dynamically.
        """
        return self.options.known_parameters

    def get_fields(self) -> dict[str, Filter]:
        """
        Resolve filters that are going to be used in this FilterSet. You may
        override this method to dynamically add or remove filters.

        .. danger::

            Make sure additional Filter instances are initialized inside this
            method (or deepcopied). Using global variables will lead to
            stale references. For example:

            .. code-block:: python

                def get_fields(self) -> dict[str, Filter]:
                    fields = super().get_fields()
                    fields["new_field"] = Filter(
                        serializers.IntegerField(),
                    )
                    return fields

            Notice that this is useful if you want to *hide* those additional
            filters. For example if you have some internal filter that is only
            enabled for certain IP's.

            If you need to change the behavior of a public filter during
            runtime, you should instead use method filters, or field serializer
            context.
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
        return {"filterset": self}

    def run_validation(
        self, value: ParsedValue, serializer: AnyField, param: str
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
            this method, using global variables will lead to stale
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
                        "This query parameter does not exist. Did you mean '%(param)s'?"
                    )
                    % {"param": matches[0]}
                ]
            else:
                possibilities = ", ".join(f"'{match}'" for match in matches)
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

    @classmethod
    def get_schema_operation_parameters(cls, view: APIView) -> list[dict[str, Any]]:
        """
        Returns OpenAPI parameters for this FilterSet. You may override this
        method to customize schema generation.

        :param view: View instance used for schema generation.
        :return: A list of parameter definitions.
        """
        return _get_filterset_schema(filterset=cls, view=view)
