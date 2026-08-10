"""
List emails functionality (msgraph-sdk)
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


@mcp.tool()
async def handle_list_emails(
    folder: str = "inbox",
    count: int = 10,
) -> str:
    """
    List emails from a specified Outlook folder

    Args:
        folder: The email folder to list emails from (default: "inbox")
        count: Maximum number of emails to retrieve (default: 10)

    Returns:
        Formatted string containing email list with sender, subject, date, and read status
    """
    count = min(count, MAX_RESULT_COUNT)

    if not await asyncio.to_thread(has_valid_session):
        return "Authentication required. Please use the 'authenticate' tool first."

    try:
        client = get_graph_client()
        folder_id = await resolve_folder_id(client, folder)

        query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
            top=count,
            orderby=["receivedDateTime desc"],
            select=EMAIL_SELECT_FIELDS.split(","),
        )
        result = await client.me.mail_folders.by_mail_folder_id(folder_id).messages.get(
            request_configuration=RequestConfiguration(query_parameters=query_params)
        )

        messages = result.value if result and result.value else []
        if not messages:
            return f"No emails found in {folder}."

        body = "".join(format_summary(m, i) for i, m in enumerate(messages, 1))
        return f"Found {len(messages)} emails in {folder}:\n\n{body}"

    except Exception as e:
        return f"Error listing emails: {str(e)}"
