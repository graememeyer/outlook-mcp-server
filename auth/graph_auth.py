"""
Microsoft Graph authentication using the azure-identity interactive browser flow.

A single delegated-user credential is shared across the server. Tokens (and the
refresh token) are held in an encrypted, on-disk MSAL cache via
``TokenCachePersistenceOptions``, and the ``AuthenticationRecord`` identifying the
signed-in account is persisted alongside it. Together these let the credential
refresh silently across restarts and multi-day gaps, only opening a browser on
the very first sign-in (or after the refresh token itself expires).
"""

from typing import Optional

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import (
    AuthenticationRecord,
    AuthenticationRequiredError,
    InteractiveBrowserCredential,
    TokenCachePersistenceOptions,
)

from config import settings
from logger import logger

# ".default" requests exactly the delegated permissions configured on the app
# registration (see terraform / MS_SCOPES), so scopes live in one place.
GRAPH_SCOPE = "https://graph.microsoft.com/.default"

# Name of the persisted MSAL token cache (managed by msal-extensions).
_CACHE_NAME = "outlook-mcp"

_credential: Optional[InteractiveBrowserCredential] = None


def _load_auth_record() -> Optional[AuthenticationRecord]:
    """Load the persisted AuthenticationRecord, if a previous sign-in exists."""
    try:
        with open(settings.MS_AUTH_RECORD_PATH, "r") as f:
            return AuthenticationRecord.deserialize(f.read())
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.error(f"Failed to load auth record: {str(e)}")
        return None


def _save_auth_record(record: AuthenticationRecord) -> None:
    try:
        with open(settings.MS_AUTH_RECORD_PATH, "w") as f:
            f.write(record.serialize())
        logger.info("Saved authentication record")
    except Exception as e:
        logger.error(f"Failed to save auth record: {str(e)}")


def get_credential() -> InteractiveBrowserCredential:
    """Return the shared credential, constructing it on first use.

    ``disable_automatic_authentication`` means token acquisition never silently
    pops a browser mid-request; instead it raises ``AuthenticationRequiredError``
    and the caller is told to run the ``authenticate`` tool.
    """
    global _credential
    if _credential is None:
        _credential = InteractiveBrowserCredential(
            client_id=settings.MS_CLIENT_ID,
            tenant_id=settings.MS_TENANT_ID,
            cache_persistence_options=TokenCachePersistenceOptions(name=_CACHE_NAME),
            authentication_record=_load_auth_record(),
            disable_automatic_authentication=True,
        )
    return _credential


def authenticate_interactive() -> AuthenticationRecord:
    """Open the browser for interactive sign-in and persist the account record."""
    record = get_credential().authenticate(scopes=[GRAPH_SCOPE])
    _save_auth_record(record)
    return record


def get_access_token() -> Optional[str]:
    """Silently return a valid access token, or ``None`` if sign-in is required."""
    try:
        return get_credential().get_token(GRAPH_SCOPE).token
    except AuthenticationRequiredError:
        logger.info("Interactive authentication required")
        return None
    except ClientAuthenticationError as e:
        logger.error(f"Token acquisition failed: {str(e)}")
        return None


def has_valid_session() -> bool:
    """True if a token can be obtained silently (i.e. the user is signed in)."""
    return get_access_token() is not None
