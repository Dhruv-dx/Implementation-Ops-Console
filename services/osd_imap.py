"""OSD -> IMAP — copies 'Admin Note Created' tickets from the source project into
the target project for a given creation date (ported from T2B)."""
from . import jira_common

SUMMARY_FILTER = "Admin Note Created"


def _adf_from_text(text):
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            for line in (text or "").split("\n")
            if line.strip()
        ] or [{"type": "paragraph", "content": []}],
    }


def _description_text(fields):
    desc = fields.get("description")
    if desc is None:
        return ""
    if isinstance(desc, str):
        return desc
    lines = []
    for block in desc.get("content", []):
        text = "".join(c.get("text", "") for c in block.get("content", []) if c.get("type") == "text")
        lines.append(text)
    return "\n".join(lines)


def _transition_to(cfg, issue_key, status_name):
    transitions = jira_common.get_transitions(cfg, issue_key)
    match = next((t for t in transitions if t["to"]["name"].lower() == status_name.lower()), None)
    if not match:
        raise jira_common.JiraError(
            f"No transition to '{status_name}' available for {issue_key} "
            f"(available: {[t['to']['name'] for t in transitions]})"
        )
    resp = jira_common.request(cfg, "POST", f"/rest/api/3/issue/{issue_key}/transitions",
                               json={"transition": {"id": match["id"]}})
    if not resp.ok:
        raise jira_common.JiraError(f"Transition failed ({resp.status_code}): {resp.text[:300]}")


def copy_admin_notes_for_date(date_str: str, dry_run: bool = False, ticket_keys: list[str] = None) -> dict:
    cfg = jira_common.get_config()
    source_project = cfg["project"]
    target_project = cfg["target_project"]

    wanted = {k.strip().upper() for k in ticket_keys if k.strip()} if ticket_keys else set()
    if wanted:
        source_jql = f'project = {source_project} AND issuekey in ({",".join(sorted(wanted))})'
    else:
        source_jql = (
            f'project = {source_project} AND summary ~ "{SUMMARY_FILTER}" '
            f'AND created >= "{date_str} 00:00" AND created <= "{date_str} 23:59"'
        )
    source_issues = jira_common.search_jql(cfg, source_jql, ["summary", "description"])

    not_found = []
    if wanted:
        fetched_keys = {issue["key"].upper() for issue in source_issues}
        not_found = sorted(wanted - fetched_keys)

    target_jql = f'project = {target_project} AND summary ~ "{SUMMARY_FILTER}"'
    existing_summaries = {
        issue["fields"]["summary"] for issue in jira_common.search_jql(cfg, target_jql, ["summary"])
    }

    assignee_account_id = None if dry_run else jira_common.get_current_account_id(cfg)

    created, skipped, errors, would_create = [], [], [], []

    for issue in source_issues:
        key = issue["key"]
        summary = issue["fields"]["summary"]

        if summary in existing_summaries:
            skipped.append({"key": key, "summary": summary})
            continue

        if dry_run:
            would_create.append({"key": key, "summary": summary})
            continue

        payload = {
            "fields": {
                "project": {"key": target_project},
                "issuetype": {"name": cfg["target_issue_type"]},
                "summary": summary,
                "description": _adf_from_text(_description_text(issue["fields"])),
                "assignee": {"id": assignee_account_id},
            }
        }
        resp = jira_common.request(cfg, "POST", "/rest/api/3/issue", json=payload)
        if resp.status_code == 201:
            new_key = resp.json()["key"]
            try:
                _transition_to(cfg, new_key, cfg["target_status"])
            except Exception as exc:
                # The issue exists in the target project but is not in the target status
                errors.append({"key": key, "new_key": new_key, "summary": summary,
                               "error": f"Created as {new_key} but transition failed: {exc}"})
                existing_summaries.add(summary)
                continue
            created.append({"source_key": key, "new_key": new_key, "summary": summary})
            existing_summaries.add(summary)
        else:
            errors.append({"key": key, "summary": summary, "error": resp.text[:300]})

    return {
        "date": date_str,
        "dry_run": dry_run,
        "source_project": source_project,
        "target_project": target_project,
        "target_status": cfg["target_status"],
        "source_count": len(source_issues),
        "created": created,
        "would_create": would_create,
        "skipped": skipped,
        "errors": errors,
        "not_found": not_found,
    }
