import os
import time

import requests
from requests.auth import HTTPBasicAuth

MAX_RESULTS = 50
RETRY_LIMIT = 3
RETRY_DELAY = 2


class JiraError(Exception):
    pass


def get_config() -> dict:
    cfg = {
        "server": (os.getenv("JIRA_SERVER") or "").rstrip("/"),
        "email": os.getenv("JIRA_EMAIL") or "",
        "token": os.getenv("JIRA_API_TOKEN") or "",
        "project": os.getenv("JIRA_PROJECT_KEY", "OSD"),
        "target_project": os.getenv("JIRA_TARGET_PROJECT", "IMAP"),
        "target_issue_type": os.getenv("JIRA_TARGET_ISSUE_TYPE", "Task"),
        "target_status": os.getenv("JIRA_TARGET_STATUS", "In Review"),
    }
    missing = [k for k in ("server", "email", "token") if not cfg[k]]
    if missing:
        raise JiraError(
            "Missing Jira configuration in .env: "
            + ", ".join({"server": "JIRA_SERVER", "email": "JIRA_EMAIL", "token": "JIRA_API_TOKEN"}[m] for m in missing)
        )
    return cfg


def auth(cfg: dict) -> HTTPBasicAuth:
    return HTTPBasicAuth(cfg["email"], cfg["token"])


def request(cfg: dict, method: str, path: str, **kwargs) -> requests.Response:
    url = f"{cfg['server']}{path}"
    for attempt in range(RETRY_LIMIT):
        try:
            resp = requests.request(method, url, auth=auth(cfg), timeout=30, **kwargs)
        except requests.ConnectionError as e:
            raise JiraError(f"Could not connect to Jira: {e}")
        if resp.status_code == 429 and attempt < RETRY_LIMIT - 1:
            time.sleep(RETRY_DELAY)
            continue
        if resp.status_code == 401:
            raise JiraError("Authentication failed — check JIRA_EMAIL and JIRA_API_TOKEN.")
        return resp
    return resp


def search_jql(cfg: dict, jql: str, fields: list[str], on_issue=None) -> list[dict]:
    """Paginated POST /rest/api/3/search/jql using nextPageToken cursors."""
    issues = []
    next_token = None
    while True:
        body = {"jql": jql, "fields": fields, "maxResults": MAX_RESULTS}
        if next_token:
            body["nextPageToken"] = next_token
        resp = request(cfg, "POST", "/rest/api/3/search/jql", json=body)
        if not resp.ok:
            raise JiraError(f"Jira search failed ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        page = data.get("issues", [])
        for issue in page:
            issues.append(issue)
            if on_issue:
                on_issue(issue)
        next_token = data.get("nextPageToken")
        if not next_token or not page:
            break
    return issues


def get_transitions(cfg: dict, issue_key: str) -> list[dict]:
    resp = request(cfg, "GET", f"/rest/api/3/issue/{issue_key}/transitions")
    if resp.status_code == 404:
        raise JiraError(f"Ticket {issue_key} not found.")
    if not resp.ok:
        raise JiraError(f"Failed to get transitions for {issue_key} ({resp.status_code}): {resp.text[:300]}")
    return resp.json().get("transitions", [])
