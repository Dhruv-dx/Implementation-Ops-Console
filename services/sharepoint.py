"""Push new Ticket Automation rows directly into the shared
'Session Notes With RCA.xlsx' file on SharePoint via Microsoft Graph,
instead of downloading + manually pasting each morning."""
import base64
import os
import re
import time

import requests

GRAPH = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

HEADER_ALIASES = {
    "ticket id": "ticket_id",
    "session id": "session_id",
    "session url": "session_url",
    "note": "note",
}

_TICKET_NUM_RE = re.compile(r"(\d+)\s*$")


class SharePointError(Exception):
    pass


def _config() -> dict:
    cfg = {
        "tenant_id": os.getenv("AZURE_TENANT_ID") or "",
        "client_id": os.getenv("AZURE_CLIENT_ID") or "",
        "client_secret": os.getenv("AZURE_CLIENT_SECRET") or "",
        "share_url": os.getenv("SHAREPOINT_EXCEL_URL") or "",
    }
    missing = [k for k in ("tenant_id", "client_id", "client_secret", "share_url") if not cfg[k]]
    if missing:
        raise SharePointError(
            "Missing SharePoint configuration in .env: "
            + ", ".join(
                {
                    "tenant_id": "AZURE_TENANT_ID",
                    "client_id": "AZURE_CLIENT_ID",
                    "client_secret": "AZURE_CLIENT_SECRET",
                    "share_url": "SHAREPOINT_EXCEL_URL",
                }[m]
                for m in missing
            )
        )
    return cfg


def _get_token(cfg: dict) -> str:
    resp = requests.post(
        TOKEN_URL_TMPL.format(tenant=cfg["tenant_id"]),
        data={
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    if not resp.ok:
        raise SharePointError(f"Azure AD auth failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()["access_token"]


def _encode_share_url(url: str) -> str:
    b64 = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    return f"u!{b64}"


def _resolve_drive_item(token: str, share_url: str) -> tuple[str, str]:
    encoded = _encode_share_url(share_url)
    resp = requests.get(
        f"{GRAPH}/shares/{encoded}/driveItem",
        headers={"Authorization": f"Bearer {token}"},
        params={"$select": "id,parentReference"},
        timeout=30,
    )
    if not resp.ok:
        raise SharePointError(f"Could not resolve SharePoint file ({resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    return data["parentReference"]["driveId"], data["id"]


def _ticket_sort_key(ticket_id: str):
    m = _TICKET_NUM_RE.search(ticket_id or "")
    prefix = ticket_id[: m.start()] if m else (ticket_id or "")
    number = int(m.group(1)) if m else 0
    return (prefix, number)


def append_new_tickets(rows: list[dict], org_name: str = "") -> dict:
    """Merge Ticket Automation rows into the shared Excel workbook.

    Existing rows (and any manually-filled Root Cause / Recommended Fix / Fixed
    values) are preserved as-is; only tickets not already present are added,
    then the full sheet is re-sorted by Ticket ID ascending.
    """
    cfg = _config()
    token = _get_token(cfg)
    drive_id, item_id = _resolve_drive_item(token, cfg["share_url"])

    base = f"{GRAPH}/drives/{drive_id}/items/{item_id}/workbook"
    headers = {"Authorization": f"Bearer {token}"}

    session_resp = requests.post(f"{base}/createSession", headers=headers, json={"persistChanges": True}, timeout=30)
    if not session_resp.ok:
        raise SharePointError(f"Could not open workbook session ({session_resp.status_code}): {session_resp.text[:300]}")
    session_id = session_resp.json()["id"]
    headers["workbook-session-id"] = session_id

    try:
        ws_resp = requests.get(f"{base}/worksheets", headers=headers, timeout=30)
        if not ws_resp.ok:
            raise SharePointError(f"Could not list worksheets ({ws_resp.status_code}): {ws_resp.text[:300]}")
        worksheets = ws_resp.json().get("value", [])
        if not worksheets:
            raise SharePointError("Workbook has no worksheets")
        sheet_name = worksheets[0]["name"]

        used_resp = requests.get(
            f"{base}/worksheets('{sheet_name}')/usedRange(valuesOnly=true)", headers=headers, timeout=30
        )
        if not used_resp.ok:
            raise SharePointError(f"Could not read worksheet data ({used_resp.status_code}): {used_resp.text[:300]}")
        values = used_resp.json().get("values", [])
        if not values:
            raise SharePointError("Worksheet appears empty — expected a header row")

        header_row_idx = None
        for i, row in enumerate(values):
            normalized = [str(c or "").strip().lower() for c in row]
            if "ticket id" in normalized:
                header_row_idx = i
                break
        if header_row_idx is None:
            raise SharePointError("Could not find a 'Ticket ID' header row in the worksheet")

        header = [str(c or "").strip() for c in values[header_row_idx]]
        col_index = {}
        for i, name in enumerate(header):
            key = HEADER_ALIASES.get(name.strip().lower())
            if key:
                col_index[key] = i
        if "ticket_id" not in col_index:
            raise SharePointError("Could not find a 'Ticket ID' column in the worksheet header")

        data_rows = [list(r) for r in values[header_row_idx + 1 :] if any(str(c or "").strip() for c in r)]
        existing_ids = {str(r[col_index["ticket_id"]]).strip() for r in data_rows if len(r) > col_index["ticket_id"]}

        added = 0
        for row in rows:
            ticket_id = str(row.get("ticket_id", "")).strip()
            if not ticket_id or ticket_id in existing_ids:
                continue
            new_row = [""] * len(header)
            for key, idx in col_index.items():
                if key in row:
                    new_row[idx] = row.get(key, "")
            new_row[col_index["ticket_id"]] = ticket_id
            data_rows.append(new_row)
            existing_ids.add(ticket_id)
            added += 1

        data_rows.sort(key=lambda r: _ticket_sort_key(str(r[col_index["ticket_id"]]) if len(r) > col_index["ticket_id"] else ""))

        width = len(header)
        full_values = [header] + [(r + [""] * width)[:width] for r in data_rows]
        start_row = header_row_idx + 1
        end_row = start_row + len(full_values) - 1
        end_col_letter = _col_letter(width)
        address = f"A{start_row}:{end_col_letter}{end_row}"

        patch_resp = requests.patch(
            f"{base}/worksheets('{sheet_name}')/range(address='{address}')",
            headers=headers,
            json={"values": full_values},
            timeout=60,
        )
        if not patch_resp.ok:
            raise SharePointError(f"Could not write to worksheet ({patch_resp.status_code}): {patch_resp.text[:300]}")

        return {
            "added": added,
            "skipped_duplicates": len(rows) - added,
            "total_rows_now": len(data_rows),
        }
    finally:
        requests.post(f"{base}/closeSession", headers=headers, timeout=30)


def _col_letter(n: int) -> str:
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters
