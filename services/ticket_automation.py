"""Tickets Automation — Jira admin-note tickets enriched with session-log URLs,
exportable to Excel (ported from Jira-Ticket-Automation)."""
import io
import os
import re
from datetime import datetime, time, timedelta

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from . import jira_common
from .mongo_common import DEFAULT_ENV, MongoConfigError, get_collection, normalize_env

SESSION_URL_BASE = "https://platform.dxfactor.com/member-concierge/chat-log"

COLUMNS = ["Ticket ID", "Session ID", "Session URL", "Note", "Root Cause", "Recommended Fix", "Fixed"]
COL_WIDTHS = [15, 35, 60, 50, 30, 30, 12]
HEADER_BG = "1E3A5F"
ADMIN_NOTE_SUMMARY = "Admin Note Created"

SESSION_ID_RE = re.compile(r"(session_\S+)")
DIRECT_DOC_ID_RE = re.compile(r"chat-log\?id=([0-9a-fA-F]{24})")

BLOCK_NODE_TYPES = (
    "doc", "paragraph", "heading", "bulletList", "orderedList", "listItem",
    "table", "tableRow", "tableCell", "tableHeader", "panel", "blockquote", "rule",
)


def _extract_text_from_adf(node) -> str:
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    if node.get("type") == "hardBreak":
        return "\n"
    parts = [_extract_text_from_adf(child) for child in node.get("content", [])]
    separator = "\n" if node.get("type") in BLOCK_NODE_TYPES else ""
    return separator.join(p for p in parts if p)


def _parse_description(raw, summary: str = "") -> dict:
    text = _extract_text_from_adf(raw) if isinstance(raw, dict) else (raw or "")
    session = re.search(r"Conversation ID:\s*(\S+)", text)
    if not session:
        session = SESSION_ID_RE.search(summary or "")
    org = re.search(r"Organization ID:\s*(\d+)", text)
    org_name = re.search(r"Organization:\s*(.+)", text)
    agent = re.search(r"Agent:\s*(.+)", text)
    note_match = re.search(r"Admin Note\s*\n+(.*?)\n*(?:Conversation Logs|$)", text, re.DOTALL | re.IGNORECASE)
    if not note_match:
        note_match = re.search(r"Note Content\s*\n+(.*?)\n*(?:Conversation Link|Conversation Logs|$)", text, re.DOTALL | re.IGNORECASE)
    direct_doc = DIRECT_DOC_ID_RE.search(text)
    return {
        "session_id": session.group(1).strip() if session else "",
        "org_id": org.group(1).strip() if org else "",
        "org_name": org_name.group(1).strip() if org_name else "",
        "agent_name": agent.group(1).strip() if agent else "",
        "note": note_match.group(1).strip() if note_match else "",
        "direct_doc_id": direct_doc.group(1) if direct_doc else "",
    }


def _org_or_agent_matches(org_id: str, org_name: str, agent_name: str, parsed: dict) -> bool:
    if org_name and parsed.get("org_name", "").strip().lower() != org_name.strip().lower():
        return False
    if parsed.get("org_id"):
        return not org_id or parsed["org_id"] == org_id
    if agent_name:
        return parsed.get("agent_name", "").strip().lower() == agent_name.strip().lower()
    return not org_id and not org_name


def _matches(ticket: dict, org_id: str, org_name: str, agent_name: str, date_from, date_to, parsed: dict) -> bool:
    if not _org_or_agent_matches(org_id, org_name, agent_name, parsed):
        return False
    if date_from or date_to:
        created_str = ticket.get("fields", {}).get("created", "")
        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00")).date()
        except Exception:
            return False
        if date_from and created < date_from:
            return False
        if date_to and created > date_to:
            return False
    return True


def _get_document_ids(session_ids: list[str], env: str = DEFAULT_ENV) -> dict[str, str]:
    if not session_ids:
        return {}
    docs = get_collection(env).find({"session_id": {"$in": session_ids}}, {"_id": 1, "session_id": 1})
    return {doc["session_id"]: str(doc["_id"]) for doc in docs}


def _session_url_base(env: str) -> str:
    """Per-env override via SESSION_URL_BASE_<ENV>; defaults to the prod platform URL."""
    return os.getenv(f"SESSION_URL_BASE_{env.upper()}") or SESSION_URL_BASE


def _note_texts(notes) -> list[str]:
    """The note field may be a string, or a list of strings / dicts."""
    if not notes:
        return []
    if isinstance(notes, (str, dict)):
        notes = [notes]
    texts = []
    for item in notes:
        if isinstance(item, dict):
            item = next((item[k] for k in ("note", "text", "content", "message") if item.get(k)), "")
        text = str(item or "").strip()
        if text:
            texts.append(text)
    return texts


def _int_filter(value: str, label: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise MongoConfigError(f"{label} must be a number on Dev / QA / UAT, got '{value}'")


def _process_mongo(org_id: str, org_name: str, agent_name: str, date_from, date_to, env: str) -> dict:
    """dev/qa/uat: admin notes aren't raised in Jira, so read them straight from
    the chats collection (sessions with a non-empty `note`). Chat documents only
    carry organization_id / agent_id, not names, so those are the filters here;
    the "Agent" input is treated as an agent ID."""
    if org_name:
        raise MongoConfigError(
            f"Organization name isn't stored on {env} chat documents; use Organization ID instead"
        )
    query: dict = {"note": {"$exists": True, "$nin": [None, ""]}}
    if org_id:
        query["organization_id"] = _int_filter(org_id, "Organization ID")
    if agent_name:
        query["agent_id"] = _int_filter(agent_name, "Agent ID")
    created = {}
    if date_from:
        created["$gte"] = datetime.combine(date_from, time.min)
    if date_to:
        created["$lt"] = datetime.combine(date_to + timedelta(days=1), time.min)
    if created:
        query["created_at"] = created

    sessions = list(
        get_collection(env).find(query, {"session_id": 1, "note": 1, "note_status": 1, "created_at": 1, "organization_id": 1, "agent_id": 1})
        .sort("created_at", 1)
    )

    base = _session_url_base(env)
    rows = []
    for session in sessions:
        texts = _note_texts(session.get("note"))
        session_id = session.get("session_id") or str(session["_id"])
        created_at = session.get("created_at")
        for i, text in enumerate(texts, 1):
            rows.append({
                "ticket_id": session_id if len(texts) == 1 else f"{session_id}#{i}",
                "session_id": session_id,
                "session_url": f"{base}/{session['_id']}",
                "agent_name": str(session.get("agent_id") or ""),
                "organization": str(session.get("organization_id") or ""),
                "note": text,
                "status": session.get("note_status") or "",
                "created": created_at.strftime("%Y-%m-%d") if hasattr(created_at, "strftime") else "",
            })

    return {
        "env": env,
        "source": "mongodb",
        "org_id": org_id,
        "org_name": org_name,
        "agent_name": agent_name,
        "fetched": len(sessions),
        "matched": len(rows),
        "resolved": len(rows),
        "unresolved": 0,
        "rows": rows,
    }


def process(org_id: str, agent_name: str = "", org_name: str = "", date_from=None, date_to=None,
            env: str = DEFAULT_ENV) -> dict:
    env = normalize_env(env)
    if env != DEFAULT_ENV:
        return _process_mongo(org_id, org_name, agent_name, date_from, date_to, env)

    cfg = jira_common.get_config()
    clauses = []
    if org_id:
        clauses.append(f'description ~ "Organization ID: {org_id}"')
    if org_name:
        clauses.append(f'description ~ "Organization: {org_name}"')
    if agent_name:
        clauses.append(f'description ~ "Agent: {agent_name}"')
    filter_clause = f" AND ({' OR '.join(clauses)})" if clauses else ""
    if not clauses:
        # Date-only run: pick every admin-note ticket on the board in the date range
        filter_clause = f' AND summary ~ "{ADMIN_NOTE_SUMMARY}"'
    if date_from:
        filter_clause += f' AND created >= "{date_from.isoformat()} 00:00"'
    if date_to:
        filter_clause += f' AND created < "{(date_to + timedelta(days=1)).isoformat()} 00:00"'
    jql = f'project = {cfg["project"]}{filter_clause} ORDER BY created DESC'
    tickets = jira_common.search_jql(cfg, jql, ["summary", "description", "status", "created"])

    matched = []
    for ticket in tickets:
        fields = ticket.get("fields", {})
        parsed = _parse_description(fields.get("description") or "", fields.get("summary") or "")
        if _matches(ticket, org_id, org_name, agent_name, date_from, date_to, parsed):
            matched.append((ticket, parsed))

    session_ids = [p["session_id"] for _, p in matched if p["session_id"] and not p["direct_doc_id"]]
    doc_id_map = _get_document_ids(session_ids, env) if session_ids else {}

    rows = []
    for ticket, parsed in matched:
        session_id = parsed["session_id"]
        document_id = parsed["direct_doc_id"] or doc_id_map.get(session_id)
        fields = ticket.get("fields", {})
        rows.append({
            "ticket_id": ticket.get("key", ""),
            "session_id": session_id,
            "session_url": f"{SESSION_URL_BASE}/{document_id}" if document_id else "",
            "agent_name": parsed["agent_name"],
            "organization": parsed["org_name"] or org_name or org_id,
            "note": parsed["note"],
            "status": (fields.get("status") or {}).get("name", ""),
            "created": (fields.get("created") or "")[:10],
        })

    return {
        "env": env,
        "source": "jira",
        "org_id": org_id,
        "org_name": org_name,
        "agent_name": agent_name,
        "fetched": len(tickets),
        "matched": len(rows),
        "resolved": len([r for r in rows if r["session_url"]]),
        "unresolved": len([r for r in rows if not r["session_url"]]),
        "rows": rows,
    }


def generate_excel(org_id: str, rows: list[dict], org_name: str = "") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = str(org_id)

    ws.append([f"Organization: {org_name or org_id}"])
    ws["A1"].font = Font(bold=True)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLUMNS))

    ws.append(COLUMNS)
    fill = PatternFill("solid", fgColor=HEADER_BG)
    font = Font(bold=True, color="FFFFFF")
    for cell in ws[2]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center")
    for i, w in enumerate(COL_WIDTHS, 1):
        ws.column_dimensions[ws.cell(2, i).column_letter].width = w

    for row in rows:
        ws.append([
            row.get("ticket_id", ""),
            row.get("session_id", ""),
            row.get("session_url", ""),
            row.get("note", ""),
            "", "", "",
        ])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
