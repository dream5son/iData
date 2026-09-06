"""FastAPI application for IDI datasource & metadata APIs."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from idi_backend.adapters import list_dialects
from idi_backend.domain import DataSourceStatus
from idi_backend.services import datasources as svc
from idi_backend.store import Store
from idi_backend.store.db import table_to_dict
from idi_metadata import MetadataBusyError, NotReadyError, run_extract, run_sync

store = Store()
app = FastAPI(title="IDI Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateBody(BaseModel):
    name: str
    dialect: str
    params: dict[str, Any] = Field(default_factory=dict)
    readonly_intent: bool = True


class UpdateBody(BaseModel):
    name: str | None = None
    params: dict[str, Any] | None = None
    readonly_intent: bool | None = None


class DeleteBody(BaseModel):
    confirm: bool = False
    cascade: bool = False


class TestBody(BaseModel):
    dialect: str
    params: dict[str, Any] = Field(default_factory=dict)
    readonly_intent: bool = True


class ScheduleBody(BaseModel):
    enabled: bool
    cron: str | None = None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dialects")
def dialects() -> list[dict[str, Any]]:
    return list_dialects()


@app.get("/api/datasources")
def list_ds(
    q: str | None = None,
    dialect: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    return [svc.serialize_datasource(d) for d in store.list_datasources(q=q, dialect=dialect, status=status)]


@app.post("/api/datasources", status_code=201)
def create_ds(body: CreateBody) -> dict[str, Any]:
    try:
        ds = svc.create_datasource(store, body.model_dump())
    except svc.ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors) from exc
    return svc.serialize_datasource(ds)


@app.get("/api/datasources/{ds_id}")
def get_ds(ds_id: str) -> dict[str, Any]:
    ds = store.get_datasource(ds_id)
    if not ds:
        raise HTTPException(404, "数据源不存在")
    return svc.serialize_datasource(ds)


@app.patch("/api/datasources/{ds_id}")
def patch_ds(ds_id: str, body: UpdateBody) -> dict[str, Any]:
    try:
        ds = svc.update_datasource(store, ds_id, body.model_dump(exclude_unset=True))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except svc.ValidationError as exc:
        raise HTTPException(400, detail=exc.errors) from exc
    return svc.serialize_datasource(ds)


@app.post("/api/datasources/{ds_id}/disable")
def disable_ds(ds_id: str) -> dict[str, Any]:
    ds = store.get_datasource(ds_id)
    if not ds:
        raise HTTPException(404, "数据源不存在")
    ds.disable()
    store.save_datasource(ds)
    return svc.serialize_datasource(ds)


@app.post("/api/datasources/{ds_id}/enable")
def enable_ds(ds_id: str) -> dict[str, Any]:
    ds = store.get_datasource(ds_id)
    if not ds:
        raise HTTPException(404, "数据源不存在")
    try:
        ds.enable()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save_datasource(ds)
    return svc.serialize_datasource(ds)


@app.delete("/api/datasources/{ds_id}")
def delete_ds(ds_id: str, body: DeleteBody) -> dict[str, str]:
    try:
        svc.delete_datasource(store, ds_id, cascade=body.cascade, confirm=body.confirm)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except svc.ValidationError as exc:
        raise HTTPException(400, detail=exc.errors) from exc
    return {"status": "deleted"}


@app.post("/api/datasources/test")
def test_form(body: TestBody) -> dict[str, Any]:
    try:
        return svc.test_ephemeral(body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/datasources/{ds_id}/test")
def test_ds(ds_id: str) -> dict[str, Any]:
    try:
        ds = svc.test_saved(store, ds_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return svc.serialize_datasource(ds)


@app.post("/api/datasources/{ds_id}/extract")
def extract_ds(ds_id: str) -> dict[str, Any]:
    try:
        job = run_extract(store, ds_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except NotReadyError as exc:
        raise HTTPException(400, str(exc)) from exc
    except MetadataBusyError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _job_dict(job)


@app.get("/api/datasources/{ds_id}/jobs")
def jobs(ds_id: str) -> list[dict[str, Any]]:
    return [_job_dict(j) for j in store.list_jobs(ds_id)]


@app.get("/api/datasources/{ds_id}/metadata")
def metadata(
    ds_id: str,
    table_q: str | None = None,
    column_q: str | None = None,
    schema: str | None = None,
    version: int | None = Query(default=None),
) -> dict[str, Any]:
    ds = store.get_datasource(ds_id)
    if not ds:
        raise HTTPException(404, "数据源不存在")
    active = store.active_job(ds_id)
    jobs = store.list_jobs(ds_id)
    latest = next((j for j in jobs if j.kind.value == "extract"), None)
    historical = False
    partial = False
    if version is not None:
        snap = store.get_snapshot(ds_id, version)
        if not snap:
            raise HTTPException(404, "快照不存在")
        tables = list(snap.tables.values())
        historical = version != ds.current_snapshot_version
        partial = snap.partial
        current_version = version
    else:
        catalog = store.load_catalog(ds_id)
        tables = list(catalog.tables.values())
        current_version = ds.current_snapshot_version
        if ds.current_snapshot_version:
            snap = store.get_snapshot(ds_id, ds.current_snapshot_version)
            partial = bool(snap and snap.partial)

    if schema:
        tables = [t for t in tables if t.schema_name == schema]
    if table_q:
        ql = table_q.lower()
        tables = [t for t in tables if ql in t.name.lower()]
    if column_q:
        ql = column_q.lower()
        tables = [t for t in tables if any(ql in c.name.lower() for c in t.columns)]

    schemas = sorted({t.schema_name for t in tables})
    extracting = bool(active and active.kind.value in {"extract", "sync"} and active.status.value in {"queued", "running"})

    return {
        "datasource": svc.serialize_datasource(ds),
        "current_snapshot_version": current_version,
        "historical": historical,
        "partial_snapshot": partial,
        "extracting": extracting,
        "stale_warning": extracting and not historical,
        "disabled_warning": ds.status == DataSourceStatus.DISABLED,
        "latest_job": _job_dict(latest) if latest else None,
        "table_count": len(tables),
        "schemas": schemas,
        "tables": [table_to_dict(t) for t in sorted(tables, key=lambda x: x.key)],
    }


@app.put("/api/datasources/{ds_id}/sync-schedule")
def schedule(ds_id: str, body: ScheduleBody) -> dict[str, Any]:
    try:
        ds = svc.set_schedule(store, ds_id, body.enabled, body.cron)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except svc.ValidationError as exc:
        raise HTTPException(400, detail=exc.errors) from exc
    return svc.serialize_datasource(ds)


@app.post("/api/datasources/{ds_id}/sync")
def sync_now(ds_id: str) -> dict[str, Any]:
    try:
        job = run_sync(store, ds_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except MetadataBusyError as exc:
        raise HTTPException(409, str(exc)) from exc
    return _job_dict(job)


@app.get("/api/datasources/{ds_id}/drifts")
def drifts(ds_id: str, kind: str | None = None) -> list[dict[str, Any]]:
    return [
        {
            "id": d.id,
            "job_id": d.job_id,
            "kind": d.kind.value,
            "schema_name": d.schema_name,
            "table_name": d.table_name,
            "object_name": d.object_name,
            "before": d.before,
            "after": d.after,
            "detected_at": d.detected_at.isoformat(),
        }
        for d in store.list_drifts(ds_id, kind=kind)
    ]


@app.get("/api/datasources/{ds_id}/snapshots")
def snapshots(ds_id: str) -> list[dict[str, Any]]:
    return [
        {
            "version": s.version,
            "created_at": s.created_at.isoformat(),
            "source_job_id": s.source_job_id,
            "partial": s.partial,
            "drift_count": s.drift_count,
            "is_current": s.is_current,
            "table_count": len(s.tables),
        }
        for s in store.list_snapshots(ds_id)
    ]


@app.post("/api/internal/tick-schedules")
def tick() -> dict[str, Any]:
    return {"ran": svc.tick_schedules(store)}


def _job_dict(job) -> dict[str, Any]:
    return {
        "id": job.id,
        "datasource_id": job.datasource_id,
        "kind": job.kind.value,
        "status": job.status.value,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "progress_done": job.progress_done,
        "progress_total": job.progress_total,
        "errors": [{"object_name": e.object_name, "reason": e.reason} for e in job.errors],
        "message": job.message,
        "snapshot_version": job.snapshot_version,
        "version_bumped": job.version_bumped,
    }
