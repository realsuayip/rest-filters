Changelog
=========

0.8.0 (unreleased)
------------------

New features

- You can now allow multiple values for the same query parameter, or choose
  to use only the first or last value. Check :py:class:`~rest_filters.Multi`
  for available options. This can be configured per filter, in
  :doc:`FilterSet.Meta <reference/filterset-options>`, or globally with
  :py:attr:`MULTI <rest_filters.conf.AppSettings.MULTI>`.
- Added :py:class:`~rest_filters.fields.ListField` for parsing query parameters
  with :py:attr:`~rest_filters.Multi.ALLOW`.
- Added :py:class:`~rest_filters.fields.VerboseChoiceField`, which includes
  available choices in error messages.
- Added :py:class:`~rest_filters.fields.StrictBooleanField`, which only accepts
  ``true``, ``false`` or ``null`` (when ``allow_null=True``) as string values.
- You can now set a default value for :doc:`noop <reference/filterset-options>`
  for all filters in a FilterSet.
- Added :py:class:`~rest_filters.filtersets.base.BaseFilterSet` for using
  query parameter parsing and grouping without a QuerySet.
- Added :py:meth:`FilterSet.get_schema_operation_parameters <rest_filters.filtersets.base.BaseFilterSet.get_schema_operation_parameters>`
  to customize schema generation.

Changes

- The existing :py:attr:`BLANK <rest_filters.conf.AppSettings.BLANK>` setting
  now uses the new :py:class:`~rest_filters.Blank` enum.
- Filter serializer context no longer modifies the dictionary returned by
  ``view.get_serializer_context()``.
- Using DRF's ``ListField`` in a filter now emits a warning. Use
  :py:class:`~rest_filters.fields.ListField` instead.
- Changed the implementation of some internal functions to support multiple
  values: ``Filter.get_query_value`` and ``Filter.parse_value``.
- Improved type annotations.

This release contains a breaking change:

- Multiple values for the same query parameter are now disallowed by default.
  Previously, only the last value was used. Set ``multi`` to
  :py:attr:`~rest_filters.Multi.LAST` to keep the previous behavior. This
  setting is also available in :doc:`FilterSet.Meta <reference/filterset-options>`
  and globally with :py:attr:`MULTI <rest_filters.conf.AppSettings.MULTI>`.

`0.8.0 diff <https://github.com/realsuayip/rest-filters/compare/0.7.1...HEAD>`__.

0.7.1
-----

Changes

- User-defined ``get_filterset_class`` now propagate exceptions properly, instead of swallowing AttributeError.
- Improved some error messages and types for invalid states
- Confirmed support for Django 6.0, 6.1 and DRF versions 3.16 to 3.18.
- Confirmed support for Python 3.15

`0.7.1 diff <https://github.com/realsuayip/rest-filters/compare/0.7.0...0.7.1>`__.

0.7.0
-----

Changes

- ``rest_filters`` now avoids eagerly importing REST framework settings.
- In error messages, double quotes (for emphasis) have been replaced by single quotes to improve readability.
- Improved type annotations.

`0.7.0 diff <https://github.com/realsuayip/rest-filters/compare/0.6.1...0.7.0>`__.

0.6.1
-----

* Confirm Python 3.14 support
* Remove redundant checks in group name validation

`0.6.1 diff <https://github.com/realsuayip/rest-filters/compare/0.6.0...0.6.1>`__.

0.6.0
-----

New features

- You can now specify a default group for all filters in a ``FilterSet``,  this setting is also globally available.
- You can now create subgroups to build complex group relations. Check documentation on subgroups.
- Added ``FilterSet.get_combinator`` method to dynamically resolve combinators.

This release contains a breaking change:

- Creating ``Entry`` objects without specifying groups is no longer allowed.

`0.6.0 diff <https://github.com/realsuayip/rest-filters/compare/0.5.2...0.6.0>`__.
