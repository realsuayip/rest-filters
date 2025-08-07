Using child filters
===================

Child filters allow you to represent related filters in an organized manner.
They are especially useful when you are providing alternative lookups for your
filters or when representing nested data structures, such as foreign keys.

Every filter you define can have child filters with arbitrary depth. Child
filters will inherit certain behaviors from its parent:

- The serializer field will be inherited from parent.
- The database field will be inherited from parent.
- If a group is specified for parent, it will also be inherited, if no group is
  specified, each of the child filters and parent filter will be chained.

.. tip::

    Since child filters are generally related to their parents and siblings, it
    is recommended to group them together.

All of the above can be overridden by explicitly specifying the related filter
option.

Using child filters will create a *namespace* using the parent query parameter
as the prefix and using dot as separator, resulting in more structured query
parameters.

Here is an example filter that makes use of child filters:

.. code-block:: python

    created = Filter(
        serializers.DateField(required=False),
        children=[
            Filter(lookup="gte"),
            Filter(lookup="lte"),
        ],
    )

The example above will create 3 query parameters:

- ``created`` that filters results based on given exact date. For example,
  ``?created=2026-01-01``
- ``created.gte`` that filters results after some certain date. For example
  ``?created.gte=2026-01-01``
- ``created.lte`` that filters results before some certain date. For example
  ``?created.lte=2026-01-01``

Thanks to inherited attributes, we didn't have to write much. But let's make
these parameters a bit more readable by overriding child filters' names:

.. code-block:: python

    created = Filter(
        serializers.DateField(required=False),
        children=[
            Filter(param="after", lookup="gte"),
            Filter(param="before", lookup="lte"),
        ],
    )

Our query parameters now would be ``created``, ``created.after`` and
``created.before``

Sometimes, we would like to use child filters just to create a namespace, in
such cases the parent filter does not make sense. In this example, we may not
need filtering by exact date. Filters can be marked as being "namespace" filter
so that only their child filters are available:

.. code-block:: python

    created = Filter(
        serializers.DateField(required=False),
        namespace=True,
        children=[
            Filter(param="after", lookup="gte"),
            Filter(param="before", lookup="lte"),
        ],
    )

Now, only the ``created.after`` and ``created.before`` query parameters are
available. Notice that details regarding the inheritance did not change.
