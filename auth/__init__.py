"""
Main authentication module for the Outlook MCP server
"""

import asyncio
import logging
from typing import Optional

from .graph_auth import get_access_token
from .tools import *
from .tools import __all__ as tools_all

logger = logging.getLogger(__name__)


async def ensure_authenticated() -> Optional[str]:
    """
    Ensure the user is authenticated and return a valid access token.
    Returns None if interactive sign-in is required.
    """
    token = await asyncio.to_thread(get_access_token)

    if not token:
        logger.info("No valid token found, interactive authentication required")
        return None

    return token


# Export the auth helper and tools
__all__ = ["ensure_authenticated"] + tools_all
