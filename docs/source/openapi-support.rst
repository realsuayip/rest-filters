OpenAPI Support
===============

``rest-filters`` can generate OpenAPI schema via ``drf-spectacular`` package.

Filters use their serializer field to resolve OpenAPI schema, so you may use
existing constructs (for example, ``extend_schema_field``) on them to customize
schema generation.

Otherwise, schema generation will mimic the serializer behavior, reflecting
changes in ``help_text`` or other parameters like ``min_length`` and
``max_length``.
