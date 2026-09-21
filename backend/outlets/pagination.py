from rest_framework.pagination import PageNumberPagination


class OutletPagination(PageNumberPagination):
    """Page size is capped and cannot be disabled by the client — this is
    the registry's "no bulk export" rule enforced at the API layer."""

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 200
