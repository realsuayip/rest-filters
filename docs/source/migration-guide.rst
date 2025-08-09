Migration Guide
===============

If you would like to switch from ``django-filter`` to ``rest-filters``, you can
incrementally migrate your code. Here is what you need to do:

If you port the entire FilterSet definition, you'll just need to change the
filter backend. This is suitable for simple FilterSet classes.

If you don't want to port your entire FilterSet, you can start writing your new
filters using ``rest-filters`` and use both libraries together. To do so:

- Your ``django-filter`` FilterSet must be specified using the
  ``filterset_class`` attribute.
- Your ``rest-filters`` FilterSet must be specified using the
  ``get_filterset_class`` method.
- Your view must have both filter backends.

Additionally, if you don't want to add known parameters from the
``django-filter`` FilterSet, you'll need to disable
:py:attr:`rest_filters.conf.AppSettings.HANDLE_UNKNOWN_PARAMETERS`.

Limitations
-----------

- ``rest-filters`` doesn't support generating filters from the model
  definition, so you'll need to declare these filters explicitly.
- ``rest-filters`` uses serializer fields to parse and validate query
  parameters. You may get slightly different behavior from ``django-filter``,
  which uses Django forms.
- ``rest-filters`` doesn't support HTML input.

It is highly recommended to have test coverage for your FilterSets before
migrating them.
