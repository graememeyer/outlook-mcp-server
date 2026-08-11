__all__ = [
    "settings",
    "SERVER_VERSION",
    "MS_CLIENT_ID",
    "MS_TENANT_ID",
    "MS_SCOPES",
    "MS_AUTH_RECORD_PATH",
]

from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SERVER_NAME: str = "outlook-assistant"
    SERVER_VERSION: str = "v1.0.0"

    # Azure AD application (client) ID of the app registration.
    MS_CLIENT_ID: str
    # "common" supports both personal Microsoft accounts and org/work accounts.
    MS_TENANT_ID: str = "common"

    # The interactive browser flow is a public-client (PKCE) flow and needs no
    # client secret. It's accepted (optional) only for backwards compatibility.
    MS_CLIENT_SECRET: Optional[str] = None

    # Delegated Graph permissions the app registration is configured with. Kept
    # for documentation/terraform parity; the credential requests them via
    # ".default" rather than listing them per-call.
    MS_SCOPES: List[str] = [
        "offline_access",
        "User.Read",
        "Mail.Read",
        "Mail.Send",
        "Calendars.Read",
        "Calendars.ReadWrite",
        "Contacts.Read",
    ]

    # Where the signed-in account's AuthenticationRecord is persisted. The token
    # cache itself is managed separately by msal-extensions (encrypted at rest).
    MS_AUTH_RECORD_PATH: str = str(Path.home() / ".outlook-mcp-auth-record.json")

    # Allow the persistent token cache to fall back to unencrypted storage when
    # no OS secret store is available (e.g. a headless Linux container). Keep
    # False on desktops (DPAPI/Keychain/libsecret are used); set True in the
    # container deployment, where the cache lives on a protected volume.
    MS_ALLOW_UNENCRYPTED_TOKEN_CACHE: bool = False

    # Transport. "stdio" (default) for local use with Claude Code/desktop;
    # "http" (streamable HTTP) for a hosted/remote deployment behind a proxy.
    MCP_TRANSPORT: str = "stdio"
    MCP_HOST: str = "127.0.0.1"
    MCP_PORT: int = 8000
    MCP_PATH: str = "/mcp"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
MS_CLIENT_ID = settings.MS_CLIENT_ID
MS_TENANT_ID = settings.MS_TENANT_ID
MS_SCOPES = settings.MS_SCOPES
MS_AUTH_RECORD_PATH = settings.MS_AUTH_RECORD_PATH

SERVER_NAME = settings.SERVER_NAME
SERVER_VERSION = settings.SERVER_VERSION

# Microsoft Graph API
GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0/"

# Calendar constants
CALENDAR_SELECT_FIELDS = (
    "id,subject,bodyPreview,start,end,location,organizer,attendees,isAllDay,isCancelled"
)

# Email constants
EMAIL_SELECT_FIELDS = "id,subject,from,toRecipients,ccRecipients,receivedDateTime,bodyPreview,hasAttachments,importance,isRead"
EMAIL_DETAIL_FIELDS = "id,subject,from,toRecipients,ccRecipients,bccRecipients,receivedDateTime,bodyPreview,body,hasAttachments,importance,isRead,internetMessageHeaders"

# Pagination
DEFAULT_PAGE_SIZE = 25
MAX_RESULT_COUNT = 50
