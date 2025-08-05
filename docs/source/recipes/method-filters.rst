Method filters
==============

Sometimes your filtering logic cannot be expressed in simple expressions or you
may need to use request information to do some stuff.

.. important::

    If you need to annotate an expression to your query just to be used in
    filtering context, you do not need to use methods. You can specify
    ``field`` or ``aliases`` for your filter. For example:

    Lookup on full name, which is a combination of first and last name:

    .. code-block:: python

        full_name = Filter(
            serializers.CharField(required=False),
            field=Concat(
                F("first_name"),
                Value(" "),
                F("last_name"),
            ),
            lookup="icontains",
        )

    Search in full name and username at the same time:

    .. code-block:: python

        search = Filter(
            serializers.CharField(required=False),
            aliases={
                "full_name": Concat(
                    F("first_name"),
                    Value(" "),
                    F("last_name"),
                ),
            },
            template=Q("full_name__icontains") | Q("username__icontains"),
        )

In such cases, you can dynamically resolve query expressions for your filters
by specifying a method. This method needs to be defined in your FilterSet
class. Here is an example:

.. code-block:: python

    class RepositoryFilterSet(FilterSet[Repository]):
        scope = Filter(
            serializers.ChoiceField(
                choices=["user", "organization"],
            ),
            method="filter_by_scope",
        )

        def filter_by_scope(self, param: str, value: str) -> Q:
            if value == "organization":
                return Q(organization_id=self.request.user.organization_id)
            return Q(author=self.request.user)

In this example, users can request to see repositories their organization owns
or repositories they have created themselves. Since both of these require
accessing the user instance, we need to use a method filter.

User defined methods must define ``param`` and ``value`` parameters. ``param``
specifies the query parameter that is currently making use of that method. This
can be useful for code reuse if you assign one method to multiple query
parameters. ``value`` will be the parsed query parameter value.

The return value of the method can either be a query expression such as ``Q``,
``Exists``, ``Case`` etc., an ``Entry`` object or ``None``. You may choose to
return an ``Entry`` in following cases:

- You need to dynamically change the resolved group. Notice that returning an
  ``Entry`` object **without specifying group will force filter chaining**,
  regardless of filter definition.
- You need to specify some aliases.
- You need to change the value to something else. This might rarely be useful
  for constraints, since they work on resolved values. Similarly
  ``FilterSet.get_queryset`` method will receive updated values.

Returning ``None`` will not resolve a query expression, so no filtering will be
done, mimicking the ``noop=True`` behavior. Methods are **not called** when the
relevant query parameter is missing.

.. note::

    QuerySet is not available in methods, and you should not attempt to modify
    it. If you need to modify QuerySets based on query parameter values, you
    can later use ``get_queryset`` method on FilterSet instead.

Here is an another example:

.. code-block:: python

    class RepositoryFilter(FilterSet[Repository]):
        is_starred = Filter(
            serializers.BooleanField(required=False),
            method="filter_by_is_starred",
        )
        needs_misuse_review = Filter(
            serializers.BooleanField(required=False),
            method="filter_by_needs_misuse_review",
        )

        def filter_by_is_starred(self, param: str, value: bool) -> Exists | None:
            expr = Exists(
                RepositoryStar.objects.filter(
                    user=self.request.user,
                    repository=OuterRef("pk"),
                )
            )
            return expr if value else ~expr

        def filter_by_needs_misuse_review(self, param: str, value: bool) -> Entry | None:
            if not self.request.user.is_staff:
                raise serializers.ValidationError(
                    "You do not have appropriate permissions to use this query parameter."
                )
            expr = Q(flag_count__gte=20)
            return Entry(
                aliases={
                    "flag_count": Count("flags"),
                },
                value=value,
                expression=expr if value else ~expr,
            )

In this example ``is_starred`` parameter makes use of ``Exists`` expression,
while ``needs_misuse_review`` parameter uses a method to do permission checks
while also returning an ``Entry`` object to add aliases, forcing ``GROUP BY``
and ``HAVING`` clauses on the SQL query.
