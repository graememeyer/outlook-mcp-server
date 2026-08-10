"""
Email folder utilities (msgraph-sdk).
"""

import logging

from kiota_abstractions.base_request_configuration import RequestConfiguration

logger = logging.getLogger(__name__)

# Friendly folder names -> Graph well-known folder IDs (usable directly as the
# folder id in /me/mailFolders/{id}).
WELL_KNOWN_FOLDERS = {
    "inbox": "inbox",
    "draft": "drafts",
    "drafts": "drafts",
    "sent": "sentitems",
    "sentitems": "sentitems",
    "sent items": "sentitems",
    "deleted": "deleteditems",
    "deleteditems": "deleteditems",
    "deleted items": "deleteditems",
    "trash": "deleteditems",
    "junk": "junkemail",
    "junkemail": "junkemail",
    "spam": "junkemail",
    "archive": "archive",
}


async def resolve_folder_id(client, folder_name: str) -> str:
    """
    Resolve a folder name to a Graph mail-folder id.

    Well-known names map to their Graph aliases; anything else is looked up by
    display name. Falls back to "inbox" if not found.
    """
    if not folder_name:
        return "inbox"

    key = folder_name.strip().lower()
    if key in WELL_KNOWN_FOLDERS:
        return WELL_KNOWN_FOLDERS[key]

    try:
        from msgraph.generated.users.item.mail_folders.mail_folders_request_builder import (
            MailFoldersRequestBuilder,
        )

        qp = MailFoldersRequestBuilder.MailFoldersRequestBuilderGetQueryParameters(
            filter=f"displayName eq '{folder_name}'",
            top=1,
            select=["id", "displayName"],
        )
        res = await client.me.mail_folders.get(
            request_configuration=RequestConfiguration(query_parameters=qp)
        )
        if res and res.value:
            logger.info(f"Resolved folder '{folder_name}' to id {res.value[0].id}")
            return res.value[0].id
    except Exception as e:
        logger.error(f"Error resolving folder '{folder_name}': {str(e)}")

    logger.info(f"Folder '{folder_name}' not found; falling back to inbox")
    return "inbox"


__all__ = ["resolve_folder_id", "WELL_KNOWN_FOLDERS"]
