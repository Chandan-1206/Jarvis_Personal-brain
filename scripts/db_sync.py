"""
Stage 4.5 -- Populate a simple, app-queryable table in Supabase.

Run locally:
    python scripts/db_sync.py

WHY THIS EXISTS (see SPEC.md architecture notes):
GBrain own Postgres schema (chunks, embeddings, entity graph) is
internal machinery not meant for hand-written SQL, and Vercel Python
functions can't shell out to GBrain Bun-based CLI at request time
anyway. So this script writes a second, simple table -- brain_pages --
into the SAME Supabase database that GBrain uses. GBrain own import
(already run via gbrain migrate --to supabase) remains the actual
required-by-the-assignment storage. This table is purely a practical
read-path for the deployed FastAPI app search tools.

Requires DATABASE_URL env var (the same Supabase connection string used
for gbrain migrate --to supabase), and psycopg2 installed.
"""

import glob
import os
import re

import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
PAGES_DIR = "pages"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS brain_pages (
    id TEXT PRIMARY KEY,
    page_type TEXT NOT NULL,
    title TEXT,
    frontmatter JSONB NOT NULL,
    body TEXT NOT NULL,
    search_text TEXT GENERATED ALWAYS AS (
        coalesce(title, '') || ' ' || coalesce(body, '')
    ) STORED
);
CREATE INDEX IF NOT EXISTS brain_pages_search_idx
    ON brain_pages USING GIN (to_tsvector('english', search_text));
"""

UPSERT_SQL = """
INSERT INTO brain_pages (id, page_type, title, frontmatter, body)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    page_type = EXCLUDED.page_type,
    title = EXCLUDED.title,
    frontmatter = EXCLUDED.frontmatter,
    body = EXCLUDED.body;
"""


def parse_page(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    fm_text = parts[1]
    body = parts[2].strip()

    fm = {}
    for line in fm_text.strip().splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if value.startswith("[") and value.endswith("]"):
            items = re.findall(r'"([^"]*)"', value)
            fm[key] = items
        elif value.startswith('"') and value.endswith('"'):
            fm[key] = value[1:-1]
        elif value in ("true", "false"):
            fm[key] = value == "true"
        elif value == "null":
            fm[key] = None
        else:
            fm[key] = value

    page_type = fm.get("type", "unknown")
    if page_type == "email":
        title = fm.get("subject", "(no subject)")
    else:
        title = fm.get("name", "(unnamed file)")

    page_id = os.path.splitext(os.path.basename(path))[0]

    return {
        "id": page_id,
        "page_type": page_type,
        "title": title,
        "frontmatter": fm,
        "body": body,
    }


def main():
    if not DATABASE_URL:
        print("ERROR: set DATABASE_URL env var first, e.g.")
        print('  $env:DATABASE_URL = "postgresql://...supabase..."')
        return

    import json

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print("Ensuring brain_pages table exists...")
    cur.execute(CREATE_TABLE_SQL)
    conn.commit()

    paths = glob.glob(os.path.join(PAGES_DIR, "**", "*.md"), recursive=True)
    print(f"Found {len(paths)} local markdown pages to sync.")

    written = 0
    for path in paths:
        page = parse_page(path)
        if not page:
            print(f"  skipped (could not parse frontmatter): {path}")
            continue

        cur.execute(UPSERT_SQL, (
            page["id"],
            page["page_type"],
            page["title"],
            json.dumps(page["frontmatter"]),
            page["body"],
        ))
        written += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nDone. {written} pages synced to brain_pages in Supabase.")


if __name__ == "__main__":
    main()
