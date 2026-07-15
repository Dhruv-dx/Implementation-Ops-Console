"""Tickets Automation — Jira admin-note tickets enriched with session-log URLs,
exportable to Excel (ported from Jira-Ticket-Automation)."""
import io
import re
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from . import jira_common
from .mongo_common import get_collection

SESSION_URL_BASE = "https://platform.dxfactor.com/member-concierge/chat-log"

COLUMNS = ["Ticket ID", "Session ID", "Session URL", "Note", "Root Cause", "Recommended Fix", "Fixed"]
COL_WIDTHS = [15, 35, 60, 50, 30, 30, 12]
HEADER_BG = "1E3A5F"


def _extract_text_from_adf(node) -> str:
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts = [_extract_text_from_adf(child) for child in node.get("content", [])]
    separator = "\n" if node.get("type") in ("paragraph", "heading", "bulletList", "listItem") else ""
    return separator.join(p for p in parts if p)


def _parse_description(raw) -> dict:
    text = _extract_text_from_adf(raw) if isinstance(raw, dict) else (raw or "")
    session = re.search(r"Conversation ID:\s*(\S+)", text)
    org = re.search(r"Organization ID:\s*(\d+)", text)
    note_match = re.search(r"Admin Note\s*\n+(.*?)\n*(?:Conversation Logs|$)", text, re.DOTALL | re.IGNORECASE)
    return {
        "session_id": session.group(1).strip() if session else "",
        "org_id": org.group(1).strip() if org else "",
        "note": note_match.group(1).strip() if note_match else "",
    }


def _matches(ticket: dict, org_id: str, date_from, date_to, parsed: dict) -> bool:
    if parsed.get("org_id") != org_id:
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


def _get_document_ids(session_ids: list[str]) -> dict[str, str]:
    if not session_ids:
        return {}
    docs = get_collection().find({"session_id": {"$in": session_ids}}, {"_id": 1, "session_id": 1})
    return {doc["session_id"]: str(doc["_id"]) for doc in docs}


def process(org_id: str, date_from=None, date_to=None) -> dict:
    cfg = jira_common.get_config()
    jql = f'project = {cfg["project"]} AND description ~ "Organization ID: {org_id}" ORDER BY created DESC'
    tickets = jira_common.search_jql(cfg, jql, ["summary", "description", "status", "created"])

    matched = []
    for ticket in tickets:
        parsed = _parse_description(ticket.get("fields", {}).get("description") or "")
        if _matches(ticket, org_id, date_from, date_to, parsed):
            matched.append((ticket, parsed))

    session_ids = [p["session_id"] for _, p in matched if p["session_id"]]
    doc_id_map = _get_document_ids(session_ids) if session_ids else {}

    rows = []
    for ticket, parsed in matched:
        session_id = parsed["session_id"]
        document_id = doc_id_map.get(session_id)
        fields = ticket.get("fields", {})
        rows.append({
            "ticket_id": ticket.get("key", ""),
            "session_id": session_id,
            "session_url": f"{SESSION_URL_BASE}/{document_id}" if document_id else "",
            "note": parsed["note"],
            "status": (fields.get("status") or {}).get("name", ""),
            "created": (fields.get("created") or "")[:10],
        })

    return {
        "org_id": org_id,
        "fetched": len(tickets),
        "matched": len(rows),
        "resolved": len(doc_id_map),
        "unresolved": len([r for r in rows if not r["session_url"]]),
        "rows": rows,
    }


def generate_excel(org_id: str, rows: list[dict]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = str(org_id)

    ws.append(COLUMNS)
    fill = PatternFill("solid", fgColor=HEADER_BG)
    font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center")
    for i, w in enumerate(COL_WIDTHS, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w

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
