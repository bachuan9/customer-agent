import os

import pytest

from app.storage.db import init_db, insert_logistics, insert_order


@pytest.fixture(autouse=True)
def isolated_test_database(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("APP_DB_PATH", str(db_path))
    init_db()
    insert_order("A101", "u001", "shipped")
    insert_logistics("L101", "A101", "delivered")
    yield
