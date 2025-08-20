Using subgroups
===============

Subgroups offer a powerful way to control relationships between filters and
groups. With properly assigned subgroups, you can control the logical operator
between each resolved query expression, whether it is created by a group or by
a single query parameter.

.. warning::

    Subgroups are a relatively advanced (and niche) feature. Make sure you
    understand the :ref:`concepts` and familiarize yourself with the
    :ref:`filterset-reference` before using them.

    Before using subgroups, you should also try solving the problem at hand
    using groups. Groups can resolve fairly complex queries using APIs like
    ``get_combinator`` and ``get_group_entry``. See: :ref:`using-groups`

To create a subgroup, you need to choose a namespace which will contain your
groups. For example:

.. code-block:: python

    class UserFilterSet(FilterSet[User]):
        city = Filter(serializers.CharField(), group="user.location")

This filter defines a group named ``user.location`` and a namespace called
``user``. However, this is not particularly useful yet, since there is only one
subgroup assigned to that namespace. Let's add another subgroup and additional
filters:

.. code-block:: python

    class UserFilterSet(FilterSet[User]):
        city = Filter(serializers.CharField(), group="user.location")
        country = Filter(serializers.CharField(), group="user.location")

        website = Filter(serializers.CharField(), group="user.contact")
        email = Filter(serializers.CharField(), group="user.contact")

In this example we have the following:

- A group namespace called ``user``
- A group named ``user.location``, subgroup of ``user``
- A group named ``user.contact``, subgroup of ``user``

Now, with this setup, we would like to perform the following request:

.. code-block::

    ?city=New
    &country=USA
    &website=alan
    &email=alan

and achieve a query equivalent to:

.. code-block:: python

    (Q(city="New") | Q(country="USA")) & (Q(website="alan") | Q(email="alan"))
    #              ^ user.location     ^ @user              ^ user.contact

This can be done by specifying combinators in the Meta class like so:

.. code-block:: python

    import operator


    class Meta:
        combinators = {
            "user.location": operator.or_,
            "user.contact": operator.or_,
        }

Nice. But we could have done this using different group names anyway. No need
for subgroups, right? Not quite; using different group names would have created
the following query instead:

.. code-block:: python

    User.objects.filter((Q(city="New") | Q(country="USA"))).filter(
        (Q(website="alan") | Q(email="alan"))
    )

This is slightly different, as you may remember from :ref:`using-groups`. Also,
we have something more useful here: we can now control the operator between
different groups. For example:

.. code-block:: python

    class Meta:
        combinators = {
            "@user": operator.or_,
            # Not specifying other groups so they use
            # the default, which is AND.
        }

Resulting in:

.. code-block:: python

    (Q(city="New") & Q(country="USA")) | (Q(website="alan") & Q(email="alan"))
    #              ^ user.location     ^ @user              ^ user.contact

Notice that we used ``@`` prefix to reference the combinator between subgroups
of that namespace. If we used ``user`` instead of ``@user``, that would refer
to a concrete group called ``user`` which is non-existent in this example.

.. note::

    You can also use namespaces as group names, however this is not recommended
    since it might lead to confusion.

Now, let's get spicy. In the following example, we give all the control to our
users, so they will decide which group gets which combinator:

.. code-block:: python

    class UserFilterSet(FilterSet[User]):
        location = Filter(
            serializers.CharField(),
            namespace=True,
            group="user.location",
            children=[
                Filter(param="city", field="city"),
                Filter(param="country", field="country"),
                Filter(
                    serializers.ChoiceField(choices=["and", "or"]),
                    param="combine",
                    noop=True,
                ),
            ],
        )
        contact = Filter(
            serializers.CharField(),
            namespace=True,
            group="user.contact",
            children=[
                Filter(param="email", field="email"),
                Filter(param="website", field="website"),
                Filter(
                    serializers.ChoiceField(choices=["and", "or"]),
                    param="combine",
                    noop=True,
                ),
            ],
        )
        combine = Filter(
            serializers.ChoiceField(choices=["and", "or"]),
            group="user.meta",
            param="combine",
            noop=True,
        )

        def get_combinator(
            self, group: str, entries: dict[str, Entry]
        ) -> Callable[..., Any]:
            lookups = {"and": operator.and_, "or": operator.or_}
            if group in ("user.contact", "user.location"):
                name = group.split(".")[-1]  # e.g., "contact", "location"
                if combine := entries.get(f"{name}.combine"):
                    return lookups[combine.value]
            if group == "@user":
                # At this point, '@user' is trying to combine 3 groups,
                # 'user.contact', 'user.location', and 'user.meta'

                # Did the user specify any filters from the 'user.meta' group?
                if meta := entries.get("user.meta"):
                    # ^ meta.value is dict, containing query parameters and their
                    # parsed values for the 'user.meta' group.
                    lookup = meta.value["combine"]
                    # ^ No need to use .get(), since only 1 filter exists in the
                    # 'user.meta' group; we can count on its existence.
                    return lookups[lookup]
            return super().get_combinator(group, entries)

The example above allows queries such as:

- ``location.city=New&location.country=USA&location.combine=and``
- ``location.city=New&contact.email=alan&combine=or``
- ``location.city=New&contact.email=alan&contact.website=alan&contact.combine=or&combine=or``

As demonstrated in this example, the following methods receive group names and
namespaces, indicated by a leading ``@``:

- :py:meth:`rest_filters.filtersets.FilterSet.get_combinator`
- :py:meth:`rest_filters.filtersets.FilterSet.get_group_entry`

.. important::

    Namespaces can have arbitrary depth. For example, a group specifier
    ``user.contact.private`` will create 2 namespaces: ``user`` and
    ``user.contact``. Similarly, you'll be able to resolve ``@user.contact``;
    this capability allows for building arbitrary query expressions.
