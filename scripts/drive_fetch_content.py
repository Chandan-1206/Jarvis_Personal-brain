"""
Stage 3.3 -- Drive file content fetch.

Run locally:
    python scripts/drive_fetch_content.py

For each file in Drive, extracts plain text:
  - Google Docs/Sheets: exported directly as text via the Drive API
  - PDFs: downloaded and text-extracted with pypdf
  - Anything else: skipped (content left empty), metadata still captured

This proves we can pull real, reasonable content out of every file type
you seeded, before Stage 3.4 normalizes it into GBrain pages.
"""

import io
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
CLIENT_SECRET_PATH = "credentials/client_secret.json"
TOKEN_PATH = "credentials/token.json"

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
PDF_MIME = "application/pdf"


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


def extract_text(service, file_id, mime_type):
    try:
        if mime_type == GOOGLE_DOC_MIME:
            data = service.files().export(fileId=file_id, mimeType="text/plain").execute()
            return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data

        if mime_type == GOOGLE_SHEET_MIME:
            data = service.files().export(fileId=file_id, mimeType="text/csv").execute()
            return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data

        if mime_type == PDF_MIME:
            request = service.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            buf.seek(0)

            try:
                from pypdf import PdfReader
                reader = PdfReader(buf)
                return "\n".join(page.extract_text() or "" for page in reader.pages)
            except ImportError:
                return "[pypdf not installed -- run: pip install pypdf]"

        return ""  # unsupported type, metadata-only
    except Exception as e:
        return f"[extraction failed: {e}]"


def main():
    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)

    results = service.files().list(
        pageSize=20,
        fields="files(id, name, mimeType, createdTime, modifiedTime)",
        orderBy="createdTime desc",
    ).execute()
    files = results.get("files", [])

    if not files:
        print("No files found.")
        return

    for f in files:
        text = extract_text(service, f["id"], f["mimeType"])
        print("=" * 70)
        print(f"Name: {f['name']}  ({f['mimeType']})")
        print(f"Text preview: {text[:200]!r}")
        print()


if __name__ == "__main__":
    main()
