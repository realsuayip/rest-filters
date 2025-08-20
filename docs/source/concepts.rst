.. _concepts:

Concepts
========

Filter
------

Filters represent your query parameters. They contain various metadata and may
additionally contain other filters in their namespace.

Ultimately, each filter resolves into a query expression that contributes to
the modification of the QuerySet object.

A Filter might be marked as ``noop`` which will disable its filtering behavior.
These filters can be used as helpers for other filters or can be used to alter
QuerySet for other purposes such as ordering.

Filter group
------------

Filter groups gather multiple filters together. This can be used to change
filtering behavior or create interactions between filters.

See: :ref:`using-groups`

Entry
-----

An Entry object represents the contribution of a Filter to the QuerySet. This
includes its query expression and annotations (if any). Each filter will
resolve into an Entry object.

Groups will also resolve into an Entry object, by combining multiple Entry
objects from their filters.

See: :ref:`entry-reference`

FilterSet
---------

A FilterSet contains the declarations of all your query parameters. You can
define and dynamically change the behavior and interactions between filters
using filtersets.

See :ref:`filterset-reference`
