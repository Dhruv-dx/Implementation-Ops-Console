"""OMAP(R) Admin Dashboard — unified entry point for the four internal tools:
Chats Review, Tickets Automation, OSD -> IMAP, Close Tickets.

Run:  python app.py   (serves http://127.0.0.1:8100)
"""
import os
import re
from datetime import date as date_type
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from services import chats, close_tickets, osd_imap, sharepoint, ticket_automation
from services.jira_common import JiraError
from services.mongo_common import MongoConfigError
from services.sharepoint import SharePointError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="OMAP Admin Dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (JiraError, MongoConfigError, SharePointError) as e:
        raise HTTPException(502, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Unexpected error: {e}")


# ---------------------------------------------------------------- Chats Review

@app.get("/api/chats/sessions")
async def chats_sessions(
    organization_id: int = Query(..., description="Organization ID"),
    session_id: str = Query("", description="Optional session ID filter"),
):
    return _guard(chats.get_sessions, organization_id, session_id.strip())


# ---------------------------------------------------------- Tickets Automation

class ProcessRequest(BaseModel):
    org_id: Optional[str] = ""
    org_name: Optional[str] = ""
    agent_name: Optional[str] = ""
    date_from: Optional[date_type] = None
    date_to: Optional[date_type] = None


def _ta_filters(req: ProcessRequest) -> tuple[str, str, str]:
    org_id = (req.org_id or "").strip()
    org_name = (req.org_name or "").strip()
    agent_name = (req.agent_name or "").strip()
    if not org_id and not org_name and not agent_name:
        raise HTTPException(400, "Provide an Organization ID, Organization name, or an Agent name")
    return org_id, org_name, agent_name


@app.post("/api/ticket-automation/process")
async def ta_process(req: ProcessRequest):
    org_id, org_name, agent_name = _ta_filters(req)
    return _guard(ticket_automation.process, org_id, agent_name, org_name, req.date_from, req.date_to)


@app.post("/api/ticket-automation/download")
async def ta_download(req: ProcessRequest):
    org_id, org_name, agent_name = _ta_filters(req)
    result = _guard(ticket_automation.process, org_id, agent_name, org_name, req.date_from, req.date_to)
    if not result["rows"]:
        raise HTTPException(404, "No tickets found for the given filters")
    label = org_id or org_name or agent_name
    xlsx = ticket_automation.generate_excel(label, result["rows"], org_name)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{label}_sessions.xlsx"'},
    )


@app.get("/api/ticket-automation/sharepoint/debug")
async def ta_sharepoint_debug():
    return {
        "cwd": os.getcwd(),
        "AZURE_TENANT_ID_set": bool(os.getenv("AZURE_TENANT_ID")),
        "AZURE_CLIENT_ID_set": bool(os.getenv("AZURE_CLIENT_ID")),
        "AZURE_CLIENT_SECRET_set": bool(os.getenv("AZURE_CLIENT_SECRET")),
        "SHAREPOINT_EXCEL_URL_set": bool(os.getenv("SHAREPOINT_EXCEL_URL")),
    }


@app.post("/api/ticket-automation/sharepoint")
async def ta_sharepoint(req: ProcessRequest):
    org_id, org_name, agent_name = _ta_filters(req)
    result = _guard(ticket_automation.process, org_id, agent_name, org_name, req.date_from, req.date_to)
    if not result["rows"]:
        raise HTTPException(404, "No tickets found for the given filters")
    return _guard(sharepoint.append_new_tickets, result["rows"], org_name)


# ------------------------------------------------------------------ OSD -> IMAP

class CopyRequest(BaseModel):
    date: date_type
    dry_run: bool = False
    ticket_numbers: Optional[str] = ""


@app.post("/api/osd-imap/copy")
async def osd_imap_copy(req: CopyRequest):
    ticket_keys = [k.strip() for k in re.split(r"[,\s]+", req.ticket_numbers or "") if k.strip()]
    return _guard(osd_imap.copy_admin_notes_for_date, req.date.isoformat(), req.dry_run, ticket_keys or None)


# ---------------------------------------------------------------- Close Tickets

class FindRequest(BaseModel):
    pattern: str


class CloseRequest(BaseModel):
    keys: list[str]
    workers: int = Field(default=close_tickets.DEFAULT_WORKERS, ge=1, le=100)


@app.post("/api/close-tickets/find")
async def ct_find(req: FindRequest):
    pattern = req.pattern.strip()
    if not pattern:
        raise HTTPException(400, "Search pattern is required")
    tickets = _guard(close_tickets.find_open_tickets, pattern)
    return {"pattern": pattern, "total": len(tickets), "tickets": tickets}


@app.post("/api/close-tickets/close")
async def ct_close(req: CloseRequest):
    if not req.keys:
        raise HTTPException(400, "No ticket keys provided")
    return _guard(close_tickets.close_tickets, req.keys, req.workers)


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
