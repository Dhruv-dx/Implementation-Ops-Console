# OMAP® Admin Dashboard (Everything-Dashboard)

A unified admin console that brings four internal tools behind one UI. The home
screen shows four cards; each opens a full sub-dashboard:

| Card | What it does | Ported from |
|---|---|---|
| **Chats Review** | Browse agent chat sessions and their router traces (turns, tool calls, tokens, latency) per organization, in Dev / QA / UAT / Prod | `projects/chats per org` |
| **Tickets Automation** | Pull admin notes (Jira for Prod, MongoDB for Dev / QA / UAT) by org, agent and/or date, resolve session-log URLs, export to Excel / SharePoint / timesheet copy | `projects/POC/Jira-Ticket-Automation` |
| **OSD → IMAP** | Copy "Admin Note Created" tickets from OSD into IMAP for a date, with dedup + status transition (supports dry run) | `projects/POC/T2B` |
| **Close Tickets** | Find open tickets by summary pattern, select, and bulk-close with concurrent workers | `projects/POC/close tickets` |

## Run

```bash
pip install -r requirements.txt
copy .env.example .env   # then fill in credentials
python app.py            # http://127.0.0.1:8000
```

Everything — the frontend and all four modules' APIs — runs from this one process
on one port. There is no separate server per module and no reverse proxy; the
original four POC projects are no longer used at runtime (their logic was ported
into `services/`).

If port 8000 is already taken, either free it (`netstat -ano | findstr :8000` on
Windows, then stop that process) or change the port in the `uvicorn.run(...)` call
at the bottom of `app.py`.

## Structure

```
app.py                        # FastAPI entry point + JSON API routes + static file serving
services/
  jira_common.py              # Shared Jira auth / paginated JQL search / transitions
  mongo_common.py             # Per-environment MongoDB connections (chats + traces collections)
  chats.py                    # Chats Review logic (sessions + traces)
  ticket_automation.py        # Tickets Automation pipeline (Jira / MongoDB) + Excel generator
  sharepoint.py               # Push Ticket Automation rows into the shared SharePoint Excel
  osd_imap.py                 # OSD -> IMAP copier (with dry-run support)
  close_tickets.py            # Pattern search + concurrent bulk close
static/
  index.html                  # Single-page shell (hash routing: #/chats, #/tickets-automation, #/osd-imap, #/close-tickets)
  app.js                       # All view logic, API calls, rendering
  style.css                    # Dark admin theme + light colorful Chats Review / Traces cards
```

## Navigation

- The topbar is a 3-column layout: brand (left) · **Home** link (dead-center,
  bold, highlighted purple when you're on the home screen) · Back button (right,
  only shown once you're inside a module).
- Every navigable element — the four home cards, the Home link, and the Back
  button — is a real `<a href="#/...">`, not a `<button onclick="...">`. That
  means **Ctrl/Cmd+click** and **middle-click** open a module in a new tab, and
  right-click gives the normal "open in new tab / copy link" browser menu. A
  plain left-click still navigates in the same tab via the app's hash router.
- Routing is entirely client-side hash routing (`#/chats`, `#/tickets-automation`,
  `#/osd-imap`, `#/close-tickets`) handled in `app.js`; there's no server-side
  page per module.

## Motion

Small, purposeful animations throughout (150–300ms, transform/opacity only):
staggered fade-in for the home cards and stat tiles, icon lift on card hover,
press feedback on buttons, a smooth expand/collapse for chat session cards
(instead of an instant toggle), staggered table-row reveals, and toasts that
fade/slide out instead of disappearing abruptly. All of it is disabled
automatically when the OS-level `prefers-reduced-motion` setting is on.

## Environments

Chats Review and Tickets Automation share the same environment selector
(Dev / QA / UAT / Prod pills). The selected environment decides which MongoDB is
queried; changing it clears the current results so data from two environments is
never mixed.

## Notes on Chats Review

Chats Review has a left side nav with two tabs, sharing one form (environment,
Organization ID, optional Session ID):

- **Chats** - session cards in a light, colorful style (distinct from the rest of
  the dark admin theme) to match the original product's conversation view:
  session ID header, calendar/message-count/category/sentiment/version meta row,
  purple "User" / pink "Assistant" message bubbles, a source-page badge, and green
  "Queries" / orange "Files Searched" tag grids.
- **Traces** - one expandable card per document in the `chats_traces` collection
  (latest 100, newest first; use Session ID to narrow down). The header shows
  turns, model, agent and version, total tokens, total latency, tool-call count and
  any error / sandbox badges. Expanded, each turn lists model, provider, stop
  reason, latency, the token breakdown, tool-loop iterations, queries, and every
  tool call (success / failed, latency, input and output). Steps, reasoning,
  provider metadata and channel / device metadata are collapsible JSON blocks.

## Notes on Tickets Automation

- **Prod** reads "Admin Note" tickets from Jira, filterable by Organization ID,
  Organization name and/or Agent name. Session-log URLs are resolved from the Prod
  chats collection.
- **Dev / QA / UAT** do not raise notes in Jira. They read the `note` field of
  sessions in that environment's chats collection instead. Chat documents only
  store `organization_id` and `agent_id` (no names), so the filters are
  Organization ID and Agent ID (the Agent input switches to "Agent ID"), and
  Organization name is Prod-only. Each row's "Ticket ID" is the session ID, and the
  Status column shows `note_status`.
- At least one filter **or a date range** is required. A date-only run picks every
  admin note created in that range (on Prod: every "Admin Note Created" ticket on
  the board). Dates are applied in the query itself, not after fetching.
- Results can be copied, downloaded as `.xlsx` (named with the environment and
  filter, e.g. `uat_2026-09-28_to_2026-09-28_sessions.xlsx`), or appended to the
  shared SharePoint workbook (existing tickets are skipped).

## Editing the frontend

`static/style.css` and `static/app.js` are loaded with a cache-busting query
string (`?v=N`) so browsers don't serve a stale copy after an edit. If you change
either file and don't see the update, bump the `v=` number in
`static/index.html` and hard-refresh (Ctrl+Shift+R).

## API

`env` is one of `dev`, `qa`, `uat`, `prod` (default `prod`).

- `GET  /api/chats/sessions?organization_id=&session_id=&env=`
- `GET  /api/chats/traces?organization_id=&session_id=&env=` - latest 100 traces
- `POST /api/ticket-automation/process` - `{org_id?, org_name?, agent_name?, date_from?, date_to?, env?}`
- `POST /api/ticket-automation/download` - same body, returns `.xlsx`
- `POST /api/ticket-automation/sharepoint` - same body, appends new rows to the SharePoint workbook
- `POST /api/osd-imap/copy` - `{date, dry_run, ticket_numbers?}`
- `POST /api/close-tickets/find` - `{pattern}`
- `POST /api/close-tickets/close` - `{keys: [...], workers}`

## Environment (`.env`)

See `.env.example`. Jira credentials are shared by three modules; MongoDB is used
by Chats Review and Tickets Automation (SharePoint uses the `AZURE_*` and
`SHAREPOINT_EXCEL_URL` variables).

MongoDB is configured per environment with `_dev`, `_qa`, `_uat` and `_prod`
suffixes (Prod also falls back to the unsuffixed names):

```
mongo_connection_string_<env>     # required for every env
mongo_database_<env>              # falls back to mongo_database
mongo_collection_<env>            # chats collection; falls back to mongo_collection
mongo_traces_collection_<env>     # optional, defaults to chats_traces (same database)
SESSION_URL_BASE_<ENV>            # optional chat-log URL base for Tickets Automation links; defaults to the Prod platform URL
```

> Note: do not commit `.env` — the original POC folders contain live tokens in
> plaintext; those should be rotated and never copied into version control.
