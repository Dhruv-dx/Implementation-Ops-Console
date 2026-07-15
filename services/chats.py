"""Chats Review — session browsing per organization (ported from `chats per org`)."""
from .mongo_common import get_collection


def _fmt_ts(value):
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value or "N/A"


def get_sessions(organization_id: int, session_id: str = "") -> dict:
    query = {"organization_id": organization_id}
    if session_id:
        query["session_id"] = session_id

    collection = get_collection()
    sessions = list(
        collection.find(
            query,
            {
                "session_id": 1,
                "messages": 1,
                "created_at": 1,
                "agent_version": 1,
                "category": 1,
                "sentiment": 1,
                "initial_source_page": 1,
            },
        ).sort("created_at", -1)
    )

    processed = []
    for session in sessions:
        messages = []
        for msg in session.get("messages", []):
            if msg.get("role") not in ("user", "assistant"):
                continue
            item = {
                "role": msg.get("role"),
                "content": msg.get("content"),
                "timestamp": _fmt_ts(msg.get("timestamp")),
            }
            if msg.get("role") == "user":
                item["source_page"] = msg.get("source_page", "N/A")
            else:
                item["queries"] = msg.get("queries", [])
                item["files_searched"] = msg.get("files_searched", [])
            messages.append(item)

        if messages:
            processed.append({
                "session_id": session.get("session_id"),
                "created_at": _fmt_ts(session.get("created_at")),
                "agent_version": (session.get("agent_version") or {}).get("name", "N/A"),
                "category": session.get("category", "N/A"),
                "sentiment": session.get("sentiment", "N/A"),
                "initial_source_page": session.get("initial_source_page", "N/A"),
                "messages": messages,
                "message_count": len(messages),
            })

    sentiments = {}
    for s in processed:
        key = (s["sentiment"] or "N/A").title()
        sentiments[key] = sentiments.get(key, 0) + 1

    return {
        "organization_id": organization_id,
        "session_id_filter": session_id,
        "total_sessions": len(processed),
        "sentiment_counts": sentiments,
        "sessions": processed,
    }
