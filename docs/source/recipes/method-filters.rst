Method filters
==============

Sometimes your filtering logic cannot be expressed in simple expressions, or
you may need to use request information to do some stuff.

.. important::

    If you need to annotate an expression to your query just to be used in
    filtering context, you do not need to use methods. You can specify
    ``field`` or ``aliases`` for your filter. For example:

    Lookup on full name, which is a combination of first and last name:

    .. code-block:: python

        from rest_filters import Filter

        from django.db.models import F, Value
        from django.db.models.functions import Concat

        full_name = Filter(
            serializers.CharField(),
            field=Concat(
                F("first_name"),
                Value(" "),
                F("last_name"),
            ),
            lookup="icontains",
        )

    Search in full name and username at the same time:

    .. code-block:: python

        from django.db.models import F, Value, Q
        from django.db.models.functions import Concat

        search = Filter(
            serializers.CharField(),
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

    from rest_filters import FilterSet
    from django.db.models import Q
    from rest_filters.fields import VerboseChoiceField


    class RepositoryFilterSet(FilterSet[Repository]):
        scope = Filter(
            VerboseChoiceField(
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

- You need to dynamically change the resolved group.
- You need to specify some aliases.
- You need to change the value to something else. This might rarely be useful
  for constraints, since they work on resolved values. Similarly
  ``FilterSet.get_queryset`` method will receive updated values.

Returning ``None`` will not resolve a query expression, so no filtering will be
done, mimicking the ``noop=True`` behavior. By default, methods are **not
called** when the relevant query parameter is missing (and no default value
is supplied).

.. note::

    QuerySet is not available in methods, and you should not attempt to modify
    it. If you need to modify QuerySets based on query parameter values, you
    can later use ``get_queryset`` method on FilterSet instead.

Here is another example:

.. code-block:: python

    from django.db.models import Exists, OuterRef, Count, Q
    from rest_filters.fields import StrictBooleanField
    from rest_filters.filters import Entry


    class RepositoryFilterSet(FilterSet[Repository]):
        is_starred = Filter(
            StrictBooleanField(),
            method="filter_by_is_starred",
        )
        needs_misuse_review = Filter(
            StrictBooleanField(),
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
                group="chain",
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

.. _always-method-filters:

Running methods for missing parameters
--------------------------------------

Wrap a method name with :py:class:`~rest_filters.always` to also call it when
an optional parameter has no value. The method receives
:py:data:`~rest_filters.utils.missing` in that case. This lets you provide a default
expression without defining a default serializer value:

.. code-block:: python

    from django.db.models import Q

    from rest_filters import Filter, FilterSet, always
    from rest_filters.fields import CSVField
    from rest_filters.utils import Missing, missing


    class ProjectFilterSet(FilterSet):
        tenant_id = Filter(
            CSVField(child=serializers.IntegerField(min_value=1)),
            method=always("filter_tenant_id"),
        )

        def filter_tenant_id(self, param: str, value: list[int] | Missing) -> Q:
            # By default, include projects from all authorized tenants.
            # If IDs are supplied, narrow the results to those tenants.
            tenant_ids = self.request.user.authorized_tenants
            if value is not missing:
                tenant_ids = [tenant_id for tenant_id in tenant_ids if tenant_id in value]
            return Q(tenant_id__in=tenant_ids)

Defaults and validation still apply. The method receives ``missing`` only when
no value or default is available.

.. note::

    When using ``always()``, missing parameters remain absent from the values
    passed to constraints and ``get_queryset()``. Return an ``Entry`` with a
    resolved value to include them.
