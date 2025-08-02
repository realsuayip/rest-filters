Using Constraints
=================

Constraints allow you to establish relationships between your filters and
control how they interact with each other.

Constraints are created by subclassing ``rest_filters.constraints.Constraint``,
and can be provided as a list of constraint instances in the ``constraints``
attribute of the ``Meta`` class within the ``FilterSet``.

There are 4 built-in constraints:

``MutuallyExclusive``
---------------------

This constraint enforces mutual exclusivity between specified filters. This can
bu used to restrict the use of filters that does not make sense together.

For example:

.. code-block:: python

    from rest_filters.constraints import MutuallyExclusive

    constraints = [
        MutuallyExclusive(fields=["id", "search"]),
    ]

Won't allow specifying ``id`` and ``search`` query parameters at the same time.

``MutuallyInclusive``
---------------------

This constraint enforces mutual inclusivity between specified filters. This can
bu used to enforce the use certain filters together.

For example:

.. code-block:: python

    from rest_filters.constraints import MutuallyInclusive

    constraints = [
        MutuallyInclusive(fields=["start_date", "end_date"]),
    ]

Won't allow specifying ``start_date`` and ``end_date`` in isolation, they must
either appear at the same time or not appear at all.

``Dependency``
--------------

This constraint establishes dependencies between fields:

For example:

.. code-block::

    from rest_filters.constraints import Dependency

    constraints = [
        Dependency(
            fields=["search.fields"],
            depends_on=["search"],
        ),
    ]

In this example, using ``search.fields`` without ``search`` would lead to an
error. Notice that this behavior cannot be achieved using ``MutuallyInclusive``
since ``search`` can be used without having to specify ``search.fields``.

Each dependency can include multiple fields with multiple dependencies. Each
member of the ``fields`` will independently be dependent on fields in
``depends_on``.

``MethodConstraint``
--------------------

This constraint enables you to define a custom filtering condition directly
through a method on the FilterSet, without the need to implement a separate
constraint class. It's ideal for one-off, non-reusable constraints that apply
only to a specific FilterSet.

For example:

.. code-block:: python

    from rest_framework.fields import empty
    from rest_filters.constraints import MethodConstraint, MutuallyInclusive


    class RangeFilterSet(FilterSet):
        start_date = Filter(serializers.DateTimeField(required=False))
        end_date = Filter(serializers.DateTimeField(required=False))

        class Meta:
            constraints = [
                MutuallyInclusive(fields=["start_date", "end_date"]),
                MethodConstraint(
                    method="ensure_valid_date_range",
                    message="The date range cannot be greater than 90 days.",
                ),
            ]

        def ensure_valid_date_range(self, values: dict[str, Any]) -> bool:
            start, end = (
                values.get("start_date", empty),
                values.get("end_date", empty),
            )
            if (start is not empty) and (end is not empty):
                return end - start <= timedelta(days=90)
            return True

This example defines two fields for filtering by range, requires them both to
be present and enforces 90 day window for the filter.

While creating custom constraints, we need to keep some things in mind:

1. While doing lookups in ``values``, we should use dictionary ``get`` since
   missing fields won't be there.
2. If a field value cannot be parsed, it will be set to the ``empty`` sentinel.
   This is why the fallback to ``empty`` is used above. The presence of
   ``empty`` in any field ensures that a ``ValidationError`` will be raised,
   regardless of the outcome of constraint evaluation (you may or may not
   decide to add constraint error to the response body).

Creating a custom constraint
----------------------------

To create a custom constraint, you can subclass from
``rest_filters.constraints.Constraint``. You'll need to override the ``check``
method which raises ``ValidationError`` when the requirement fails.

Here is the range example above, created as custom constraint:

.. code-block:: python

    from rest_framework.fields import empty
    from rest_filters.constraints import Constraint


    class RangeConstraint(Constraint):
        def check(self, values: dict[str, Any]) -> bool:
            start, end = (
                values.get("start_date", empty),
                values.get("end_date", empty),
            )
            if (start is not empty) and (end is not empty):
                in_range = end - start <= timedelta(days=90)
                if not in_range:
                    raise serializers.ValidationError(
                        "The date range cannot be greater than 90 days."
                    )
