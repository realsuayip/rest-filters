.. _using-groups:

Using groups
============

Filter groups offer a way to represent alternative Django QuerySet filtering
mechanisms. Consider the condition ``color=red`` AND ``shape=triangle`` for a
QuerySet. This can be written in the following ways:

The first way is combining these two conditions in one expression by either
using ``Q`` objects or QuerySet keyword arguments:

.. code-block:: python

    Geometry.objects.filter(color="red", shape="triangle")

To achieve the same result in our context, we would need to define a custom
"group".

The alternative way is to chain filter calls for each condition:

.. code-block:: python

    Geometry.objects.filter(color="red").filter(shape="triangle")

The above example is the default behavior if no group is specified. To be
specific, a default, reserved group called "chain" is supplied for you, which
chains each expression. The default group can be changed on a per-Filterset
basis via meta options or globally.

Ultimately, both of these queries will find Geometry objects that are **red
triangles**. However, when filtering on fields with multi-valued relationships,
such as ManyToManyFields or reverse foreign keys, the behavior changes.

For example, let's assume a ``Scene`` object, which contains many geometries.
We would like to find scenes which contain red triangles. To do so, we would
have to write:

.. code-block:: python

    Scene.objects.filter(geometries__color="red", geometries__shape="triangle")

In this case, chaining each of the conditions would not fulfill our request
since doing so would return scene objects that contain either "red geometries"
or "triangles of any color".

Depending on your context, you might or might not want to chain queries. By
specifying groups, you opt out from chaining QuerySets (the default behavior).

Here is an example FilterSet that makes use of groups:

.. code-block:: python

    class SceneFilterSet(FilterSet[Scene]):
        geometry_color = Filter(
            serializers.CharField(),
            group="geometry",
            field="geometries__color",
        )
        geometry_shape = Filter(
            serializers.CharField(),
            group="geometry",
            field="geometries__shape",
        )

Groups are specified using a user-defined string that uniquely identifies the
group. Groups can be specified regardless of the filter context. For example,
child filters can share groups with unrelated filters.

.. tip::

    Child filters inherit the group of their parent for convenience, however
    for some use cases it might be desirable to disable that. You can specify
    the reserved "chain" value for a group to force chained filtering.

Advanced usage
--------------

Groups can also be used to control the boolean logic between specified filters.
For example, the example above uses:

.. code-block::

    color=red AND shape=triangle

but we might as well do:

.. code-block::

    color=red OR shape=triangle

By default, each expression in a group will be combined with ``AND``. This can
be changed using ``Meta.combinators`` option. For example:

.. code-block:: python

    import operator


    class FilterSet(FilterSet[Geometry]):
        color = Filter(serializers.CharField(), group="obj_props")
        shape = Filter(serializers.CharField(), group="obj_props")

        class Meta:
            combinators = {"obj_props": operator.or_}

You can go even further beyond, by overriding ``get_group_entry`` method in
your FilterSet, which will provide you with each of the filter expressions for
given group. You may then arbitrarily combine them with whatever logic you have
in mind.

In the next section, we will use this functionality to implement an advanced
search filter.
