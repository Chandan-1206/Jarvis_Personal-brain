"""
Stage 2.4 -- Gmail full message fetch.

Run locally:
    python scripts/gmail_fetch_full.py

Extends gmail_auth_test.py: instead of just headers, pulls the plain-text
body and lists any attachments per message. This is the shape of data
Stage 2.5 will normalize into GBrain pages.
"""

import base64
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


def extract_body_and_attachments(payload):
    """Walk the MIME tree and pull out plain-text body + attachment metadata."""
    body_text = ""
    attachments = []

    def walk(part):
        nonlocal body_text
        mime_type = part.get("mimeType", "")
        filename = part.get("filename", "")
        body = part.get("body", {})

        if filename:
            attachments.append({
                "filename": filename,
                "mime_type": mime_type,
                "attachment_id": body.get("attachmentId"),
                "size": body.get("size"),
            })
        elif mime_type == "text/plain" and "data" in body:
            decoded = base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="replace")
            body_text += decoded

        for sub_part in part.get("parts", []):
            walk(sub_part)

    walk(payload)
    return body_text.strip(), attachments


def main():
    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    results = service.users().messages().list(userId="me", maxResults=10).execute()
    messages = results.get("messages", [])

    if not messages:
        print("No messages found.")
        return

    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        body, attachments = extract_body_and_attachments(msg["payload"])

        print("=" * 70)
        print(f"Subject: {headers.get('Subject', '(no subject)')}")
        print(f"From:    {headers.get('From', '?')}")
        print(f"Thread:  {msg.get('threadId')}")
        print(f"Body preview: {body[:150]!r}")
        if attachments:
            print(f"Attachments: {[a['filename'] for a in attachments]}")
        print()


if __name__ == "__main__":
    main()
