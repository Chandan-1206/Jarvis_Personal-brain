"""
Stage 5.2 -- Gemini tool-calling reasoning loop.

Run locally to test:
    python scripts/gemini_chat_test.py "What jobs have I applied to?"

Requires GEMINI_API_KEY and DATABASE_URL env vars.
"""

import sys
import json
import time
import re

from google import genai
from google.genai import types
from google.genai import errors

import brain_search

MODEL = "gemini-3.1-flash-lite"

SYSTEM_INSTRUCTION = """You are Personal Brain, an assistant that answers
questions using ONLY the search tools provided -- never from general
knowledge or assumption. You have access to a person's email (Gmail) and
files (Google Drive) via these tools.

Rules:
- Always search before answering. Never guess at facts.
- Be EFFICIENT with tool calls -- you are rate-limited. Prefer ONE broad,
  well-chosen search_pages call over many narrow single-word searches.
  Do not repeat near-duplicate queries (e.g. "application" then
  "interview" then "role" then "take home", or slight rewordings of the
  same company name) -- pick the most distinctive terms from the question
  and search once or twice, then work with what you get back.
- For questions asking about MULTIPLE items (e.g. "what jobs have I
  applied to" -- plural), your FIRST search should be broad and generic
  (e.g. just "job application" or "applied") to survey everything, not
  narrowly worded around one sub-detail like "take-home" or "submission"
  -- a narrow first query biases results toward one match and hides the
  others. Only narrow down on later searches once you know what companies
  exist.
- HARD RULE: call search_pages AT MOST 3 times total for a single
  question. After that, STOP searching and answer using whatever you
  found -- even if incomplete. If a company/topic didn't turn up after
  2 different phrasings, say "I couldn't find anything about X" rather
  than trying a 4th, 5th, 6th variation of the same search.
- For questions that plausibly involve both an email thread AND a related
  file (e.g. "did I send X the contract", "what's my status including the
  submission file"), use get_thread_emails and get_files_linked_to_thread
  together -- that is the whole point of this tool: combining sources.
- CRITICAL DISTINCTION: a file existing in Drive is NOT the same as it
  being sent/submitted. Only say something was "submitted" or "sent" if
  an email actually confirms that action (e.g. an email with the file
  attached, or text saying it was sent). If you only found a file in
  Drive with no corresponding email, say something like "I found a file
  that looks like it might be your submission, but I don't see an email
  confirming it was actually sent" -- do not say "you submitted" as fact.
- If you don't find something after searching, say so plainly. Do not
  fabricate an answer. "I don't know" / "I couldn't find that" is correct
  and expected when the data isn't there.
- Cite what you found concisely (e.g. "per the email from X on [date]").
- Be conversational, not a raw dump of search results.
"""

TOOLS = [
    {
        "name": "search_pages",
        "description": "Full-text search across all emails and files. Use this first for almost any query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms"},
                "page_type": {"type": "string", "enum": ["email", "file"], "description": "Optional filter"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_page",
        "description": "Fetch the full content of one specific page by its id (from a prior search result).",
        "parameters": {
            "type": "object",
            "properties": {"page_id": {"type": "string"}},
            "required": ["page_id"],
        },
    },
    {
        "name": "get_thread_emails",
        "description": "Fetch all emails in a Gmail thread, to see the full back-and-forth (e.g. did someone reply).",
        "parameters": {
            "type": "object",
            "properties": {"thread_id": {"type": "string", "description": "gmail_thread_id from a page's frontmatter"}},
            "required": ["thread_id"],
        },
    },
    {
        "name": "get_files_linked_to_thread",
        "description": "Fetch Drive files that were cross-linked to a given email thread (e.g. an attachment or shared file). Use this together with get_thread_emails for cross-source questions.",
        "parameters": {
            "type": "object",
            "properties": {"thread_id": {"type": "string"}},
            "required": ["thread_id"],
        },
    },
]

FUNCTIONS = {
    "search_pages": brain_search.search_pages,
    "get_page": brain_search.get_page,
    "get_thread_emails": brain_search.get_thread_emails,
    "get_files_linked_to_thread": brain_search.get_files_linked_to_thread,
}


def _generate_with_retry(client, model, contents, config, max_retries=5):
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except errors.ServerError as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(f"  [retrying after server error] waiting {wait}s...")
            time.sleep(wait)
        except errors.ClientError as e:
            if getattr(e, "code", None) != 429 or attempt == max_retries - 1:
                raise
            wait = 20
            m = re.search(r"'retryDelay': '(\d+)s'", str(e))
            if m:
                wait = int(m.group(1)) + 2
            print(f"  [rate limited] waiting {wait}s before retry...")
            time.sleep(wait)


def ask(question: str, verbose: bool = True):
    client = genai.Client()

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=[types.Tool(function_declarations=TOOLS)],
    )

    contents = [types.Content(role="user", parts=[types.Part(text=question)])]

    for turn in range(8):
        response = _generate_with_retry(client, MODEL, contents, config)

        candidate = response.candidates[0]
        function_calls = [
            part.function_call for part in candidate.content.parts if part.function_call
        ]

        if not function_calls:
            final_text = "".join(
                part.text for part in candidate.content.parts if part.text
            )
            return final_text

        contents.append(candidate.content)

        function_response_parts = []
        for fc in function_calls:
            fn = FUNCTIONS.get(fc.name)
            args = dict(fc.args) if fc.args else {}

            if verbose:
                print(f"  [tool call] {fc.name}({args})")

            try:
                result = fn(**args) if fn else {"error": f"unknown tool {fc.name}"}
            except Exception as e:
                result = {"error": str(e)}

            function_response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name,
                        response={"result": result},
                    )
                )
            )

        contents.append(types.Content(role="user", parts=function_response_parts))

    return "(gave up after too many tool-call rounds -- something's looping)"


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "What jobs have I applied to?"
    print(f"Q: {question}\n")
    answer = ask(question)
    print(f"\nA: {answer}")
