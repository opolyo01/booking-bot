import asyncio
import logging

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


def _service(creds: Credentials):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


async def mark_all_as_read(creds: Credentials) -> int:
    """Mark every unread message in the mailbox as read. Returns count marked."""

    def _sync() -> int:
        svc = _service(creds)
        marked = 0
        page_token = None

        while True:
            resp = (
                svc.users()
                .messages()
                .list(
                    userId="me",
                    q="is:unread",
                    pageToken=page_token,
                    maxResults=500,
                )
                .execute()
            )

            message_ids = [m["id"] for m in resp.get("messages", [])]
            if not message_ids:
                break

            svc.users().messages().batchModify(
                userId="me",
                body={
                    "ids": message_ids,
                    "removeLabelIds": ["UNREAD"],
                },
            ).execute()

            marked += len(message_ids)
            logger.info("Marked %d messages as read so far", marked)

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return marked

    return await asyncio.to_thread(_sync)
