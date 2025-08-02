Implementing a search filter
============================

A query parameter solely reserved for search functionality is common in
applications. Generally speaking, this filter will require us performing
lookups on multiple fields.

This can easily be achieved using the template parameter, here is an example:

.. code-block:: python

    class UserFilterSet(FilterSet[User]):
        search = Filter(
            serializers.CharField(required=False),
            template=Q("username__icontains")
            | Q("email__icontains")
            | Q("first_name__icontains")
            | Q("last_name__icontains"),
        )

Using the template parameter, we can create complex multi-field lookups with
ease. Notice that we did not specify values for Q objects, since their values
will be determined by the value of query parameter itself.

Now let's do something more involved: What if we allowed users to specify which
fields they want to perform search on? This way our search parameter would be
much flexible, allowing users to do lookups on specific fields.

To do this we would have to create an auxiliary query parameter called
``search.fields``, containing comma seperated field names. Here is a detailed
example:

.. code-block:: python

    from rest_filters.constraints import Dependency
    from rest_filters.fields import CSVField
    from rest_filters.filters import Entry
    from django.db.models import Q


    class UserFilterSet(FilterSet[User]):
        search = Filter(
            serializers.CharField(required=False),
            group="search",
            children=[
                Filter(
                    CSVField(
                        child=serializers.ChoiceField(
                            choices=[
                                "username",
                                "email",
                                "first_name",
                                "last_name",
                            ]
                        ),
                        required=False,
                    ),
                    param="fields",
                    noop=True,
                ),
            ],
        )

        def get_group_entry(self, group: str, entries: dict[str, Entry]) -> Entry:
            # 'entries' contain the resolved 'Entry' objects for each filter in
            # given 'group', if the param is not provided, it will not appear
            # in this dict. This method won't be called for groups that do not
            # appear at all in query parameters.
            if group == "search" and (search := entries.get("search")) is not None:
                value, fields = (
                    search.value,
                    ["username", "email", "first_name", "last_name"],
                )
                # If user provided this query parameter, use it instead.
                # Otherwise we will use all the available fields.
                if search_fields := entries.get("search.fields"):
                    fields = search_fields.value
                expr = Q()
                for name in fields:
                    expr |= Q(**{name: value})
                return Entry(group=group, value=value, expression=expr)
            return super().get_group_entry(group, entries)

        class Meta:
            constraints = [
                Dependency(
                    fields=["search.fields"],
                    depends_on=["search"],
                ),
            ]

In the example above, following is happening:

1. We created a filter which encapsulates search parameters. ``search.filter``
   being the child of ``search``.
2. We assigned a group named "search" to these filters so that they would fall
   into same group. This is that we can use ``get_group_entry`` method to
   capture them together.
3. We used a plain ``CharField`` for search term and combined ``CSVField`` with
   ``ChoiceField`` to simulate a multiple choice query parameter for search
   fields.
4. We marked ``search.fields`` with ``noop=True`` so that it would not try to
   resolve a query expression, this is because this field by itself does
   nothing and is going to be used as an "helper".
5. In ``get_group_entry`` we captured these fields' values and dynamically
   resolved the final query expression of the ``search`` group.
6. We added a dependency constraint so that specifying ``search.fields``
   without a search term would cause a ``ValidationError``, informing user
   about the requirement.

This example could further be extended to allow specifying lookups. For example
users could specify ``username`` for exact lookups and ``username.icontains``
for substring lookups. This is is left as an exercise for the reader.
