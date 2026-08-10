"""
Improved search emails functionality
"""

from typing import Dict, Any
from config import MAX_RESULT_COUNT, EMAIL_SELECT_FIELDS
from utils.graph_api import call_graph_api
from auth import ensure_authenticated
from .folder_utils import resolve_folder_path
from logger import logger
from server import mcp


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
        has_attachments: Filter emails that have attachments (default: False)
        unread_only: Filter to show only unread emails (default: False)

    Returns:
        Formatted string containing search results with email details including
        sender, subject, date, read status, and attachment information
    """

    count = min(count, MAX_RESULT_COUNT)

    try:
        # Get access token
        access_token = await ensure_authenticated()
        if not access_token:
            return "Authentication required. Please use the 'authenticate' tool first."

        # Resolve the folder path
        endpoint = await resolve_folder_path(access_token, folder)
        logger.info(f"Using endpoint: {endpoint} for folder: {folder}")

        # Execute progressive search
        response = await progressive_search(
            endpoint,
            access_token,
            {"query": query, "from": from_addr, "to": to, "subject": subject},
            {"hasAttachments": has_attachments, "unreadOnly": unread_only},
            count,
        )

        return format_search_results(response)
    except Exception as e:
        if str(e) == "Authentication required":
            return "Authentication required. Please use the 'authenticate' tool first."

        return f"Error searching emails: {str(e)}"


async def progressive_search(
    endpoint: str,
    access_token: str,
    search_terms: Dict[str, str],
    filter_terms: Dict[str, bool],
    count: int,
) -> Dict[str, Any]:
    """
    Execute a search with progressively simpler fallback strategies

    Args:
        endpoint: API endpoint
        access_token: Access token
        search_terms: Search terms (query, from, to, subject)
        filter_terms: Filter terms (hasAttachments, unreadOnly)
        count: Maximum number of results

    Returns:
        Search results
    """
    # Track search strategies attempted
    search_attempts = []

    try:
        params = build_search_params(search_terms, filter_terms, count)
        logger.info(f"Attempting combined search with params: {params}")
        search_attempts.append("combined-search")

        response = await call_graph_api(access_token, "GET", endpoint, None, params)
        if response.get("value") and len(response["value"]) > 0:
            logger.info(
                f"Combined search successful: found {len(response['value'])} results"
            )
            return response
    except Exception as e:
        logger.error(f"Combined search failed: {str(e)}")

    # 2. Try each search term individually, starting with most specific
    search_priority = ["subject", "from", "to", "query"]

    for term in search_priority:
        if search_terms[term]:
            try:
                logger.info(
                    f"Attempting search with only {term}: '{search_terms[term]}'"
                )
                search_attempts.append(f"single-term-{term}")

                # For single term search, only use $search with that term.
                # NOTE: Microsoft Graph does not allow $search to be combined
                # with $orderby, so we deliberately omit $orderby here.
                simplified_params = {
                    "$top": count,
                    "$select": EMAIL_SELECT_FIELDS,
                }

                # Add the search term in the appropriate KQL syntax.
                # The whole expression must be double-quoted, including the
                # "field:value" form, otherwise Graph rejects the colon.
                if term == "query":
                    # General query doesn't need a field prefix
                    simplified_params["$search"] = f'"{search_terms[term]}"'
                else:
                    # Specific field searches use "field:value" syntax
                    simplified_params["$search"] = f'"{term}:{search_terms[term]}"'

                # Add boolean filters if applicable
                add_boolean_filters(simplified_params, filter_terms)

                response = await call_graph_api(
                    access_token, "GET", endpoint, None, simplified_params
                )
                if response.get("value") and len(response["value"]) > 0:
                    logger.info(
                        f"Search with {term} successful: found {len(response['value'])} results"
                    )
                    return response
            except Exception as e:
                logger.error(f"Search with {term} failed: {str(e)}")

    # 3. Try with only boolean filters
    if filter_terms.get("hasAttachments") or filter_terms.get("unreadOnly"):
        try:
            logger.info("Attempting search with only boolean filters")
            search_attempts.append("boolean-filters-only")

            filter_only_params = {
                "$top": count,
                "$select": EMAIL_SELECT_FIELDS,
                "$orderby": "receivedDateTime desc",
            }

            # Add the boolean filters
            add_boolean_filters(filter_only_params, filter_terms)

            response = await call_graph_api(
                access_token, "GET", endpoint, None, filter_only_params
            )
            logger.info(
                f"Boolean filter search found {len(response.get('value', []))} results"
            )
            return response
        except Exception as e:
            logger.error(f"Boolean filter search failed: {str(e)}")

    # 4. Final fallback: just get recent emails
    logger.info("All search strategies failed, falling back to recent emails")
    search_attempts.append("recent-emails")

    basic_params = {
        "$top": count,
        "$select": EMAIL_SELECT_FIELDS,
        "$orderby": "receivedDateTime desc",
    }

    response = await call_graph_api(access_token, "GET", endpoint, None, basic_params)
    logger.info(
        f"Fallback to recent emails found {len(response.get('value', []))} results"
    )

    # Add a note to the response about the search attempts
    response["_searchInfo"] = {
        "attemptsCount": len(search_attempts),
        "strategies": search_attempts,
        "originalTerms": search_terms,
        "filterTerms": filter_terms,
    }

    return response


def build_search_params(
    search_terms: Dict[str, str], filter_terms: Dict[str, bool], count: int
) -> Dict[str, Any]:
    """
    Build search parameters from search terms and filter terms

    Args:
        search_terms: Search terms (query, from, to, subject)
        filter_terms: Filter terms (hasAttachments, unreadOnly)
        count: Maximum number of results

    Returns:
        Query parameters
    """
    params = {
        "$top": count,
        "$select": EMAIL_SELECT_FIELDS,
    }

    # Handle search terms
    kql_terms = []

    # NOTE: For KQL field-scoped search, the *entire* "field:value" expression
    # must be wrapped in double quotes (e.g. "from:foo@bar.com"). Wrapping only
    # the value (from:"foo@bar.com") makes Graph reject the ':' as a syntax error.
    if search_terms["query"]:
        # General query doesn't need a field prefix
        kql_terms.append(f'"{search_terms["query"]}"')

    if search_terms["subject"]:
        kql_terms.append(f'"subject:{search_terms["subject"]}"')

    if search_terms["from"]:
        kql_terms.append(f'"from:{search_terms["from"]}"')

    if search_terms["to"]:
        kql_terms.append(f'"to:{search_terms["to"]}"')

    # Add $search if we have any search terms.
    # NOTE: Microsoft Graph does not allow $search to be combined with
    # $orderby, so only fall back to $orderby when there is no $search.
    if kql_terms:
        params["$search"] = " ".join(kql_terms)
    else:
        params["$orderby"] = "receivedDateTime desc"

    # Add boolean filters
    add_boolean_filters(params, filter_terms)

    return params


def add_boolean_filters(params: Dict[str, Any], filter_terms: Dict[str, bool]) -> None:
    """
    Add boolean filters to query parameters

    Args:
        params: Query parameters
        filter_terms: Filter terms (hasAttachments, unreadOnly)
    """
    filter_conditions = []

    if filter_terms.get("hasAttachments"):
        filter_conditions.append("hasAttachments eq true")

    if filter_terms.get("unreadOnly"):
        filter_conditions.append("isRead eq false")

    # Add $filter parameter if we have any filter conditions
    if filter_conditions:
        params["$filter"] = " and ".join(filter_conditions)


def format_search_results(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format search results into a readable text format

    Args:
        response: The API response object

    Returns:
        str
    """
    if not response.get("value") or len(response["value"]) == 0:
        return "No emails found matching your search criteria."

    # Format each email
    email_list = []
    for index, email in enumerate(response["value"], 1):
        sender = email.get("from", {}).get(
            "emailAddress", {"name": "Unknown", "address": "unknown"}
        )
        date = email["receivedDateTime"]
        read_status = "" if email.get("isRead", True) else "[UNREAD] "

        email_list.append(
            f"{index}. {read_status}{date} - From: {sender['name']} ({sender['address']})\n"
            f"Subject: {email['subject']}\n"
            f"ID: {email['id']}\n"
        )

    # Add search info if available
    search_info = response.get("_searchInfo", {})
    if search_info:
        info_text = (
            f"\nSearch Information:\n"
            f"Attempted {search_info['attemptsCount']} search strategies: {', '.join(search_info['strategies'])}\n"
        )
    else:
        info_text = ""

    return f"Found {len(response['value'])} emails:\n\n{''.join(email_list)}{info_text}"
