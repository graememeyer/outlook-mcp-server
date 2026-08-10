"""
Token management for Microsoft Graph API authentication
"""

import os
import json
import time
from typing import Dict, Optional

import requests

from logger import logger
from config import settings

# Microsoft identity platform token endpoint (same one the auth server uses)
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

# Refresh slightly ahead of the real expiry so a long-running call never races
# the boundary.
EXPIRY_BUFFER_SECONDS = 300


def load_token_cache() -> Optional[Dict]:
    """Load tokens from cache file"""
    try:
        if not os.path.exists(settings.MS_TOKEN_STORE_PATH):
            logger.info("No token cache file found")
            return None

        with open(settings.MS_TOKEN_STORE_PATH) as f:
            tokens = json.load(f)

        logger.info("Successfully loaded token cache")
        return tokens

    except Exception as e:
        logger.error(f"Error loading token cache: {str(e)}")
        return None


def save_token_cache(tokens: Dict) -> bool:
    """Save tokens to cache file"""
    try:
        with open(settings.MS_TOKEN_STORE_PATH, "w") as f:
            json.dump(tokens, f, indent=2)

        logger.info("Successfully saved token cache")
        return True

    except Exception as e:
        logger.error(f"Error saving token cache: {str(e)}")
        return False


def is_token_expired(tokens: Dict) -> bool:
    """Check if the access token is expired (or about to expire).

    ``expires_at`` is stored in Unix seconds by the auth server and by
    ``refresh_access_token`` below, so we compare against ``time.time()``.
    """
    if not tokens or "expires_at" not in tokens:
        return True

    return time.time() >= (tokens["expires_at"] - EXPIRY_BUFFER_SECONDS)


def refresh_access_token(tokens: Dict) -> Optional[str]:
    """Exchange the stored refresh token for a fresh access token.

    Persists the new tokens (carrying the existing refresh token forward if
    Microsoft doesn't return a rotated one) and returns the new access token,
    or ``None`` if refresh isn't possible (no refresh token, or the grant was
    rejected — e.g. the refresh token has expired or been revoked).
    """
    refresh_token = tokens.get("refresh_token") if tokens else None
    if not refresh_token:
        logger.info("No refresh token available; interactive re-authentication required")
        return None

    data = {
        "client_id": settings.MS_CLIENT_ID,
        "client_secret": settings.MS_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(settings.MS_SCOPES),
    }

    try:
        response = requests.post(TOKEN_URL, data=data, timeout=30)
        result = response.json()
    except Exception as e:
        logger.error(f"Token refresh request failed: {str(e)}")
        return None

    if "error" in result or "access_token" not in result:
        logger.error(
            "Token refresh failed: "
            f"{result.get('error_description', result.get('error', 'unknown error'))}"
        )
        return None

    # Microsoft usually rotates the refresh token, but not always. Preserve the
    # previous one if a replacement wasn't returned so we don't lose the ability
    # to refresh next time.
    if "refresh_token" not in result:
        result["refresh_token"] = refresh_token

    result["expires_at"] = int(time.time()) + int(result.get("expires_in", 3600))

    save_token_cache(result)
    logger.info("Successfully refreshed access token")

    return result["access_token"]


def get_valid_token() -> Optional[str]:
    """Get a valid access token, refreshing it if necessary."""
    tokens = load_token_cache()

    if not tokens:
        logger.info("No tokens found")
        return None

    if is_token_expired(tokens):
        logger.info("Access token expired or near expiry, attempting refresh")
        return refresh_access_token(tokens)

    return tokens["access_token"]
