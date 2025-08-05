Getting started
===============

In the following mini-tutorial, we will learn how to make use of some
``rest-filters`` features.

To begin, we need a model to construct QuerySet objects from. Since the User
model is a common component in most applications, it will serve as our example
throughout this guide. Assume the following User model:

.. code-block:: python

    class Company(models.Model):
        name = models.CharField(max_length=100)
        address = models.CharField(max_length=100)

        created = models.DateTimeField(auto_now_add=True)


    class User(models.Model):
        username = models.CharField(max_length=50)

        first_name = models.CharField(max_length=50)
        last_name = models.CharField(max_length=50)

        company = models.ForeignKey(
            Company,
            on_delete=models.SET_NULL,
            null=True,
            blank=True,
            related_name="users",
        )
        following_companies = models.ManyToManyField(Company)

        created = models.DateTimeField(auto_now_add=True)

Setting filter backend
----------------------

Next, we are going to define our view. In this example, we are using a
``ViewSet`` to list users:

.. code-block:: python

    from rest_filters import FilterBackend


    class UserViewSet(ReadOnlyModelViewSet[User]):
        queryset = User.objects.all()
        serializer_class = UserSerializer

        filter_backends = [FilterBackend]

Notice that we need to include our filter backend in ``filter_backends``. As
usual, you can set this value globally in REST framework using
``DEFAULT_FILTER_BACKENDS`` setting, for example:

.. code-block:: python

    REST_FRAMEWORK = {
        "DEFAULT_FILTER_BACKENDS": ["rest_filters.FilterBackend"],
    }

Creating your FilterSet
-----------------------

Now we need to define our ``FilterSet`` class. To begin, we will create a
simple filterset that allows searching users by username:

.. code-block:: python

    from rest_filters import Filter, FilterSet
    from rest_framework import serializers


    class UserFilterSet(FilterSet[User]):
        username = Filter(serializers.CharField(min_length=2))

This filterset declaration implies a few things:

1. Since a field name is not specified, this filterset assumes ``username``
   field will be available during QuerySet filtering.
2. Since no explicit parameter name is given, the querying will be done using
   ``username`` via API endpoint.
3. Since only ``min_length`` argument is used, this field will be required and
   a ``ValidationError`` will be raised if users do not specify the query
   parameter. This is due to serializer field defaults, and can be changed by
   providing ``required=False``.

.. note::

    ``FilterSet[User]`` uses the model class as a type variable solely for
    typing purposes. It does not automatically generate filters or fields based
    on the model definition.

Using FilterSet in views
------------------------

Let's plug this FilterSet into our view. There are two ways to do this. The
first method is using ``filterset_class`` attribute, just like
``django-filter``:

.. code-block:: python

    class UserViewSet(ReadOnlyModelViewSet[User]):
        queryset = User.objects.all()
        serializer_class = UserSerializer

        filter_backends = [FilterBackend]
        filterset_class = UserFilterSet

This method is not suitable if you are using both ``django-filter`` and
``rest-filters`` at the same time. Since they will both resolve to the same
FilterSet class, one of them won't work.

The second method allows using both libraries together, this involves creating
a method called ``get_filterset_class`` like so:

.. code-block:: python

    class UserViewSet(ReadOnlyModelViewSet[User]):
        queryset = User.objects.all()
        serializer_class = UserSerializer

        filter_backends = [FilterBackend]

        def get_filterset_class(self) -> FilterSet:
            return UserFilterSet

This method is more preferable since it also allows dynamic dispatch of
FilterSets based on view actions, permissions, etc.

Navigating to our endpoint, we should be able to filter users by username. We
should also get some error messages if something goes wrong, for example:

.. code-block:: json
    :caption: ``GET /api/users/``

    {
        "username": [
            "This field is required."
        ]
    }

.. code-block:: json
    :caption: ``GET /api/users/?username=a``

    {
        "username": [
            "Ensure this field has at least 2 characters."
        ]
    }

.. code-block:: json
    :caption: ``GET /api/users/?usrname=hello``

    {
        "username": [
            "This field is required."
        ],
        "usrname": [
            "This query parameter does not exist. Did you mean \"username\"?"
        ]
    }

Using child filters
-------------------

Now, let’s implement a more advanced filter. Specifically, we want to search
users based on their companies, by both company ID and company name.

.. code-block:: python

    class UserFilterSet(FilterSet[User]):
        username = Filter(serializers.CharField(min_length=2, required=False))
        company = Filter(
            serializers.IntegerField(min_value=1, required=False),
            children=[
                Filter(
                    serializers.CharField(min_length=2, required=False),
                    lookup="name",
                ),
            ],
        )

Let's digest the ``company`` filter:

1. The root filter allows filtering by company ID using the company query
   parameter, e.g., ``company=1``.
2. The child filter enables filtering by company name using the
   ``company.name`` query parameter, e.g., ``company.name=google``. This is
   made possible by the ``lookup`` argument, which maps both the model field
   and the query parameter name.
3. Each filter field is marked with ``required=False``, making all filters
   optional.
4. Both parent and child filters use different serializer fields, since they
   require different types. However, fields for child filters might be omitted,
   in which case they will be inherited from the parent filter.

While this example is useful, the company filter may be unclear to users, as it
doesn't explicitly indicate what attribute is being filtered. To improve this,
we can use namespace filters:

.. code-block:: python

    company = Filter(
        namespace=True,
        children=[
            Filter(
                serializers.IntegerField(min_value=1, required=False),
                lookup="id",
            ),
            Filter(
                serializers.CharField(min_length=2, required=False),
                lookup="name",
            ),
        ],
    )

This filter exposes two parameters: ``company.id`` and ``company.name``.

Using constraints
-----------------

Depending on your API design, it might not be desirable to make these filters
available at the same time. We might force users to only provide ``id`` or
``name`` using a built-in constraint:

.. code-block:: python

    from rest_filters.constraints import MutuallyExclusive


    class UserFilterSet(FilterSet[User]):
        username = Filter(serializers.CharField(min_length=2, required=False))
        company = Filter(
            namespace=True,
            children=[
                Filter(
                    serializers.IntegerField(min_value=1, required=False),
                    lookup="id",
                ),
                Filter(
                    serializers.CharField(min_length=2, required=False),
                    lookup="name",
                ),
            ],
        )

        class Meta:
            constraints = [
                MutuallyExclusive(
                    fields=[
                        "company.id",
                        "company.name",
                    ]
                )
            ]

Notice that we used resolved query parameter names while supplying fields for
our constraint. This constraint will raise a ``ValidationError`` when both
fields are used at the same time:

.. code-block:: json
    :caption: GET /api/users/?company.id=1&company.name=google

     {
         "non_field_errors": [
             "Following fields are mutually exclusive, you may only provide one of them: \"company.id\", \"company.name\""
         ]
     }

Using Filter groups
-------------------

Up to now, all the filters we used chained ``filter()`` calls on QuerySets,
since we did not specify any groups. Let's see an example where using a group
would be useful:

.. code-block:: python

    following_companies = Filter(
        namespace=True,
        children=[
            Filter(
                serializers.CharField(required=False),
                lookup="name",
            ),
            Filter(
                serializers.CharField(required=False),
                lookup="address",
            ),
        ],
    )

This filter allows filtering on users, based on the information of companies
they follow. Since we did not specify any group, specifying both of these query
parameters will result in a query like this:

.. code-block:: sql

    SELECT *
      FROM "auth_user"
     INNER JOIN "auth_user_following_companies"
        ON ("auth_user"."id" = "auth_user_following_companies"."user_id")
     INNER JOIN "auth_company"
        ON ("auth_user_following_companies"."company_id" = "auth_company"."id")
     INNER JOIN "auth_user_following_companies" T4
        ON ("auth_user"."id" = T4."user_id")
     INNER JOIN "auth_company" T5
        ON (T4."company_id" = T5."id")
     WHERE ("auth_company"."name" = 'google' AND T5."address" = 'california')

Depending on your use case, this might not be desirable. To limit the joined
tables we can group these filters together, by providing ``group`` argument on
parent filter, from which both of them will inherit. We can also specify groups
per filter basis.

Doing this results in a query like this:

.. code-block:: sql

    SELECT *
      FROM "auth_user"
     INNER JOIN "auth_user_following_companies"
        ON ("auth_user"."id" = "auth_user_following_companies"."user_id")
     INNER JOIN "auth_company"
        ON ("auth_user_following_companies"."company_id" = "auth_company"."id")
     WHERE ("auth_company"."name" = 'google' AND "auth_company"."address" = 'california')

Final FilterSet definition
--------------------------

Here is the final ``FilterSet`` with some minor additions for reference:

.. code-block:: python

    class UserFilterSet(FilterSet[User]):
        username = Filter(serializers.CharField(min_length=2, required=False))
        company = Filter(
            namespace=True,
            children=[
                Filter(
                    serializers.IntegerField(min_value=1, required=False),
                    lookup="id",
                ),
                Filter(
                    serializers.CharField(min_length=2, required=False),
                    lookup="name",
                ),
                Filter(
                    serializers.DateTimeField(required=False),
                    param="created",
                    field="company__created",
                    namespace=True,
                    children=[
                        Filter(lookup="gte"),
                        Filter(lookup="lte"),
                        Filter(
                            serializers.IntegerField(
                                min_value=1900,
                                max_value=2050,
                                required=False,
                            ),
                            lookup="year",
                        ),
                    ],
                ),
            ],
        )
        following_companies = Filter(
            namespace=True,
            group="following_companies_group",
            children=[
                Filter(
                    serializers.CharField(required=False),
                    lookup="name",
                ),
                Filter(
                    serializers.CharField(required=False),
                    param="address",
                    lookup="address__icontains",
                ),
            ],
        )
        created = Filter(
            serializers.DateTimeField(required=False),
            namespace=True,
            children=[
                Filter(lookup="gte"),
                Filter(lookup="lte"),
            ],
        )

        class Meta:
            constraints = [
                MutuallyExclusive(
                    fields=[
                        "company.id",
                        "company.name",
                    ]
                )
            ]
