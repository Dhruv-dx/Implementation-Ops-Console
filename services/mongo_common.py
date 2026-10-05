import os

from pymongo import MongoClient

ENVIRONMENTS = ("dev", "qa", "uat", "prod")
DEFAULT_ENV = "prod"

_clients: dict[str, MongoClient] = {}


class MongoConfigError(Exception):
    pass


def normalize_env(env: str | None) -> str:
    env = (env or DEFAULT_ENV).strip().lower()
    if env not in ENVIRONMENTS:
        raise MongoConfigError(f"Unknown environment '{env}' (expected one of: {', '.join(ENVIRONMENTS)})")
    return env


def _env_var(name: str, env: str) -> str | None:
    """`<name>_<env>` wins for every env (prod included). The unsuffixed value is a
    fallback for prod, and for database / collection names on other envs (only the
    connection string must be env-specific)."""
    value = os.getenv(f"{name}_{env}")
    if value:
        return value
    if env == DEFAULT_ENV or name != "mongo_connection_string":
        return os.getenv(name)
    return None


def get_collection(env: str | None = None, collection: str | None = None):
    """Chats collection for `env`; pass `collection` to read another collection in the same DB."""
    env = normalize_env(env)
    uri = _env_var("mongo_connection_string", env)
    db = _env_var("mongo_database", env)
    coll = collection or _env_var("mongo_collection", env)
    if not all([uri, db, coll]):
        raise MongoConfigError(
            f"Missing MongoDB configuration for '{env}' in .env: "
            f"mongo_connection_string_{env} / mongo_database_{env} / mongo_collection_{env}"
        )
    if uri not in _clients:
        _clients[uri] = MongoClient(uri)
    return _clients[uri][db][coll]


def get_traces_collection(env: str | None = None):
    env = normalize_env(env)
    return get_collection(env, _env_var("mongo_traces_collection", env) or "chats_traces")
