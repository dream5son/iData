"""Datasource lifecycle and connection testing services."""

from __future__ import annotations

from typing import Any

from idi_backend.adapters import get_adapter, list_dialects
from idi_backend.domain import (
    ConnectionConfig,
    DataSource,
    DataSourceStatus,
    Dialect,
    SECRET_KEYS,
    new_id,
    utcnow,
)
from idi_backend.store import Store
from idi_metadata.extract import run_extract
from idi_metadata.sync import next_cron_time, run_sync, validate_cron


class ValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("validation failed")
        self.errors = errors


def serialize_datasource(ds: DataSource) -> dict[str, Any]:
    return {
        "id": ds.id,
        "name": ds.name,
        "dialect": ds.config.dialect.value,
        "params": ds.config.public_params(),
        "readonly_intent": ds.config.readonly_intent,
        "status": ds.status.value,
        "created_at": ds.created_at.isoformat(),
        "updated_at": ds.updated_at.isoformat(),
        "last_tested_at": ds.last_tested_at.isoformat() if ds.last_tested_at else None,
        "last_test": None
        if not ds.last_test
        else {
            "overall_passed": ds.last_test.overall_passed,
            "tested_at": ds.last_test.tested_at.isoformat(),
            "steps": [
                {"name": s.name, "outcome": s.outcome.value, "message": s.message}
                for s in ds.last_test.steps
            ],
        },
        "current_snapshot_version": ds.current_snapshot_version,
        "sync_enabled": ds.sync_enabled,
        "sync_cron": ds.sync_cron,
        "next_sync_at": ds.next_sync_at.isoformat() if ds.next_sync_at else None,
    }


def _merge_secrets(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key.endswith("__configured"):
            continue
        if key.lower() in SECRET_KEYS or key.startswith("secret_"):
            if value is None or value == "":
                continue
            merged[key] = value
        else:
            merged[key] = value
    return merged


def create_datasource(store: Store, payload: dict[str, Any]) -> DataSource:
    errors: dict[str, str] = {}
    name = (payload.get("name") or "").strip()
    if not name or len(name) > 128:
        errors["name"] = "显示名称必填，长度 1–128"
    try:
        dialect = Dialect(payload.get("dialect"))
    except Exception:
        errors["dialect"] = "不支持的数据库类型"
        dialect = None  # type: ignore

    if dialect:
        adapter = get_adapter(dialect)
        params = dict(payload.get("params") or {})
        if "port" in params and params["port"] is not None and not str(params["port"]).isdigit():
            errors["port"] = "端口须为数字"
        missing = adapter.validate_params(params)
        # Allow sqlite bridge to omit live secrets in local proof mode
        if params.get("__sqlite_path"):
            missing = [m for m in missing if m not in {"password", "username", "token"}]
        for key in missing:
            errors[key] = f"{key} 为必填项"

    if store.get_by_name(name):
        errors["name"] = "显示名称冲突"

    if errors:
        raise ValidationError(errors)

    assert dialect is not None
    params = dict(payload.get("params") or {})
    readonly = payload.get("readonly_intent")
    if readonly is None:
        readonly = True

    ds = DataSource(
        id=new_id("ds"),
        name=name,
        config=ConnectionConfig(dialect=dialect, params=params, readonly_intent=bool(readonly)),
        status=DataSourceStatus.DRAFT,
    )
    return store.save_datasource(ds)


def update_datasource(store: Store, ds_id: str, payload: dict[str, Any]) -> DataSource:
    ds = store.get_datasource(ds_id)
    if not ds:
        raise KeyError("数据源不存在")
    errors: dict[str, str] = {}
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name or len(name) > 128:
            errors["name"] = "显示名称必填，长度 1–128"
        other = store.get_by_name(name)
        if other and other.id != ds_id:
            errors["name"] = "显示名称冲突"
        else:
            ds.name = name

    if "params" in payload:
        incoming = dict(payload["params"] or {})
        if "port" in incoming and incoming["port"] is not None and not str(incoming["port"]).isdigit():
            errors["port"] = "端口须为数字"
        ds.config.params = _merge_secrets(ds.config.params, incoming)

    if "readonly_intent" in payload:
        ds.config.readonly_intent = bool(payload["readonly_intent"])

    if errors:
        raise ValidationError(errors)

    ds.updated_at = utcnow()
    if ds.status == DataSourceStatus.READY:
        ds.status = DataSourceStatus.DRAFT
    return store.save_datasource(ds)


def delete_datasource(store: Store, ds_id: str, *, cascade: bool, confirm: bool) -> None:
    ds = store.get_datasource(ds_id)
    if not ds:
        raise KeyError("数据源不存在")
    if not confirm:
        raise ValidationError({"confirm": "删除需要二次确认"})
    has_meta = store.has_catalog(ds_id) or bool(store.list_snapshots(ds_id))
    if has_meta and not cascade:
        raise ValidationError({"cascade": "请先确认级联删除元数据"})
    store.delete_datasource(ds_id)


def test_saved(store: Store, ds_id: str) -> DataSource:
    ds = store.get_datasource(ds_id)
    if not ds:
        raise KeyError("数据源不存在")
    adapter = get_adapter(ds.config.dialect)
    report = adapter.test_connection(ds.config)
    ds.last_test = report
    ds.last_tested_at = report.tested_at
    first_ready = False
    if ds.status != DataSourceStatus.DISABLED:
        was_ready = ds.status == DataSourceStatus.READY
        ds.transition_after_test(report.overall_passed)
        first_ready = report.overall_passed and not was_ready and ds.status == DataSourceStatus.READY
    ds.updated_at = utcnow()
    store.save_datasource(ds)
    if first_ready:
        run_extract(store, ds.id)
    return store.get_datasource(ds_id)  # type: ignore


def test_ephemeral(payload: dict[str, Any]) -> dict[str, Any]:
    dialect = Dialect(payload["dialect"])
    config = ConnectionConfig(
        dialect=dialect,
        params=dict(payload.get("params") or {}),
        readonly_intent=bool(payload.get("readonly_intent", True)),
    )
    report = get_adapter(dialect).test_connection(config)
    return {
        "overall_passed": report.overall_passed,
        "tested_at": report.tested_at.isoformat(),
        "steps": [
            {"name": s.name, "outcome": s.outcome.value, "message": s.message} for s in report.steps
        ],
    }


def set_schedule(store: Store, ds_id: str, enabled: bool, cron: str | None) -> DataSource:
    ds = store.get_datasource(ds_id)
    if not ds:
        raise KeyError("数据源不存在")
    if enabled:
        if not cron or not validate_cron(cron):
            raise ValidationError({"sync_cron": "非法 Cron 表达式"})
        ds.sync_enabled = True
        ds.sync_cron = cron
        ds.next_sync_at = next_cron_time(cron)
    else:
        ds.sync_enabled = False
        ds.next_sync_at = None
        if cron is not None:
            if cron and not validate_cron(cron):
                raise ValidationError({"sync_cron": "非法 Cron 表达式"})
            ds.sync_cron = cron or ds.sync_cron
    ds.updated_at = utcnow()
    return store.save_datasource(ds)


def tick_schedules(store: Store) -> list[str]:
    """Run due sync jobs. Returns datasource ids processed."""
    ran: list[str] = []
    now = utcnow()
    for ds in store.list_datasources():
        if not ds.sync_enabled or not ds.sync_cron or not ds.next_sync_at:
            continue
        if ds.next_sync_at <= now:
            run_sync(store, ds.id, scheduled=True)
            ran.append(ds.id)
    return ran
