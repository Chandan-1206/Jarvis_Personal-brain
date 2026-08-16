"""
Stage 3.2 -- Drive OAuth smoke test.

Run locally:
    python scripts/drive_auth_test.py

Requests BOTH gmail.readonly and drive.readonly scopes in one token, since
our app needs both. First run re-triggers the browser consent screen
(that's why we deleted the old token.json) -- approve access to
personalbraintest@gmail.com for both Gmail and Drive.

If this prints your recently uploaded files, Drive access works and we
can move to real ingest.
"""

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
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
    service = build("drive", "v3", credentials=creds)

    results = service.files().list(
        pageSize=20,
        fields="files(id, name, mimeType, createdTime, modifiedTime, owners)",
        orderBy="createdTime desc",
    ).execute()

    files = results.get("files", [])
    if not files:
        print("No files found. Did you upload files to personalbraintest@gmail.com's Drive?")
        return

    print(f"Found {len(files)} files:\n")
    for f in files:
        print(f"  {f['name']}  ({f['mimeType']})")
        print(f"    id: {f['id']}")
        print(f"    created: {f.get('createdTime')}")
        print()


if __name__ == "__main__":
    main()
