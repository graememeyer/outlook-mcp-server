"""
List emails functionality (msgraph-sdk)
"""

import asyncio

from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (
    MessagesRequestBuilder,
)

from config import MAX_RESULT_COUNT, LIST_PAGE_SIZE, EMAIL_SELECT_FIELDS
from auth.graph_auth import get_graph_client, has_valid_session
from .folder_utils import resolve_folder_id
from .formatting import format_summary
from .date_utils import (
    DateParseError,
    build_date_filter,
    combine_filters,
    date_field_for_folder,
)
from .paging import fetch_messages
from server import mcp


@mcp.tool(name="list_emails", title="List emails")
async def handle_list_emails(
    folder: str = "inbox",
    count: int = 10,
    received_after: str = "",
    received_before: str = "",
    include_recipients: bool = True,
) -> str:
    """
    List emails from a specified Outlook folder, optionally within a date range

    Args:
        folder: The email folder to list emails from (default: "inbox")
        count: Maximum number of emails to retrieve across all pages (default: 10,
            maximum: 1000). Results are paginated automatically.
        received_after: Only include emails on or after this date. Accepts
            YYYY-MM-DD, an ISO-8601 timestamp, or relative shorthand such as
            "90d", "6m", "1y" (default: no lower bound)
        received_before: Only include emails on or before this date, same
            formats as received_after (default: no upper bound)
        include_recipients: Include To/CC addresses in each summary (default: True)

    Returns:
        Formatted string containing email list with sender, recipients, subject,
        date, and read status
    """
    count = max(1, min(count, MAX_RESULT_COUNT))

    if not await asyncio.to_thread(has_valid_session):
        return "Authentication required. Please use the 'authenticate' tool first."

    try:
        client = get_graph_client()
        folder_id = await resolve_folder_id(client, folder)
        date_field = date_field_for_folder(folder_id)

        try:
            date_clauses = build_date_filter(date_field, received_after, received_before)
        except DateParseError as e:
            return f"Invalid date range: {e}"

        query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
            top=min(count, LIST_PAGE_SIZE),
            orderby=[f"{date_field} desc"],
            select=EMAIL_SELECT_FIELDS.split(","),
            filter=combine_filters(date_clauses),
        )

        messages = await fetch_messages(client, folder_id, query_params, limit=count)

        window = ""
        if received_after or received_before:
            window = (
                f" between {received_after or 'the beginning'} "
                f"and {received_before or 'now'}"
            )

        if not messages:
            return f"No emails found in {folder}{window}."

        body = "".join(
            format_summary(m, i, include_recipients=include_recipients)
            for i, m in enumerate(messages, 1)
        )
        truncated = " (truncated to the requested count)" if len(messages) == count else ""
        return f"Found {len(messages)} emails in {folder}{window}{truncated}:\n\n{body}"

    except Exception as e:
        return f"Error listing emails: {str(e)}"
