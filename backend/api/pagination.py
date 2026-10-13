"""Opt-in pagination.

The platform has never paginated: `REST_FRAMEWORK` sets no `DEFAULT_PAGINATION_CLASS`, so every
list endpoint returns a bare JSON array and every frontend caller reads it as one. Setting a
global default — or even `pagination_class` on a single viewset — silently changes that shape to
`{count, next, previous, results}` and breaks every existing caller of that endpoint at once.
For approvals and clarifications alone that is seven call sites, two of them in the legacy
components.

So pagination is requested, not imposed: `paginate_queryset` returns `None` (DRF's "don't
paginate" signal) unless the request actually asks for a page. A caller that says nothing gets
exactly the bare array it got before, byte for byte; a caller that passes `?page=1` gets the
envelope and can walk `next`. That lets the history screens page through months of records
without touching a single existing caller.

When the whole app is ready to move, this becomes the global default and the opt-in check goes
away — but that is a migration with its own PR, not a side effect of adding a history tab.
"""
from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class OptInPageNumberPagination(PageNumberPagination):
    """Paginate only when the caller passes `?page=`. Otherwise behave as if unpaginated."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        if self.page_query_param not in request.query_params:
            return None          # DRF renders the plain list — the pre-existing contract
        return super().paginate_queryset(queryset, request, view=view)
