# OMAP® Admin Dashboard (Everything-Dashboard)

A unified admin console that brings four internal tools behind one UI. The home
screen shows four cards; each opens a full sub-dashboard:

| Card | What it does | Ported from |
|---|---|---|
| **Chats Review** | Browse agent chat sessions per organization (conversation threads, sentiment, category, KB usage) | `projects/chats per org` |
| **Tickets Automation** | Pull admin-note tickets from Jira, resolve session-log URLs from MongoDB, export to Excel / timesheet copy | `projects/POC/Jira-Ticket-Automation` |
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
  mongo_common.py             # Shared MongoDB connection
  chats.py                    # Chats Review logic
  ticket_automation.py        # Tickets Automation pipeline + Excel generator
  osd_imap.py                 # OSD -> IMAP copier (with dry-run support)
  close_tickets.py            # Pattern search + concurrent bulk close
static/
  index.html                  # Single-page shell (hash routing: #/chats, #/tickets-automation, #/osd-imap, #/close-tickets)
  app.js                       # All view logic, API calls, rendering
  style.css                    # Dark admin theme + light colorful Chats Review cards
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

## Notes on Chats Review

The Chats Review module renders session cards in a light, colorful card style
(distinct from the rest of the dark admin theme) to match the original product's
conversation view — session ID header, calendar/message-count/category/sentiment/
version meta row, purple "User" / pink "Assistant" message bubbles, a source-page
badge, and green "Queries" / orange "Files Searched" tag grids.

## Editing the frontend

`static/style.css` is loaded with a cache-busting query string
(`style.css?v=N`) so browsers don't serve a stale copy after an edit. If you
change `style.css` and don't see the update, bump the `v=` number in
`static/index.html` and hard-refresh (Ctrl+Shift+R).

## API

- `GET  /api/chats/sessions?organization_id=&session_id=`
- `POST /api/ticket-automation/process` — `{org_id, date_from?, date_to?}`
- `POST /api/ticket-automation/download` — same body, returns `.xlsx`
- `POST /api/osd-imap/copy` — `{date, dry_run}`
- `POST /api/close-tickets/find` — `{pattern}`
- `POST /api/close-tickets/close` — `{keys: [...], workers}`

## Environment (`.env`)

See `.env.example`. Jira credentials are shared by three modules; MongoDB is
used by Chats Review and Tickets Automation.

> Note: do not commit `.env` — the original POC folders contain live tokens in
> plaintext; those should be rotated and never copied into version control.
