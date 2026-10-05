"""Chats Review — session browsing per organization (ported from `chats per org`)."""
from .mongo_common import DEFAULT_ENV, get_collection, get_traces_collection, normalize_env


def _fmt_ts(value):
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value or "N/A"


def get_sessions(organization_id: int, session_id: str = "", env: str = DEFAULT_ENV) -> dict:
    query = {"organization_id": organization_id}
    if session_id:
        query["session_id"] = session_id

    collection = get_collection(normalize_env(env))
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
        "env": env,
        "organization_id": organization_id,
        "session_id_filter": session_id,
        "total_sessions": len(processed),
        "sentiment_counts": sentiments,
        "sessions": processed,
    }


TRACE_LIMIT = 100


def _jsonable(value):
    """Mongo values -> JSON-safe (datetimes, ObjectIds, nested containers)."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "strftime"):
        return _fmt_ts(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _trace_turn(turn: dict) -> dict:
    usage = turn.get("usage") or {}
    return {
        "turn_number": turn.get("turn_number"),
        "provider": turn.get("provider"),
        "model": turn.get("model"),
        "timestamp": _fmt_ts(turn.get("timestamp")),
        "latency_ms": turn.get("latency_ms"),
        "stop_reason": turn.get("stop_reason"),
        "usage": _jsonable(usage),
        "tool_loop": _jsonable(turn.get("tool_loop") or {}),
        "steps": _jsonable(turn.get("steps") or []),
        "tool_calls": _jsonable(turn.get("tool_calls") or []),
        "queries": _jsonable(turn.get("queries") or []),
        "reasoning": _jsonable(turn.get("reasoning") or {}),
        "provider_metadata": _jsonable(turn.get("provider_metadata") or {}),
        "error": _jsonable(turn.get("error")),
    }


def get_traces(organization_id: int, session_id: str = "", env: str = DEFAULT_ENV) -> dict:
    env = normalize_env(env)
    query = {"organization_id": organization_id}
    if session_id:
        query["session_id"] = session_id

    collection = get_traces_collection(env)
    total = collection.count_documents(query)
    docs = list(collection.find(query).sort("created_at", -1).limit(TRACE_LIMIT))

    traces = []
    for doc in docs:
        turns = [_trace_turn(t) for t in doc.get("turns", [])]
        tokens = sum(((t["usage"] or {}).get("total_tokens") or 0) for t in turns)
        provider = doc.get("provider_details") or {}
        traces.append({
            "session_id": doc.get("session_id"),
            "chat_id": str(doc.get("chat_id") or ""),
            "created_at": _fmt_ts(doc.get("created_at")),
            "updated_at": _fmt_ts(doc.get("updated_at")),
            "agent_id": doc.get("agent_id"),
            "agent_version_id": doc.get("agent_version_id"),
            "router_version": doc.get("router_version"),
            "distribution_type": (doc.get("channel") or {}).get("distribution_type"),
            "model": provider.get("model_attribute_name"),
            "provider": provider.get("provider_name"),
            "sandbox": bool(doc.get("sandbox")),
            "byok": bool(doc.get("byok")),
            "channel": _jsonable(doc.get("channel") or {}),
            "turns": turns,
            "turn_count": len(turns),
            "total_tokens": tokens,
            "total_latency_ms": sum(t["latency_ms"] or 0 for t in turns),
            "tool_call_count": sum(len(t["tool_calls"]) for t in turns),
            "error_count": sum(1 for t in turns if t["error"]),
        })

    return {
        "env": env,
        "organization_id": organization_id,
        "session_id_filter": session_id,
        "total_traces": total,
        "shown": len(traces),
        "traces": traces,
    }
