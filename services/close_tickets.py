"""Close Tickets — find open Jira tickets by summary pattern and bulk-close them
(ported from `close tickets` CLI)."""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import jira_common

CLOSE_TRANSITION_NAMES = ["done", "mark as done", "closed", "close", "resolve", "resolved"]
DEFAULT_WORKERS = 50
KEY_RE = re.compile(r"^[A-Z]+-\d+$")


def find_open_tickets(pattern: str) -> list[dict]:
    """Fetch every open ticket in the project and filter client-side with an exact
    substring match (Jira's `summary ~` fuzzy search can silently miss tickets)."""
    cfg = jira_common.get_config()
    jql = f'project = "{cfg["project"]}" AND statusCategory != Done ORDER BY created DESC'
    pattern_lower = pattern.lower()
    tickets = []
    for issue in jira_common.search_jql(cfg, jql, ["summary"]):
        summary = issue.get("fields", {}).get("summary", "(no summary)")
        if pattern_lower in summary.lower():
            tickets.append({"key": issue["key"], "summary": summary})
    return tickets


def _resolve_close_transition(cfg: dict, issue_key: str) -> tuple[str | None, list[str]]:
    transitions = jira_common.get_transitions(cfg, issue_key)
    for name in CLOSE_TRANSITION_NAMES:
        for t in transitions:
            if t["name"].lower() == name:
                return t["id"], []
    return None, [t["name"] for t in transitions]


def _close_one(cfg: dict, issue_key: str, transition_id: str) -> dict:
    resp = jira_common.request(cfg, "POST", f"/rest/api/3/issue/{issue_key}/transitions",
                               json={"transition": {"id": transition_id}})
    if resp.status_code == 204:
        return {"key": issue_key, "status": "closed"}
    if resp.status_code == 400:
        return {"key": issue_key, "status": "already_closed"}
    if resp.status_code == 403:
        return {"key": issue_key, "status": "permission_denied"}
    return {"key": issue_key, "status": "error", "detail": f"HTTP {resp.status_code}"}


def close_tickets(keys: list[str], workers: int = DEFAULT_WORKERS) -> dict:
    keys = [k.strip() for k in keys if KEY_RE.match(k.strip())]
    if not keys:
        raise jira_common.JiraError("No valid ticket keys provided (expected format: PROJECT-123).")

    cfg = jira_common.get_config()
    # Resolve transition ID once — same board, same transitions for all tickets
    transition_id, available = _resolve_close_transition(cfg, keys[0])
    if not transition_id:
        raise jira_common.JiraError(
            f"Could not auto-detect a close transition for {keys[0]}. "
            f"Available transitions: {available}. Expected one of: {CLOSE_TRANSITION_NAMES}"
        )

    results = []
    workers = max(1, min(workers, 100))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_close_one, cfg, k, transition_id): k for k in keys}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                results.append({"key": futures[future], "status": "error", "detail": str(e)})

    order = {k: i for i, k in enumerate(keys)}
    results.sort(key=lambda r: order.get(r["key"], 0))
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"total": len(results), "counts": counts, "results": results}
