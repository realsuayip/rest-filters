Introduction
============

.. toctree::
    :hidden:
    :maxdepth: 2
    :caption: User Guide

    self
    installation
    getting-started

.. toctree::
    :hidden:
    :maxdepth: 2
    :caption: Recipes

    recipes/using-constraints
    recipes/default-values
    recipes/using-child-filters
    recipes/using-groups

What is rest-filters?
=====================

rest-filers is an extension for Django REST Framework that parses query
parameters and constructs the corresponding ``QuerySet`` objects. It serves as
a replacement for the commonly used ``django-filter`` library.

Highlight features
------------------

``rest-filters`` is specifically designed to be used in a REST API context. You
can enforce strict constraints on your parameters, how they are provided and
how they interact with each other. Here are some highlight features:

- **Use serializer fields to parse query parameters.** Existing serializer
  fields used in request bodies can be reused directly, ensuring consistency in
  parsing logic and validation error messages. This approach also simplifies
  the implementation of custom fields by utilizing familiar serializer API.
- **Support for default values on filter fields is built-in and straightforward
  to use.** Defaults can be either static or dynamically computed at runtime.
  Unlike ``django-filter``, which omits this feature to align with Django forms
  behavior, rest-filers embraces it as a common and practical pattern in API
  design. For example, a date range filter can default to the last 90 days and
  enforce this constraint by limiting the selectable range.
- **Use filter groups to combine related query components (e.g., using logical
  operators such as OR, AND).** By default, ``django-filter`` chains all
  ``QuerySet`` filters using ``AND``, which may result in additional ``JOIN``
  statements, potentially leading to inefficient or unintended queries. Filter
  groups provide a flexible mechanism for expressing arbitrary boolean logic
  within filters, allowing for more precise query construction.
- **Utilize the constraint system to define and enforce rules between
  independent filters.** Built-in support is provided for common use cases such
  as mutual exclusivity and mutual inclusivity. Custom constraints can be
  implemented to enforce arbitrary validation logic across filters.
- **Define child filters to inherit behavior from parent filters, simplifying
  the creation of closely related filters.** For example, filters like
  ``created.gte``, ``created.lte``, or ``created.year`` can be implemented with
  minimal duplication. Child filters also allow traversing relationships via
  foreign keys, enabling expressions such as ``company.industry.name``. These
  capabilities can be combined to build robust and expressive filtering
  systems.
- **Use the serializer context and flexible API to dynamically modify filter
  behavior at runtime.** Filters can be added or removed based on conditions
  such as user permissions. Additionally, reusable filter fields can be
  implemented to encapsulate permission checks and other dynamic logic.
- **Annotations can be added directly to the** ``QuerySet`` **within the filter
  definition.** This enables the creation of filters based on simple
  annotations without the need to implement separate method-based filters.
- **By default, a** ``ValidationError`` **is raised when a user submits an
  unrecognized query parameter.** If closely matching parameter names are
  detected, the error message will provide suggestions to guide the user in a
  self-documenting manner. This behavior is configurable and can be disabled if
  desired.
- **Query parameter names can be customized freely.** You don't need to stick
  with Python identifiers.
