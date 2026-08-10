"""
Shared formatting helpers for Graph message objects (msgraph-sdk models).
"""

import re
from datetime import datetime

from msgraph.generated.models.body_type import BodyType


def fmt_date(dt) -> str:
    """Format a Graph datetime as an ISO-8601 UTC string (…Z)."""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(dt) if dt else "unknown"


def _recipient_str(recipient) -> str:
    ea = getattr(recipient, "email_address", None) if recipient else None
    if not ea:
        return "unknown"
    return f"{ea.name or 'Unknown'} ({ea.address or 'unknown'})"


def _recipient_list(recipients) -> str:
    if not recipients:
        return "None"
    return ", ".join(_recipient_str(r) for r in recipients) or "None"


def format_summary(msg, index: int) -> str:
    """One-line-per-email summary used by list/search."""
    ea = msg.from_.email_address if msg.from_ else None
    name = (ea.name if ea else None) or "Unknown"
    address = (ea.address if ea else None) or "unknown"
    read_status = "" if (msg.is_read is None or msg.is_read) else "[UNREAD] "

    return (
        f"{index}. {read_status}{fmt_date(msg.received_date_time)} - From: {name} ({address})\n"
        f"Subject: {msg.subject or '(no subject)'}\n"
        f"ID: {msg.id}\n"
    )


def format_detail(msg) -> str:
    """Full detail rendering used by read_email."""
    body = ""
    if msg.body and msg.body.content is not None:
        if msg.body.content_type == BodyType.Html:
            # Simple HTML-to-text conversion for HTML bodies
            body = re.sub(r"<[^>]*>", "", msg.body.content)
        else:
            body = msg.body.content
    else:
        body = msg.body_preview or "No content"

    cc = _recipient_list(msg.cc_recipients)
    bcc = _recipient_list(msg.bcc_recipients)
    importance = msg.importance.value if msg.importance else "normal"

    return (
        f"From: {_recipient_str(msg.from_) if msg.from_ else 'Unknown'}\n"
        f"To: {_recipient_list(msg.to_recipients)}\n"
        + (f"CC: {cc}\n" if cc != "None" else "")
        + (f"BCC: {bcc}\n" if bcc != "None" else "")
        + f"Subject: {msg.subject or '(no subject)'}\n"
        f"Date: {fmt_date(msg.received_date_time)}\n"
        f"Importance: {importance}\n"
        f"Has Attachments: {'Yes' if msg.has_attachments else 'No'}\n\n"
        f"{body}"
    )
