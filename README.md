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
    username = Filter(serializers.CharField(min_length=2), lookup="icontains")
    company = Filter(
        namespace=True,
        children=[
            Filter(
                serializers.IntegerField(min_value=1),
                lookup="id",
            ),
            Filter(
                serializers.CharField(min_length=2),
                lookup="name__icontains",
                param="name",
            ),
        ],
    )
    created = Filter(
        serializers.DateTimeField(),
        namespace=True,
        children=[
            Filter(lookup="gte"),
            Filter(lookup="lte"),
        ],
    )
```

## License

Copyright (c) 2025, Şuayip Üzülmez

All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
