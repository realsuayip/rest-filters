Default values
==============

You can specify default values for filter fields, which can be used in the
absence of such query parameters.

Here is a simple usage:

.. code-block:: python

    class UserFilterSet(FilterSet):
        role = Filter(
            serializers.CharField(required=False, default="developer"),
        )

This filterset will only list users with developer role if no explicit role is
specified. Notice that ``required`` is set to ``False``. This is a common
occurrence with defaults.

.. important::

    If you are using ``blank="omit"`` (which is the default) blank values
    (e.g., ``?role=``) will be treated as not provided; this will make default
    value take over.

You can also use a callable for serializer default argument, this is useful if
you want something mutable as a default value.

You can also dynamically specify defaults, this is useful if you want to make
use of view and request objects. Here is an example:

.. code-block:: python

    class PostFilterSet(FilterSet):
        feed_type = Filter(
            serializers.CharField(required=False, default="all_posts"),
        )

        def get_default(self, param: str, default: Any) -> Any:
            user = self.request.user
            if param == "feed_type" and user.is_authenticated:
                return user.preferred_feed_type
            return super().get_default(param, default)

This example will adopt to the feed type users have selected and will default
to all posts for anonymous users.

.. danger::

    **Use carefully!**

    Defaults behave just as if users provided them. This might lead to
    confusing behavior for users if you are not careful. For example, you may
    violate a constraint via a default value and users might get an error for
    the filters they did not even provide.
