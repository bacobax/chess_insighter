"""Shared pytest fixtures.

Every test runs against a fresh in-memory mongomock database so the suite never
touches the real MongoDB Atlas cluster configured in ``.env``.

Set ``MONGO_REAL_SMOKE=1`` to run the same tests against the real cluster instead, in a
throwaway ``chess_insighter_smoke`` database that is dropped after each test (the name is
hardcoded on purpose so teardown can never drop the application database).
"""

from __future__ import annotations

import os

import mongomock
import pytest
from pymongo import MongoClient

from backend.services import mongo_service
from backend.settings import settings


SMOKE_DATABASE = "chess_insighter_smoke"


@pytest.fixture(autouse=True)
def mongo_db():
    if os.environ.get("MONGO_REAL_SMOKE") == "1":
        client = MongoClient(settings.mongodb_uri)
        database = client[SMOKE_DATABASE]
    else:
        client = mongomock.MongoClient()
        database = client["chess_insighter_test"]
    mongo_service.use_database(database)
    try:
        yield database
    finally:
        mongo_service.use_database(None)
        if os.environ.get("MONGO_REAL_SMOKE") == "1":
            client.drop_database(SMOKE_DATABASE)
        client.close()
