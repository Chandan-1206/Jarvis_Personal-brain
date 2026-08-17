# Personal Brain — Spec

Owner: Chandan Agarwal <br>
Assignment: SkillLayer SDE I take-home

## 1. Goal

A conversational agent that answers natural-language questions by pulling
facts from at least two connected personal tools and reasoning across them
in a single answer — not a raw search dump.

## 2. Scope decisions

| Decision | Choice | Why |
|---|---|---|
| Connectors | Gmail + Google Drive | Both Tier 2 example queries need exactly this pair (thread status + attachment matching). |
| Account | Brand-new throwaway Google test account | No real personal data touched. Populated with realistic synthetic data (job applications, take-home submissions, a contract sent to a fictional "Vanisha"). |
| Data store | GBrain (github.com/garrytan/gbrain), standalone CLI mode only | Required by the assignment. We use `gbrain init --pglite`, `gbrain import`, `gbrain search`/`gbrain query` only — no agent-driven install, no cron "dream cycle," no credential gateway. Installed and run on your local machine, not in the build sandbox. |
| App stack | Python: FastAPI backend + plain HTML/vanilla JS chat frontend (no build step, no TS), deployed to Vercel (Python serverless functions) | Per assignment doc: deploy on Vercel. Matches your FastAPI experience. |
| Data store hosting | GBrain running on its Postgres + pgvector engine, hosted on Supabase free tier (not local PGLite) | Vercel functions are stateless/ephemeral — no persistent local disk, no Bun runtime for the GBrain CLI at request time. GBrain's own docs specify Postgres+Supabase as the mode for exactly this (shared/hosted, non-single-machine) use case. `gbrain import` is run locally, once per data refresh, against this same DB — not per-request. |
| Data store reads at runtime | FastAPI queries the Supabase Postgres DB directly (plain SQL) for its search tools | Vercel's Python functions can't shell out to GBrain's Bun-based CLI, so live queries hit the same underlying DB GBrain wrote to, directly. |
| Reasoning model | Google Gemini API (`gemini-2.5-flash`), tool-calling, via `google-genai` SDK | Genuinely free tier (no credit card), includes function calling. Switched from Claude API after hitting real cost barriers with both OpenAI (embeddings) and Anthropic (reasoning) requiring paid credits with no reliable free allowance as of Aug 2026. Not a compromise on capability — Gemini's function-calling supports the same tool-loop pattern. |
| Auth | Google OAuth 2.0, readonly scopes (`gmail.readonly`, `drive.readonly`) | Read-only is all we need; smaller blast radius on the test account. |

## 3. Architecture

```
[Test Gmail/Drive account]
        │  OAuth (readonly)
        ▼
[Ingest scripts, Python — run locally]  ──normalize──▶  [GBrain pages: markdown + frontmatter]
                                                                   │
                                                       gbrain import (local CLI → remote DB)
                                                                   ▼
                                              [GBrain DB — Postgres + pgvector, hosted on Supabase]
                                                                   ▲
                                                        direct SQL reads (psycopg2/asyncpg)
                                                                   │
[FastAPI on Vercel, /chat endpoint] ──tool calls──▶ [Claude API (anthropic SDK), tool-calling agent loop]
        ▲                                                     │
        │                                            search_emails / search_files /
        │                                            get_thread / get_file tools
        ▼
[Static HTML + vanilla JS chat page, served by FastAPI]
```

Note: `gbrain import` (writing) happens locally against the Supabase DB.
The deployed Vercel app only reads (no gbrain CLI at request time — Vercel's
Python runtime can't execute GBrain's Bun-based binary).

Key point for Tier 2 (cross-source): the Claude tool-loop can call the
Gmail-backed tool and the Drive-backed tool within the same answer, then
synthesize one response citing both.

## 4. Data model (GBrain pages)

Two custom page types, written as markdown files with frontmatter,
importable by `gbrain import`:

**`email/<id>.md`**
```
---
type: email
gmail_thread_id: string
gmail_msg_id: string
from: string
to: [string]
subject: string
date: ISO8601
labels: [string]
has_attachments: boolean
attachments: [string]   # filenames, empty list if none
---
<plain-text body>
```

**`file/<id>.md`**
```
---
type: file
drive_file_id: string
name: string
mime_type: string
created: ISO8601
modified: ISO8601
owner: string
shared_with: [string]
linked_email_thread_id: string | null   # heuristic match, see §6
---
<extracted text content, or summary for binary files>
```

Cross-linking (email ↔ file) is done at ingest time via:
- Gmail attachment → matching Drive file (by filename + nearby timestamp), OR
- explicit Drive share event to an email participant, OR
- shared filename/keyword mention in email body.

This is what makes "did I send Vanisha the contract, and did she reply" answerable:
the tool layer can pull the thread AND the matched Drive file in one turn.

## 5. Synthetic dataset (test account)

Designed specifically to exercise every example query:

- **Job applications (3–4 companies):** application email sent → confirmation
  reply → (for one) a take-home assignment email → a submission email with a
  Drive-linked file → (for one) a rejection or an interview-scheduling reply.
  Statuses should differ per company (applied / interviewing / rejected / no response).
- **Contract thread with "Vanisha":** an email sending a contract draft
  (Drive file attached/linked) + a reply from Vanisha (for at least one; leave
  a second contact with **no reply**, to test the negative case honestly).
- **Misc noise:** a few unrelated emails/files/calendar-adjacent content so
  retrieval isn't trivially "return everything."
- **Unread Slack DMs / calendar** are NOT in scope since we're using
  Gmail+Drive only — Tier 1 examples will be adapted to Gmail/Drive-native
  equivalents (see §6).

## 6. Target queries (acceptance criteria)

**Tier 1 (single-source, conversational)**
1. "Find the email from Stripe about the failed payment." *(adapted: we'll seed a Stripe-style email instead of assuming it's already there)*
2. "What files did I edit in Drive this week?"
3. "List my unread/unresponded application emails."

**Tier 2 (cross-source)** <br>
4. "What jobs have I applied to, and what's my status on each, including my take-home submission?" <br>
5. "Did I ever send Vanisha the contract draft, and did she reply?"

Each query must be answered live, in the chat UI, grounded in the actual
seeded data (no fabrication), citing which source(s) it pulled from.

## 7. Out of scope (for this pass)

- Slack/Notion connectors
- Write actions (sending email, editing Drive files)
- GBrain's cron/"dream cycle"/agent-autonomous features
- Multi-user auth beyond the single test account

## 8. Milestones (traceable stages)

1. Scaffold + Vercel deploy skeleton (Python serverless function)
2. Gmail connector + ingest → GBrain pages
3. Drive connector + ingest → GBrain pages + cross-linking
4. GBrain local store bring-up (`gbrain init --pglite`, import, verify search)
5. Tool-calling reasoning layer (Claude API + search tools)
6. Chat UI
7. Tier 1 validation against real seeded data
8. Tier 2 validation against real seeded data
9. Polish, README, demo recording

## 9. Open questions / risks (resolved during build)

- GBrain's default schema pack (`gbrain-base-v2`) doesn't have `email`/`file`
  types out of the box — we may need `gbrain schema` to add them, or fold
  data into the closest existing types (`email` type does exist; `file`
  may need to be a custom pack). Resolve in Milestone 4.
- **Resolved**: GBrain's file collector respects `.gitignore` when scanning
  a directory for markdown to import. Since `pages/` was gitignored (to
  avoid committing generated files), `gbrain import` silently found 0
  files. Fix: temporarily un-ignore `pages/` during import, re-add after.
  Also confirmed GBrain's import does not require flat directories —
  `pages/email/` and `pages/file/` subfolders both worked once the
  gitignore issue was fixed.
- **OpenAI cost note (resolved)**: new OpenAI accounts no longer reliably
  get free credits, and adding billing requires a $5 minimum prepay.
  Since this is a student project, we run GBrain in **keyless mode**
  (`--no-embedding`, `gbrain import --no-embed`) — keyword/BM25 search
  only, no vector embeddings. Confirmed sufficient for this dataset size
  (35 pages, distinctive terms like company/person names) via live test:
  `gbrain search "Vanisha contract"` correctly ranked the actual contract
  thread top-2 despite typos/paraphrase in the query.
- **Resolved**: `gemini-2.5-flash` was deprecated for new API accounts as
  of Aug 2026 (Google ships new model generations fast). Switched to the
  `gemini-flash-latest` alias, which auto-points at the current stable
  Flash model, to avoid re-hitting this on the next Google release.
- **Milestone 5 first live test (Stage 5.2)**: query "Did I ever send
  Vanisha the contract draft, and did she reply?" correctly triggered
  `search_pages` → `get_thread_emails` → `get_files_linked_to_thread`
  across both sources, and produced a grounded answer citing the actual
  filename, date, and reply content.
- **Resolved (important)**: `plainto_tsquery`/`websearch_to_tsquery` both
  require ALL words in a multi-word query to match (AND semantics) unless
  the query text explicitly contains the literal word "OR" -- Gemini's
  natural multi-word queries were silently returning zero results. Fixed
  by having `search_pages` build an OR'd `to_tsquery` internally from the
  input words, so any term matching counts (ranked by how many match).
  This was the root cause of several "I couldn't find anything" false
  negatives during testing -- not a data problem, a query-semantics bug.
- **Stage 5 fully validated**: "What jobs have I applied to, and what's
  my status on each, including my take-home submission?" now correctly
  surfaces 7 real companies (SkillLayer, Amazon, Adani, bp, SquadStack,
  Wisdom AI, Juspay) each with accurate, specific status, in a single
  efficient search call -- genuine Tier 2 cross-source reasoning working
  end-to-end.
- **Runtime query decision**: GBrain's actual Postgres schema (chunks,
  embeddings, entity edges) is internal/undocumented for direct SQL
  querying, and reverse-engineering it precisely isn't a good use of time
  under deadline. Resolution: `gbrain import` still runs for real
  (satisfies "store data in GBrain" literally, using GBrain's own
  pipeline), but our FastAPI app's search tools read from a second,
  simple table we control in the *same* Supabase database, populated by
  our own ingest scripts. This keeps runtime retrieval logic
  understandable and debuggable while still genuinely using GBrain as
  required.

## 10. Stage 7-8 validation (live, on deployed Vercel URL)

All queries from §6 tested live against the deployed app, Aug 17 2026:

**Tier 1**
- "Find the email from Vanisha about the SkillLayer application" → correct, single email, right date/content. ✅
- "What files did I edit in Drive this week?" → correctly identified the one file modified this week. ✅
- "List my unread or unresponded application emails" → listed 6 companies with confirmation-received-no-followup status, plus honestly flagged a borderline case (Army internship invite) as relevant-but-not-a-job-application. ✅

**Tier 2**
- "What jobs have I applied to, and what's my status on each, including my take-home submission?" → correctly surfaced all 7 companies with accurate individual statuses, AND correctly hedged on the take-home file ("I do not see an email confirming that you have actually sent or submitted this specific file") rather than asserting submission as fact. ✅
- "Did I ever send Vanisha the contract draft, and did she reply?" → correct filename, date, and accurate paraphrase of her reply content. ✅

All answers grounded in actual seeded data, no fabrication observed. Both
tiers fully satisfied per the assignment's acceptance criteria.
