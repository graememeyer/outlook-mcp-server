"""
Authentication-related tools for the Outlook MCP server
"""

__all__ = ["handle_about", "handle_authenticate", "handle_check_auth_status"]

import asyncio
import logging

from config import settings
from server import mcp
from .graph_auth import authenticate_interactive, has_valid_session

logger = logging.getLogger(__name__)


@mcp.tool(name="about", title="About this server")
async def handle_about() -> str:
    """
    About tool handler - provides information about the Outlook MCP server

    Returns:
        String containing server information including name, version, capabilities,
        and available features for managing Outlook emails and calendar events
    """
    return (
        f"📧 MODULAR Outlook Assistant MCP Server v{settings.SERVER_VERSION} 📧\n\n"
        f"Provides access to Microsoft Outlook email, calendar, and contacts through Microsoft Graph API.\n"
        f"Implemented with a modular architecture for improved maintainability."
    )


@mcp.tool(name="authenticate", title="Authenticate with Microsoft")
async def handle_authenticate(force: bool = False) -> str:
    """
    Authentication tool handler - signs in to Microsoft Graph via the interactive
    browser flow. Opens a browser window for the user to sign in; the resulting
    tokens are cached (encrypted) so subsequent sessions refresh silently.

    Args:
        force: Re-run interactive sign-in even if a valid session already exists.

    Returns:
        A message indicating the signed-in account, or the failure reason.
    """
    if not force and await asyncio.to_thread(has_valid_session):
        return "Already authenticated and ready."

    try:
        record = await asyncio.to_thread(authenticate_interactive)
        return f"Authentication successful. Signed in as {record.username}."
    except Exception as e:
        logger.error(f"Interactive authentication failed: {str(e)}")
        return (
            "Authentication failed: "
            f"{str(e)}\n\nPlease try running the 'authenticate' tool again."
        )


@mcp.tool(name="check_auth_status", title="Check authentication status")
async def handle_check_auth_status() -> str:
    """
    Check authentication status tool handler - reports whether a valid Microsoft
    Graph session exists (attempting a silent token acquisition).

    Returns:
        A message describing the current authentication state.
    """
    if await asyncio.to_thread(has_valid_session):
        return "Authenticated and ready."

    return "Not authenticated. Please use the 'authenticate' tool to sign in."
