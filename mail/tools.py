"""
Email tools for Outlook MCP server
"""

from .list import handle_list_emails
from .search import handle_search_emails
from .read import handle_read_email
from .send import handle_send_email
from .correspondents import handle_summarise_correspondents

__all__ = [
    "handle_list_emails",
    "handle_search_emails",
    "handle_read_email",
    "handle_send_email",
    "handle_summarise_correspondents",
]
