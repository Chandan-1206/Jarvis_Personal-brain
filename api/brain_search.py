import os

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL")


def _connect():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def _build_or_query(query: str) -> str:
    words = [w for w in query.replace('"', ' ').split() if w.upper() not in ("OR", "AND")]
    if not words:
        return query
    return " | ".join(words)


def search_pages(query: str, page_type: str = None, limit: int = 15):
    conn = _connect()
    cur = conn.cursor()

    or_query = _build_or_query(query)

    sql = """
        SELECT id, page_type, title, frontmatter,
               ts_headline('english', body, to_tsquery('english', %(q)s),
                           'MaxWords=40, MinWords=15') AS snippet,
               ts_rank(to_tsvector('english', search_text), to_tsquery('english', %(q)s)) AS rank
        FROM brain_pages
        WHERE to_tsvector('english', search_text) @@ to_tsquery('english', %(q)s)
    """
    params = {"q": or_query, "limit": limit}
    if page_type:
        sql += " AND page_type = %(page_type)s"
        params["page_type"] = page_type
    sql += " ORDER BY rank DESC LIMIT %(limit)s"

    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "id": row["id"],
            "page_type": row["page_type"],
            "title": row["title"],
            "snippet": row["snippet"],
            "frontmatter": row["frontmatter"],
        }
        for row in rows
    ]


def get_page(page_id: str):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, page_type, title, frontmatter, body FROM brain_pages WHERE id = %s",
        (page_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def get_thread_emails(thread_id: str):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, title, frontmatter, body
        FROM brain_pages
        WHERE page_type = 'email' AND frontmatter->>'gmail_thread_id' = %s
        ORDER BY id
        """,
        (thread_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_files_linked_to_thread(thread_id: str):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, title, frontmatter, body
        FROM brain_pages
        WHERE page_type = 'file' AND frontmatter->>'linked_email_thread_id' = %s
        """,
        (thread_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]
