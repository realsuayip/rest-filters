Ordering filters
================

``rest-filters`` does not *natively* support ordering query parameters. This is
because filtering and ordering are separate concerns. However, ``rest-filters``
makes it quite easy to modify QuerySets with query parameters, even if you are
not filtering thanks to the ``noop`` directive.

.. note::

    You can still use ``OrderingFilter`` provided by Django REST framework
    alongside ``rest-filters`` if the solutions below are not to your taste.

.. note::

    You can use methods described here to also handle ``distinct()`` calls to
    your QuerySet, since distinct is not supported in filters.

Here is an implementation of a typical ordering field:

.. code-block:: python

    class UserFilterSet(FilterSet[User]):
        ordering = Filter(
            CSVField(
                child=serializers.ChoiceField(
                    choices=[
                        "id",
                        "-id",
                        "created",
                        "-created",
                    ],
                ),
                default=["-id"],
            ),
            noop=True,
        )

        def get_queryset(
            self,
            queryset: QuerySet[User],
            values: dict[str, Any],
        ) -> QuerySet[User]:
            queryset = super().get_queryset(queryset, values)
            return queryset.order_by(*values["ordering"])

In this example:

1. We defined a ``CSVField`` with ``ChoiceField`` as the child, containing the
   possible ordering values. This will allow specifying multiple ordering
   fields while validating choices.
2. We set a default value as fallback in case users don't specify ordering.
3. We marked ordering as ``noop=True`` since it won't affect the filtering of
   the QuerySet.
4. We used ``get_queryset`` method to apply the ordering preference. Notice
   that ``values["ordering"]`` assumes value always being there, which is
   guaranteed by the ``default`` fallback.

While this style of ordering is very common in Django apps, it is a bit cryptic
and hard to read at a glance. Instead we could opt for something more verbose,
for example:

.. code-block:: python

    ORDERING_REGEX = re.compile(
        r"^(?P<value>[a-zA-Z_][a-zA-Z0-9_]*)"
        r"(:(?P<direction>asc|desc))?"
        r"(:(?P<nulls>nulls_last|nulls_first))?$"
    )


    class OrderingField(serializers.CharField):
        def to_internal_value(self, data):
            value = super().to_internal_value(data)
            if match := ORDERING_REGEX.match(value):
                groupdict = match.groupdict()
                if groupdict["value"] in ["id", "created"]:
                    return groupdict
            raise serializers.ValidationError("Not a valid ordering parameter.")


    class UserFilterSet(FilterSet[User]):
        ordering = Filter(
            CSVField(
                child=OrderingField(),
                default=[{"value": "id", "direction": "desc"}],
            ),
            noop=True,
        )

        def get_queryset(
            self,
            queryset: QuerySet[User],
            values: dict[str, Any],
        ) -> QuerySet[User]:
            queryset = super().get_queryset(queryset, values)
            order_by = []
            for order in values["ordering"]:
                f = F(order["value"])
                direction = order.get("direction")
                kwargs = {}
                if nulls := order.get("nulls"):
                    kwargs[nulls] = True
                if direction == "desc":
                    f = f.desc(**kwargs)
                else:
                    f = f.asc(**kwargs)
                order_by.append(f)
            return queryset.order_by(*order_by)

In this example:

1. We created a custom field, which parses query parameters in the format of
   ``field_name:asc|desc:nulls_first|nulls_last``. This allows specifying
   fields with explicit ordering direction (asc or desc) and an option to
   specify how to deal with null values.
2. We used ``CSVField`` to accept multiple of these fields so that we can
   specify multiple ordering expressions.
3. In ``get_queryset`` we constructed relevant ``F()`` object from parsed parts
   to do the actual ordering.

This FilterSet will allow ordering in these styles:

- ``?ordering=created``
- ``?ordering=created:desc``
- ``?ordering=created:desc:nulls_first``
- ``?ordering=created:desc:nulls_first,id``
- ``?ordering=created:desc:nulls_first,id:desc:nulls_last``

After implementing ordering style of your choice, you may choose to create a
base class for it. You may then use this base in your future FilterSets for
consistent ordering experience.
