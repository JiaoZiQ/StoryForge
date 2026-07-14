"""Small mapping helpers shared by application services."""

from math import ceil

from storyforge.repositories import PageSlice
from storyforge.schemas.api import PageMeta, PageResponse


def page_response[SourceT, TargetT](
    page_slice: PageSlice[SourceT],
    *,
    page: int,
    page_size: int,
    items: list[TargetT],
) -> PageResponse[TargetT]:
    """Create consistent page metadata from a database-backed slice."""
    return PageResponse(
        items=items,
        meta=PageMeta(
            page=page,
            page_size=page_size,
            total_items=page_slice.total_items,
            total_pages=ceil(page_slice.total_items / page_size) if page_slice.total_items else 0,
        ),
    )
