"""
Stage 3.4 -- Drive -> GBrain page ingest, with email cross-linking.

Run locally, AFTER scripts/gmail_ingest.py has already populated pages/email/:
    python scripts/drive_ingest.py

For each Drive file, writes a GBrain-format markdown page under pages/file/
matching the schema in SPEC.md section 4. Cross-links each file to an email
thread using two signals: real Gmail attachments, and filenames mentioned
in email body text (covers files shared as links/text rather than true
attachments).
"""

import io
import os
import re
import glob

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
EMAIL_PAGES_DIR = "pages/email"
OUTPUT_DIR = "pages/file"

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
            from pypdf import PdfReader
            reader = PdfReader(buf)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        return ""
    except Exception as e:
        return f"[extraction failed: {e}]"


def build_attachment_index():
    index = {}
    for path in glob.glob(os.path.join(EMAIL_PAGES_DIR, "*.md")):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        thread_match = re.search(r'gmail_thread_id:\s*"([^"]*)"', content)
        if not thread_match:
            continue
        thread_id = thread_match.group(1)

        attachments_match = re.search(r"attachments:\s*\[([^\]]*)\]", content)
        if attachments_match:
            for fname in re.findall(r'"([^"]*)"', attachments_match.group(1)):
                index.setdefault(fname.lower().strip(), thread_id)

        parts = content.split("---", 2)
        body = parts[2] if len(parts) >= 3 else ""
        for m in re.finditer(r"\b([\w\-]+\.(?:pdf|docx?|xlsx?|csv))\b", body, re.IGNORECASE):
            index.setdefault(m.group(1).lower().strip(), thread_id)

    return index


def normalize_name(name):
    return re.sub(r"\.(pdf|docx?|xlsx?|csv)$", "", name.lower().strip())


def yaml_str(s):
    return '"' + str(s).replace('"', '\\"').replace("\n", " ").strip() + '"'


def safe_filename(file_id):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", file_id)


def main():
    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    attachment_index = build_attachment_index()
    print(f"Loaded {len(attachment_index)} filename signals from email pages for cross-linking.\n")

    results = service.files().list(
        pageSize=50,
        fields="files(id, name, mimeType, createdTime, modifiedTime, owners, shared)",
        orderBy="createdTime desc",
    ).execute()
    files = results.get("files", [])

    if not files:
        print("No files found -- nothing to ingest.")
        return

    written = 0
    for f in files:
        text = extract_text(service, f["id"], f["mimeType"])
        owner = f.get("owners", [{}])[0].get("emailAddress", "")

        fname_lower = f["name"].lower().strip()
        linked_thread = attachment_index.get(fname_lower)
        if not linked_thread:
            norm_target = normalize_name(f["name"])
            for att_name, thread_id in attachment_index.items():
                if normalize_name(att_name) == norm_target:
                    linked_thread = thread_id
                    break

        frontmatter = "\n".join([
            "---",
            "type: file",
            f"drive_file_id: {yaml_str(f['id'])}",
            f"name: {yaml_str(f['name'])}",
            f"mime_type: {yaml_str(f['mimeType'])}",
            f"created: {yaml_str(f.get('createdTime', ''))}",
            f"modified: {yaml_str(f.get('modifiedTime', ''))}",
            f"owner: {yaml_str(owner)}",
            "shared_with: []",
            f"linked_email_thread_id: {yaml_str(linked_thread) if linked_thread else 'null'}",
            "---",
        ])

        page_content = f"{frontmatter}\n{text}\n"
        out_path = os.path.join(OUTPUT_DIR, f"{safe_filename(f['id'])}.md")
        with open(out_path, "w", encoding="utf-8") as out_f:
            out_f.write(page_content)

        link_note = f"  -> linked to thread {linked_thread}" if linked_thread else ""
        print(f"  wrote {out_path}  ({f['name']}){link_note}")
        written += 1

    print(f"\nDone. {written} file pages written to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
