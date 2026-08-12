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


def _truncate_recipients(recipients, max_shown: int = 4) -> str:
    """Render a recipient list, collapsing the tail of large distributions."""
    if not recipients:
        return "None"
    shown = [_recipient_str(r) for r in recipients[:max_shown]]
    extra = len(recipients) - max_shown
    if extra > 0:
        shown.append(f"(+{extra} more)")
    return ", ".join(shown)


def message_date(msg):
    """Prefer sentDateTime when present, else receivedDateTime.

    Sent items carry both; receivedDateTime on a sent item reflects delivery
    and is occasionally absent, so authorship time is the better default.
    """
    return getattr(msg, "sent_date_time", None) or msg.received_date_time


def format_summary(msg, index: int, include_recipients: bool = True) -> str:
    """One-line-per-email summary used by list/search.

    Recipients are included by default: they were already being fetched via
    $select but never rendered, which forced a read_email round-trip per
    message just to find out who a sent item went to.
    """
    ea = msg.from_.email_address if msg.from_ else None
    name = (ea.name if ea else None) or "Unknown"
    address = (ea.address if ea else None) or "unknown"
    read_status = "" if (msg.is_read is None or msg.is_read) else "[UNREAD] "

    out = (
        f"{index}. {read_status}{fmt_date(message_date(msg))} - From: {name} ({address})\n"
    )
    if include_recipients:
        out += f"To: {_truncate_recipients(msg.to_recipients)}\n"
        cc = _truncate_recipients(msg.cc_recipients)
        if cc != "None":
            out += f"CC: {cc}\n"
    out += (
        f"Subject: {msg.subject or '(no subject)'}\n"
        f"ID: {msg.id}\n"
    )
    return out


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
        f"Date: {fmt_date(message_date(msg))}\n"
        f"Importance: {importance}\n"
        f"Has Attachments: {'Yes' if msg.has_attachments else 'No'}\n\n"
        f"{body}"
    )
