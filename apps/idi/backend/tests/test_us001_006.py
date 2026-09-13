"""End-to-end coverage for US-001 through US-006 against SQLite bridge."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

# Isolate store before app import
TEST_ROOT = Path("/tmp/idi-test-run")
TEST_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["IDI_DATA_DIR"] = str(TEST_ROOT / "data")
os.environ["IDI_FERNET_KEY"] = Fernet.generate_key().decode()

from app import app, store  # noqa: E402


@pytest.fixture(autouse=True)
def clean_store(tmp_path):
    db_path = tmp_path / "idi.db"
    store.engine.dispose()
    store.db_url = f"sqlite+pysqlite:///{db_path}"
    store.engine = __import__("sqlalchemy").create_engine(store.db_url, future=True)
    from infra.store import Base

    Base.metadata.create_all(store.engine)
    store.Session = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(
        store.engine, expire_on_commit=False
    )
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sqlite_source(tmp_path):
    path = tmp_path / "source.db"
    engine = create_engine(f"sqlite+pysqlite:///{path}", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"))
        conn.execute(text("CREATE INDEX ix_users_name ON users (name)"))
    engine.dispose()
    return str(path)


def _create_payload(sqlite_path: str, name: str = "生产数仓") -> dict:
    return {
        "name": name,
        "dialect": "postgresql",
        "readonly_intent": True,
        "params": {
            "host": "demo.local",
            "port": "5432",
            "database": "demo",
            "username": "ro",
            "password": "secret-pass",
            "__sqlite_path": sqlite_path,
            "__skip_tcp": True,
        },
    }


def test_dialects_cover_prd_list(client):
    data = client.get("/api/dialects").json()
    ids = {d["id"] for d in data}
    assert len(ids) == 14
    assert "postgresql" in ids and "snowflake" in ids and "bigquery" in ids


def test_create_list_secret_mask_and_validation(client, sqlite_source):
    bad = client.post(
        "/api/datasources",
        json={"name": "", "dialect": "postgresql", "params": {"host": "x", "port": "abc"}},
    )
    assert bad.status_code == 400
    assert "name" in bad.json()["detail"]

    created = client.post("/api/datasources", json=_create_payload(sqlite_source)).json()
    assert created["status"] == "draft"
    assert created["readonly_intent"] is True
    assert created["params"]["password"] is None
    assert created["params"]["password__configured"] is True

    conflict = client.post("/api/datasources", json=_create_payload(sqlite_source, name="生产数仓"))
    assert conflict.status_code == 400

    listed = client.get("/api/datasources", params={"q": "生产"}).json()
    assert len(listed) == 1
    assert "secret-pass" not in str(listed)


def test_edit_keeps_password_and_disable_enable(client, sqlite_source):
    ds = client.post("/api/datasources", json=_create_payload(sqlite_source)).json()
    ds_id = ds["id"]
    client.post(f"/api/datasources/{ds_id}/test")
    ready = client.get(f"/api/datasources/{ds_id}").json()
    assert ready["status"] == "ready"

    patched = client.patch(
        f"/api/datasources/{ds_id}",
        json={"params": {"host": "demo.local", "port": "5432", "password": ""}},
    ).json()
    assert patched["status"] == "draft"
    stored = store.get_datasource(ds_id)
    assert stored.config.params["password"] == "secret-pass"

    client.post(f"/api/datasources/{ds_id}/test")
    client.post(f"/api/datasources/{ds_id}/disable")
    disabled = client.get(f"/api/datasources/{ds_id}").json()
    assert disabled["status"] == "disabled"
    client.post(f"/api/datasources/{ds_id}/test")
    still = client.get(f"/api/datasources/{ds_id}").json()
    assert still["status"] == "disabled"
    client.post(f"/api/datasources/{ds_id}/enable")
    enabled = client.get(f"/api/datasources/{ds_id}").json()
    assert enabled["status"] == "draft"


def test_connection_test_steps_and_auto_extract(client, sqlite_source):
    ds = client.post("/api/datasources", json=_create_payload(sqlite_source)).json()
    ds_id = ds["id"]
    result = client.post(f"/api/datasources/{ds_id}/test").json()
    assert result["status"] == "ready"
    assert result["last_test"]["overall_passed"] is True
    assert [s["outcome"] for s in result["last_test"]["steps"]] == [
        "passed",
        "passed",
        "passed",
        "passed",
    ]

    jobs = client.get(f"/api/datasources/{ds_id}/jobs").json()
    assert any(j["kind"] == "extract" and j["status"] == "succeeded" for j in jobs)
    meta = client.get(f"/api/datasources/{ds_id}/metadata").json()
    assert meta["table_count"] >= 1
    assert meta["current_snapshot_version"] == 1
    users = next(t for t in meta["tables"] if t["name"] == "users")
    assert any(c["name"] == "id" and c["is_primary_key"] for c in users["columns"])
    assert users["indexes"]


def test_network_failure_short_circuits(client, sqlite_source):
    payload = _create_payload(sqlite_source, name="坏主机")
    del payload["params"]["__sqlite_path"]
    del payload["params"]["__skip_tcp"]
    payload["params"]["host"] = "203.0.113.1"
    payload["params"]["port"] = "1"
    ds = client.post("/api/datasources", json=payload).json()
    result = client.post(f"/api/datasources/{ds['id']}/test").json()
    assert result["status"] == "test_failed"
    steps = result["last_test"]["steps"]
    assert steps[0]["outcome"] == "failed"
    assert steps[1]["outcome"] == "skipped"


def test_delete_requires_cascade(client, sqlite_source):
    ds = client.post("/api/datasources", json=_create_payload(sqlite_source)).json()
    client.post(f"/api/datasources/{ds['id']}/test")
    blocked = client.request(
        "DELETE",
        f"/api/datasources/{ds['id']}",
        json={"confirm": True, "cascade": False},
    )
    assert blocked.status_code == 400
    ok = client.request(
        "DELETE",
        f"/api/datasources/{ds['id']}",
        json={"confirm": True, "cascade": True},
    )
    assert ok.status_code == 200
    assert client.get(f"/api/datasources/{ds['id']}").status_code == 404


def test_sync_drift_and_snapshot_versioning(client, sqlite_source, tmp_path):
    ds = client.post("/api/datasources", json=_create_payload(sqlite_source)).json()
    ds_id = ds["id"]
    client.post(f"/api/datasources/{ds_id}/test")
    snaps = client.get(f"/api/datasources/{ds_id}/snapshots").json()
    assert snaps[0]["version"] == 1 and snaps[0]["is_current"]

    # no-op sync does not bump
    job = client.post(f"/api/datasources/{ds_id}/sync").json()
    assert job["status"] == "succeeded"
    assert job["version_bumped"] is False
    assert client.get(f"/api/datasources/{ds_id}").json()["current_snapshot_version"] == 1

    engine = create_engine(f"sqlite+pysqlite:///{sqlite_source}", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount REAL)"))
        conn.execute(text("ALTER TABLE users ADD COLUMN email TEXT"))
    engine.dispose()

    job2 = client.post(f"/api/datasources/{ds_id}/sync").json()
    assert job2["version_bumped"] is True
    assert job2["snapshot_version"] == 2
    drifts = client.get(f"/api/datasources/{ds_id}/drifts").json()
    kinds = {d["kind"] for d in drifts}
    assert "table_added" in kinds
    assert "column_added" in kinds

    hist = client.get(f"/api/datasources/{ds_id}/metadata", params={"version": 1}).json()
    assert hist["historical"] is True
    assert all(t["name"] != "orders" for t in hist["tables"])

    bad_cron = client.put(
        f"/api/datasources/{ds_id}/sync-schedule",
        json={"enabled": True, "cron": "not-a-cron"},
    )
    assert bad_cron.status_code == 400
    ok_cron = client.put(
        f"/api/datasources/{ds_id}/sync-schedule",
        json={"enabled": True, "cron": "*/5 * * * *"},
    )
    assert ok_cron.status_code == 200
    assert ok_cron.json()["sync_enabled"] is True
    assert ok_cron.json()["next_sync_at"]


def test_non_ready_cannot_extract(client, sqlite_source):
    ds = client.post("/api/datasources", json=_create_payload(sqlite_source)).json()
    resp = client.post(f"/api/datasources/{ds['id']}/extract")
    assert resp.status_code == 400
