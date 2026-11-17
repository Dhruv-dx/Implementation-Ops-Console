"""Comment on Tix — post the same comment to one or many Jira Service Management
tickets, either as an internal note (agents only) or a public reply to the customer."""
import re
from concurrent.futures import ThreadPoolExecutor

from . import jira_common

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")
MODES = {"internal": False, "reply": True}
DEFAULT_WORKERS = 10


def parse_keys(raw: str) -> list[str]:
    """Split on commas/whitespace, upper-case, drop duplicates but keep input order."""
    seen = {}
    for token in re.split(r"[,\s]+", raw or ""):
        token = token.strip().upper()
        if token:
            seen.setdefault(token, None)
    return list(seen)


def _comment_one(cfg: dict, key: str, body: str, public: bool) -> dict:
    if not KEY_RE.match(key):
        return {"key": key, "status": "invalid", "detail": "Expected format PROJECT-123"}
    try:
        resp = jira_common.request(cfg, "POST", f"/rest/servicedeskapi/request/{key}/comment",
                                   json={"body": body, "public": public})
    except jira_common.JiraError as e:
        return {"key": key, "status": "error", "detail": str(e)}
    if resp.status_code == 201:
        return {"key": key, "status": "commented"}
    if resp.status_code == 404:
        return {"key": key, "status": "not_found", "detail": "Ticket not found or not a service desk request"}
    if resp.status_code == 403:
        return {"key": key, "status": "permission_denied"}
    return {"key": key, "status": "error", "detail": f"HTTP {resp.status_code}: {resp.text[:200]}"}


def add_comments(raw_keys: str, comment: str, mode: str, workers: int = DEFAULT_WORKERS) -> dict:
    if mode not in MODES:
        raise jira_common.JiraError("Mode must be 'internal' or 'reply'.")
    comment = (comment or "").strip()
    if not comment:
        raise jira_common.JiraError("Comment cannot be empty.")
    keys = parse_keys(raw_keys)
    if not keys:
        raise jira_common.JiraError("No ticket numbers provided (expected format: PROJECT-123).")

    cfg = jira_common.get_config()
    public = MODES[mode]
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(keys)))) as pool:
        results = list(pool.map(lambda k: _comment_one(cfg, k, comment, public), keys))

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"mode": mode, "total": len(results), "counts": counts, "results": results}
