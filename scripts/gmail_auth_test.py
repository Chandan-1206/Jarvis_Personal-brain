"""
Stage 2.3 -- Gmail OAuth smoke test.

Run this LOCALLY only (never on Vercel):

    python scripts/gmail_auth_test.py

First run: opens a browser window asking you to log into
personalbraintest@gmail.com and approve read-only Gmail access.
This creates credentials/token.json so future runs skip the browser step.

If this prints your 5 most recent email subjects, OAuth is working
end-to-end and we can move to real ingest.
"""

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CLIENT_SECRET_PATH = "credentials/client_secret.json"
TOKEN_PATH = "credentials/token.json"


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


def main():
    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    results = service.users().messages().list(userId="me", maxResults=5).execute()
    messages = results.get("messages", [])

    if not messages:
        print("No messages found. Did you seed personalbraintest@gmail.com yet?")
        return

    print(f"Found {len(messages)} recent messages:\n")
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="metadata",
            metadataHeaders=["Subject", "From", "Date"]
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        print(f"  Subject: {headers.get('Subject', '(no subject)')}")
        print(f"  From:    {headers.get('From', '?')}")
        print(f"  Date:    {headers.get('Date', '?')}")
        print()


if __name__ == "__main__":
    main()
