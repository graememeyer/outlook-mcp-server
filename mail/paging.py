"""
Paginated message retrieval.

Graph caps a single response at ``$top`` items and hands back an
``@odata.nextLink`` for the remainder. The previous implementation issued one
request and stopped, which silently made ``$top`` a hard ceiling on the whole
mailbox. Everything here exists to walk that chain instead.
"""

import asyncio
from typing import Any, List, Optional

from kiota_abstractions.base_request_configuration import RequestConfiguration
from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (
    MessagesRequestBuilder,
)

from config import MAX_PAGES
from logger import logger


def _page_builder(client, next_link: str) -> MessagesRequestBuilder:
    """Build a request builder aimed at a raw ``@odata.nextLink`` URL.

    Kiota request builders accept either a path-parameter dict or a fully
    formed URL as their third argument, which is how a nextLink is followed.
    The link already encodes $top/$select/$filter/$skiptoken, so no query
    parameters are re-applied on top of it.
    """
    return MessagesRequestBuilder(client.request_adapter, next_link)


async def fetch_messages(
    client,
    folder_id: str,
    query_params: Any,
    *,
    limit: int,
    max_pages: int = MAX_PAGES,
    progress_every: Optional[int] = None,
) -> List[Any]:
    """Fetch up to ``limit`` messages, following nextLink as needed.

    ``query_params`` is applied to the first request only. Returns the
    accumulated message models, truncated to ``limit``.
    """
    messages: List[Any] = []
    next_link: Optional[str] = None
    pages = 0

    while pages < max_pages and len(messages) < limit:
        if next_link:
            result = await _page_builder(client, next_link).get()
        else:
            result = await client.me.mail_folders.by_mail_folder_id(folder_id).messages.get(
                request_configuration=RequestConfiguration(query_parameters=query_params)
            )

        pages += 1
        if not result or not result.value:
            break

        messages.extend(result.value)

        if progress_every and len(messages) % progress_every < len(result.value):
            logger.info(f"Fetched {len(messages)} messages from {folder_id}...")

        next_link = getattr(result, "odata_next_link", None)
        if not next_link:
            break

        # Be a considerate API citizen on long sweeps; Graph throttles per-app
        # and a tight loop over 50 pages is exactly what trips it.
        await asyncio.sleep(0)

    if pages >= max_pages and next_link:
        logger.warning(
            f"Stopped paging {folder_id} at the {max_pages}-page guard; "
            f"results are truncated."
        )

    return messages[:limit]


__all__ = ["fetch_messages"]
