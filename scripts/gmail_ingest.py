"""
Stage 2.5 -- Gmail -> GBrain page ingest.

Run locally:
    python scripts/gmail_ingest.py

Fetches messages from personalbraintest@gmail.com and writes each one as
a GBrain-format markdown page under pages/email/, matching the schema in
SPEC.md section 4. These files are what `gbrain import` will load in a
later stage -- this script does NOT touch GBrain or any database, it just
produces the normalized markdown.

Adjust MAX_MESSAGES if you want more/fewer than the default pulled in.
"""

import base64
import os
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CLIENT_SECRET_PATH = "credentials/client_secret.json"
TOKEN_PATH = "credentials/token.json"
OUTPUT_DIR = "pages/email"
MAX_MESSAGES = 50


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
    body_text = ""
    attachments = []

    def walk(part):
        nonlocal body_text
        mime_type = part.get("mimeType", "")
        filename = part.get("filename", "")
        body = part.get("body", {})

        if filename:
            attachments.append(filename)
        elif mime_type == "text/plain" and "data" in body:
            decoded = base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="replace")
            body_text += decoded

        for sub_part in part.get("parts", []):
            walk(sub_part)

    walk(payload)
    return body_text.strip(), attachments


def yaml_list(items):
    if not items:
        return "[]"
    quoted = [f'"{item.replace(chr(34), chr(92) + chr(34))}"' for item in items]
    return "[" + ", ".join(quoted) + "]"


def yaml_str(s):
    return '"' + s.replace('"', '\\"').replace("\n", " ").strip() + '"'


def safe_filename(msg_id):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", msg_id)


def main():
    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = service.users().messages().list(userId="me", maxResults=MAX_MESSAGES).execute()
    messages = results.get("messages", [])

    if not messages:
        print("No messages found -- nothing to ingest.")
        return

    written = 0
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        body, attachments = extract_body_and_attachments(msg["payload"])

        subject = headers.get("Subject", "(no subject)")
        from_addr = headers.get("From", "")
        to_addr = headers.get("To", "")
        date = headers.get("Date", "")
        labels = msg.get("labelIds", [])
        thread_id = msg.get("threadId", "")
        msg_id = msg.get("id", "")

        frontmatter = "\n".join([
            "---",
            "type: email",
            f"gmail_thread_id: {yaml_str(thread_id)}",
            f"gmail_msg_id: {yaml_str(msg_id)}",
            f"from: {yaml_str(from_addr)}",
            f"to: {yaml_list([to_addr] if to_addr else [])}",
            f"subject: {yaml_str(subject)}",
            f"date: {yaml_str(date)}",
            f"labels: {yaml_list(labels)}",
            f"has_attachments: {'true' if attachments else 'false'}",
            f"attachments: {yaml_list(attachments)}",
            "---",
        ])

        page_content = f"{frontmatter}\n{body}\n"

        out_path = os.path.join(OUTPUT_DIR, f"{safe_filename(msg_id)}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page_content)

        written += 1
        print(f"  wrote {out_path}  ({subject[:60]})")

    print(f"\nDone. {written} email pages written to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
