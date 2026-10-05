Introduction
============

.. toctree::
    :hidden:
    :maxdepth: 2
    :caption: User Guide

    self
    installation
    getting-started
    concepts
    openapi-support
    migration-guide

.. toctree::
    :hidden:
    :maxdepth: 2
    :caption: Recipes

    recipes/default-values
    recipes/using-constraints
    recipes/using-child-filters
    recipes/using-groups
    recipes/search-filters
    recipes/method-filters
    recipes/ordering-filters
    recipes/using-subgroups

.. toctree::
    :hidden:
    :maxdepth: 2
    :caption: Reference

    reference/settings
    reference/filterset-options
    reference/filter-reference
    reference/field-reference
    reference/filterset-reference
    reference/entry-reference

What is rest-filters?
=====================

rest-filters is an extension for Django REST Framework that parses query
parameters and constructs the corresponding ``QuerySet`` objects. It serves as
a replacement for the commonly used ``django-filter`` library.

Key features
------------

``rest-filters`` is specifically designed to be used in a REST API context. You
can enforce strict constraints on your parameters, how they are parsed and
how they interact with each other. Here are some key features:

- **Use serializer fields to parse query parameters.** You can reuse the same
  fields you use in request bodies, so parsing and error messages stay
  consistent.
- **Set default values for filters.** Defaults can be a fixed value or
  computed at runtime.
- **Use filter groups.** Group related filters and combine them with ``AND``,
  ``OR``, or your own logic.
- **Set constraints between filters.** Built-in constraints include mutual
  exclusivity and mutual inclusivity. You can also write custom constraints.
- **Use child filters.** Related filters can inherit from a parent. For example,
  ``created.gte``, ``created.lte``, or ``created.year``. Child filters can
  also follow foreign keys, such as ``company.industry.name``.
- **Change filter behavior at runtime.** Filters and FilterSets can use
  serializer context. Allowing you, for example, to create permission-based
  filters.
- **Control your QuerySet.** You can add complex QuerySet annotations
  in the filter definition, without having to write a custom method. You
  can opt-out from QuerySet chaining behavior.
- **Get verbose error messages.** Errors are raised when unrecognized query
  parameters are used or multiple query parameters with the same name are
  provided. All error messages related to filters, constraints, and unknown
  parameters are propagated properly. All error behavior and messages can be
  customized.
- **Customize query parameter names freely.** You don't need to stick
  with Python identifiers.
