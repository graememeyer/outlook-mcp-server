"""
Search emails functionality (msgraph-sdk)
"""

import asyncio

from kiota_abstractions.base_request_configuration import RequestConfiguration
from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (
    MessagesRequestBuilder,
)

from config import MAX_RESULT_COUNT, EMAIL_SELECT_FIELDS
from auth.graph_auth import get_graph_client, has_valid_session
from .folder_utils import resolve_folder_id
from .formatting import format_summary
from server import mcp


def build_search_query(query: str, from_addr: str, to: str, subject: str) -> str:
    """Build a Graph KQL $search string from the individual terms.

    Each field-scoped term must be wrapped *entirely* in double quotes
    (e.g. "from:foo@bar.com"); multiple terms are ANDed with a space.
    """
    terms = []
    if query:
        terms.append(f'"{query}"')
    if subject:
        terms.append(f'"subject:{subject}"')
    if from_addr:
        terms.append(f'"from:{from_addr}"')
    if to:
        terms.append(f'"to:{to}"')
    return " ".join(terms)


@mcp.tool()
async def handle_search_emails(
    folder: str = "inbox",
    count: int = 10,
    query: str = "",
    from_addr: str = "",
    to: str = "",
    subject: str = "",
    has_attachments: bool = False,
    unread_only: bool = False,
) -> str:
    """
    Search emails in a specified folder with various filter criteria

    Args:
        folder: The email folder to search in (default: "inbox")
        count: Maximum number of emails to retrieve (default: 10)
        query: General search query string to match against email content
        from_addr: Filter emails by sender email address
        to: Filter emails by recipient email address
        subject: Filter emails by subject line content
        has_attachments: Only return emails that have attachments (default: False)
        unread_only: Only return unread emails (default: False)

    Returns:
        Formatted string containing search results with sender, subject, date, and read status
    """
    count = min(count, MAX_RESULT_COUNT)

    if not await asyncio.to_thread(has_valid_session):
        return "Authentication required. Please use the 'authenticate' tool first."

    try:
        client = get_graph_client()
        folder_id = await resolve_folder_id(client, folder)
        select = EMAIL_SELECT_FIELDS.split(",")

        kql = build_search_query(query, from_addr, to, subject)

        if kql:
            # Graph forbids $search together with $orderby or $filter, so the
            # boolean filters (attachments/unread) are applied client-side below.
            query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
                top=count,
                search=kql,
                select=select,
            )
        else:
            filters = []
            if has_attachments:
                filters.append("hasAttachments eq true")
            if unread_only:
                filters.append("isRead eq false")
            query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
                top=count,
                orderby=["receivedDateTime desc"],
                select=select,
                filter=" and ".join(filters) if filters else None,
            )

        result = await client.me.mail_folders.by_mail_folder_id(folder_id).messages.get(
            request_configuration=RequestConfiguration(query_parameters=query_params)
        )
        messages = list(result.value) if result and result.value else []

        # Client-side boolean filtering for the $search path.
        if kql and has_attachments:
            messages = [m for m in messages if m.has_attachments]
        if kql and unread_only:
            messages = [m for m in messages if m.is_read is False]

        if not messages:
            return "No emails found matching your search criteria."

        body = "".join(format_summary(m, i) for i, m in enumerate(messages, 1))
        return f"Found {len(messages)} emails:\n\n{body}"

    except Exception as e:
        return f"Error searching emails: {str(e)}"
