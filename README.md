# rest-filters

[![PyPI version](https://badge.fury.io/py/rest-filters.svg)](https://badge.fury.io/py/rest-filters)

rest-filters is an extension for Django REST Framework that parses query
parameters and constructs the corresponding `QuerySet` objects.

See full documentation at: https://rest-filters.readthedocs.io/

## Installation

Use your favorite Python package manager to install rest-filters:

```
pip install rest-filters
```

rest-filters supports Django 4.2 and Django 5.2, with REST framework 3.14 and
above.

rest-filters uses semantic versioning: https://semver.org

## A basic example

Here is a basic FilterSet declaration that allows filtering users by username,
company, and creation date.

Check
out [getting started guide](https://rest-filters.readthedocs.io/en/latest/getting-started.html)
for more details.

```python
from rest_filters import Filter, FilterSet
from rest_framework import serializers


class UserFilterSet(FilterSet[User]):
    username = Filter(
        serializers.CharField(min_length=2, required=False),
        lookup="icontains",
    )
    company = Filter(
        namespace=True,
        children=[
            Filter(
                serializers.IntegerField(min_value=1, required=False),
                lookup="id",
            ),
            Filter(
                serializers.CharField(min_length=2, required=False),
                lookup="name__icontains",
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
```
