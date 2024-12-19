from rest_framework import filters

__all__ = [
    "FilterBackend",
]


class FilterBackend(filters.BaseFilterBackend):
    def get_filterset_class(self, request, queryset, view):
        # todo def get_filterset_class
        return view.filterset_classes.get(view.action)

    def get_filterset(self, request, queryset, view):
        klass = self.get_filterset_class(request, queryset, view)
        return klass(request, queryset, view)

    def filter_queryset(self, request, queryset, view):
        filterset = self.get_filterset(request, queryset, view)
        return filterset.get_queryset()
