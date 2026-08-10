"""
Read email functionality (msgraph-sdk)
"""

import asyncio

from kiota_abstractions.base_request_configuration import RequestConfiguration
from msgraph.generated.users.item.messages.item.message_item_request_builder import (
    MessageItemRequestBuilder,
)

from config import EMAIL_DETAIL_FIELDS
from auth.graph_auth import get_graph_client, has_valid_session
from .formatting import format_detail
from logger import logger
from server import mcp


@mcp.tool()
async def handle_read_email(id: str) -> str:
    """
    Read a specific email by its ID and return detailed content

    Args:
        id: The unique identifier of the email to read

    Returns:
        Formatted string containing complete email details including sender, recipients,
        subject, date, importance, attachments status, and full body content
    """
    if not id:
        return "Email ID is required."

    if not await asyncio.to_thread(has_valid_session):
        return "Authentication required. Please use the 'authenticate' tool first."

    try:
        client = get_graph_client()
        query_params = MessageItemRequestBuilder.MessageItemRequestBuilderGetQueryParameters(
            select=EMAIL_DETAIL_FIELDS.split(",")
        )
        msg = await client.me.messages.by_message_id(id).get(
            request_configuration=RequestConfiguration(query_parameters=query_params)
        )

        if not msg:
            return f"Email with ID {id} not found."

        return format_detail(msg)

    except Exception as e:
        logger.error(f"Error reading email: {str(e)}")
        text = str(e)
        if "doesn't belong to the targeted mailbox" in text or "ErrorInvalidIdMalformed" in text:
            return (
                "The email ID seems invalid or doesn't belong to your mailbox. "
                "Please try with a different email ID."
            )
        return f"Failed to read email: {text}"
