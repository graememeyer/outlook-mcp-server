"""
Search emails functionality (msgraph-sdk)
"""

import asyncio

from msgraph.generated.users.item.mail_folders.item.messages.messages_request_builder import (
    MessagesRequestBuilder,
)

from config import (
    MAX_RESULT_COUNT,
    LIST_PAGE_SIZE,
    SEARCH_PAGE_SIZE,
    EMAIL_SELECT_FIELDS,
)
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

# When boolean filters are applied client-side (the $search path), over-fetch
# so that filtering doesn't leave the caller short of the count they asked for.
_CLIENT_FILTER_OVERFETCH = 4


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


def build_participant_filter(from_addr: str, to: str) -> list:
    """Build $filter clauses for sender/recipient, for the non-$search path.

    Graph refuses $search alongside $filter, so when a date window is present
    the address terms have to be expressed as filters instead. Recipients are
    a collection, hence the lambda.
    """
    clauses = []
    if from_addr:
        clauses.append(f"from/emailAddress/address eq '{from_addr}'")
    if to:
        clauses.append(
            f"toRecipients/any(r: r/emailAddress/address eq '{to}')"
        )
    return clauses


@mcp.tool(name="search_emails", title="Search emails")
async def handle_search_emails(
    folder: str = "inbox",
    count: int = 10,
    query: str = "",
    from_addr: str = "",
    to: str = "",
    subject: str = "",
    has_attachments: bool = False,
    unread_only: bool = False,
    received_after: str = "",
    received_before: str = "",
    include_recipients: bool = True,
) -> str:
    """
    Search emails in a specified folder with various filter criteria

    Note on date ranges: Microsoft Graph forbids combining $search with $filter
    or $orderby. When a date range is supplied, this tool therefore switches to
    a filter-based query. In that mode, from_addr/to become exact address
    matches and free-text `query`/`subject` matching is unavailable (subject
    falls back to a substring match). Without a date range, full-text search is
    used as before.

    Args:
        folder: The email folder to search in (default: "inbox")
        count: Maximum number of emails to retrieve across all pages
            (default: 10, maximum: 1000)
        query: General search query string to match against email content
        from_addr: Filter emails by sender email address
        to: Filter emails by recipient email address
        subject: Filter emails by subject line content
        has_attachments: Only return emails that have attachments (default: False)
        unread_only: Only return unread emails (default: False)
        received_after: Only include emails on or after this date. Accepts
            YYYY-MM-DD, an ISO-8601 timestamp, or relative shorthand like "90d"
        received_before: Only include emails on or before this date
        include_recipients: Include To/CC addresses in each summary (default: True)

    Returns:
        Formatted string containing search results with sender, recipients,
        subject, date, and read status
    """
    count = max(1, min(count, MAX_RESULT_COUNT))

    if not await asyncio.to_thread(has_valid_session):
        return "Authentication required. Please use the 'authenticate' tool first."

    try:
        client = get_graph_client()
        folder_id = await resolve_folder_id(client, folder)
        select = EMAIL_SELECT_FIELDS.split(",")
        date_field = date_field_for_folder(folder_id)

        try:
            date_clauses = build_date_filter(date_field, received_after, received_before)
        except DateParseError as e:
            return f"Invalid date range: {e}"

        kql = build_search_query(query, from_addr, to, subject)
        use_search = bool(kql) and not date_clauses
        notes = []

        if use_search:
            # $search cannot be combined with $orderby or $filter, so boolean
            # filters are applied client-side and we over-fetch to compensate.
            fetch_limit = count * _CLIENT_FILTER_OVERFETCH if (
                has_attachments or unread_only
            ) else count
            fetch_limit = min(fetch_limit, MAX_RESULT_COUNT * _CLIENT_FILTER_OVERFETCH)

            query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
                top=min(fetch_limit, SEARCH_PAGE_SIZE),
                search=kql,
                select=select,
            )
            notes.append("full-text search (results ranked by relevance, not date)")
        else:
            if kql and date_clauses:
                notes.append(
                    "date range supplied, so filter mode was used instead of "
                    "full-text search"
                )
            filters = list(date_clauses)
            filters.extend(build_participant_filter(from_addr, to))
            if has_attachments:
                filters.append("hasAttachments eq true")
            if unread_only:
                filters.append("isRead eq false")
            if subject:
                escaped = subject.replace("'", "''")
                filters.append(f"contains(subject, '{escaped}')")
            if query:
                notes.append(
                    "free-text `query` was ignored in filter mode; use "
                    "`subject` or drop the date range"
                )

            fetch_limit = count
            query_params = MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
                top=min(count, LIST_PAGE_SIZE),
                orderby=[f"{date_field} desc"],
                select=select,
                filter=combine_filters(filters),
            )

        messages = await fetch_messages(
            client, folder_id, query_params, limit=fetch_limit
        )

        # Client-side boolean filtering for the $search path.
        if use_search and has_attachments:
            messages = [m for m in messages if m.has_attachments]
        if use_search and unread_only:
            messages = [m for m in messages if m.is_read is False]
        messages = messages[:count]

        if not messages:
            return "No emails found matching your search criteria."

        body = "".join(
            format_summary(m, i, include_recipients=include_recipients)
            for i, m in enumerate(messages, 1)
        )
        note_text = f"\nNote: {'; '.join(notes)}.\n" if notes else ""
        return f"Found {len(messages)} emails:{note_text}\n{body}"

    except Exception as e:
        return f"Error searching emails: {str(e)}"
