import os

from pymongo import MongoClient

_client: MongoClient | None = None


class MongoConfigError(Exception):
    pass


def get_collection():
    global _client
    uri = os.getenv("mongo_connection_string")
    db = os.getenv("mongo_database")
    coll = os.getenv("mongo_collection")
    if not all([uri, db, coll]):
        raise MongoConfigError(
            "Missing MongoDB configuration in .env: mongo_connection_string / mongo_database / mongo_collection"
        )
    if _client is None:
        _client = MongoClient(uri)
    return _client[db][coll]
