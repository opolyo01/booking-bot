"""Standalone script to mark all Gmail emails as read.

Usage:
    1. First run: opens a browser for Google OAuth consent.
       python backend/scripts/mark_all_gmail_read.py

    2. Subsequent runs reuse the saved token automatically.

Requires: pip install google-auth google-auth-oauthlib google-api-python-client
"""

import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_PATH = Path(__file__).parent / ".gmail_token.json"
CREDENTIALS_PATH = Path(__file__).parent.parent / "credentials.json"


def get_credentials() -> Credentials:
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not CREDENTIALS_PATH.exists():
            print(
                f"Missing {CREDENTIALS_PATH}\n"
                "Download your OAuth client credentials JSON from the Google Cloud Console\n"
                "and save it as backend/credentials.json"
            )
            sys.exit(1)
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        creds = flow.run_local_server(port=0)

    TOKEN_PATH.write_text(creds.to_json())
    return creds


def mark_all_as_read(creds: Credentials) -> int:
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    marked = 0
    page_token = None

    while True:
        resp = (
            svc.users()
            .messages()
            .list(userId="me", q="is:unread", pageToken=page_token, maxResults=500)
            .execute()
        )

        message_ids = [m["id"] for m in resp.get("messages", [])]
        if not message_ids:
            break

        svc.users().messages().batchModify(
            userId="me",
            body={"ids": message_ids, "removeLabelIds": ["UNREAD"]},
        ).execute()

        marked += len(message_ids)
        print(f"  Marked {marked} messages as read so far...")

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return marked


def main():
    print("Authenticating with Gmail...")
    creds = get_credentials()

    print("Marking all unread emails as read...")
    total = mark_all_as_read(creds)

    if total == 0:
        print("No unread emails found — inbox already clean!")
    else:
        print(f"Done! Marked {total} emails as read.")


if __name__ == "__main__":
    main()
