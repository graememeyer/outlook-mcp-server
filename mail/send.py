"""
Send email functionality (msgraph-sdk)
"""

import asyncio

from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.importance import Importance
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.message import Message
from msgraph.generated.models.recipient import Recipient
from msgraph.generated.users.item.send_mail.send_mail_post_request_body import (
    SendMailPostRequestBody,
)

from auth.graph_auth import get_graph_client, has_valid_session
from server import mcp

_IMPORTANCE = {"low": Importance.Low, "normal": Importance.Normal, "high": Importance.High}


def _recipients(addresses: str):
    """Turn a comma-separated address string into a list of Recipient objects."""
    return [
        Recipient(email_address=EmailAddress(address=a.strip()))
        for a in (addresses or "").split(",")
        if a.strip()
    ]


@mcp.tool(name="send_email", title="Send email")
async def handle_send_email(
    to: str = "",
    cc: str = "",
    bcc: str = "",
    subject: str = "",
    body: str = "",
    importance: str = "normal",
    save_to_sent_items: bool = True,
) -> str:
    """
    Send an email through Outlook with specified recipients and content

    Args:
        to: Primary recipient email addresses (comma-separated for multiple recipients)
        cc: Carbon copy recipient email addresses (comma-separated for multiple recipients)
        bcc: Blind carbon copy recipient email addresses (comma-separated for multiple recipients)
        subject: Email subject line
        body: Email body content (HTML is detected automatically)
        importance: Email importance level ("low", "normal", or "high") (default: "normal")
        save_to_sent_items: Whether to save the email to Sent Items folder (default: True)

    Returns:
        Success message with sent email details or error message if sending failed
    """
    if not to:
        return "Recipient (to) is required."
    if not subject:
        return "Subject is required."
    if not body:
        return "Body content is required."

    if not await asyncio.to_thread(has_valid_session):
        return "Authentication required. Please use the 'authenticate' tool first."

    try:
        client = get_graph_client()

        to_recipients = _recipients(to)
        cc_recipients = _recipients(cc)
        bcc_recipients = _recipients(bcc)

        message = Message(
            subject=subject,
            body=ItemBody(
                content_type=BodyType.Html if "<html" in body.lower() else BodyType.Text,
                content=body,
            ),
            to_recipients=to_recipients,
            cc_recipients=cc_recipients or None,
            bcc_recipients=bcc_recipients or None,
            importance=_IMPORTANCE.get(importance.lower(), Importance.Normal),
        )

        request_body = SendMailPostRequestBody(
            message=message, save_to_sent_items=save_to_sent_items
        )
        await client.me.send_mail.post(request_body)

        extra = (f" + {len(cc_recipients)} CC" if cc_recipients else "") + (
            f" + {len(bcc_recipients)} BCC" if bcc_recipients else ""
        )
        return (
            "Email sent successfully!\n\n"
            f"Subject: {subject}\n"
            f"Recipients: {len(to_recipients)}{extra}\n"
            f"Message Length: {len(body)} characters"
        )

    except Exception as e:
        return f"Error sending email: {str(e)}"
