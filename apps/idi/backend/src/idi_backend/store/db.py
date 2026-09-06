"""SQLite-backed persistence for datasources, catalog, jobs, drifts, snapshots."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from cryptography.fernet import Fernet
from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    MetaData,
    String,
    Text,
    create_engine,
    delete,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from idi_backend.domain import (
    Catalog,
    ColumnMeta,
    ConnectionConfig,
    ConnectionTestReport,
    DataSource,
    DataSourceStatus,
    Dialect,
    DriftKind,
    DriftRecord,
    IndexMeta,
    Job,
    JobError,
    JobKind,
    JobStatus,
    SECRET_KEYS,
    Snapshot,
    StepOutcome,
    TableMeta,
    TestStepResult,
    new_id,
    utcnow,
)


class Base(DeclarativeBase):
    metadata = MetaData()


class DataSourceRow(Base):
    __tablename__ = "datasources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    dialect: Mapped[str] = mapped_column(String(32))
    params_json: Mapped[str] = mapped_column(Text)
    readonly_intent: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_snapshot_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_cron: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CatalogTableRow(Base):
    __tablename__ = "catalog_tables"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    datasource_id: Mapped[str] = mapped_column(String(64), index=True)
    schema_name: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(256))
    payload_json: Mapped[str] = mapped_column(Text)


class JobRow(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    datasource_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress_done: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    errors_json: Mapped[str] = mapped_column(Text, default="[]")
    message: Mapped[str] = mapped_column(Text, default="")
    snapshot_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version_bumped: Mapped[bool] = mapped_column(Boolean, default=False)


class DriftRow(Base):
    __tablename__ = "drifts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    datasource_id: Mapped[str] = mapped_column(String(64), index=True)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    schema_name: Mapped[str] = mapped_column(String(128))
    table_name: Mapped[str] = mapped_column(String(256))
    object_name: Mapped[str] = mapped_column(String(256))
    before: Mapped[str | None] = mapped_column(Text, nullable=True)
    after: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SnapshotRow(Base):
    __tablename__ = "snapshots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    datasource_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_job_id: Mapped[str] = mapped_column(String(64))
    partial: Mapped[bool] = mapped_column(Boolean, default=False)
    drift_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text)


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def table_to_dict(table: TableMeta) -> dict[str, Any]:
    return {
        "schema_name": table.schema_name,
        "name": table.name,
        "table_type": table.table_type,
        "created_at": table.created_at,
        "storage_size": table.storage_size,
        "comment": table.comment,
        "columns": [asdict(c) for c in table.columns],
        "indexes": [asdict(i) for i in table.indexes],
        "partition_keys": table.partition_keys,
        "bucket_keys": table.bucket_keys,
    }


def table_from_dict(data: dict[str, Any]) -> TableMeta:
    return TableMeta(
        schema_name=data["schema_name"],
        name=data["name"],
        table_type=data.get("table_type", "BASE TABLE"),
        created_at=data.get("created_at"),
        storage_size=data.get("storage_size"),
        comment=data.get("comment"),
        columns=[ColumnMeta(**c) for c in data.get("columns", [])],
        indexes=[IndexMeta(**i) for i in data.get("indexes", [])],
        partition_keys=list(data.get("partition_keys") or []),
        bucket_keys=list(data.get("bucket_keys") or []),
    )


class Store:
    def __init__(self, db_url: str | None = None, fernet_key: str | None = None):
        data_dir = Path(os.environ.get("IDI_DATA_DIR", "/tmp/idi-data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_url = db_url or f"sqlite+pysqlite:///{data_dir / 'idi.db'}"
        key = fernet_key or os.environ.get("IDI_FERNET_KEY")
        if not key:
            key_path = data_dir / "fernet.key"
            if key_path.exists():
                key = key_path.read_text().strip()
            else:
                key = Fernet.generate_key().decode()
                key_path.write_text(key)
        self.fernet = Fernet(key.encode() if isinstance(key, str) else key)
        self.engine = create_engine(self.db_url, future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def lock_for(self, datasource_id: str) -> threading.Lock:
        with self._locks_guard:
            if datasource_id not in self._locks:
                self._locks[datasource_id] = threading.Lock()
            return self._locks[datasource_id]

    def encrypt_params(self, params: dict[str, Any]) -> dict[str, Any]:
        out = dict(params)
        for key, value in list(out.items()):
            if value is None:
                continue
            if key.lower() in SECRET_KEYS or key.startswith("secret_"):
                token = self.fernet.encrypt(str(value).encode()).decode()
                out[key] = f"enc:{token}"
        return out

    def decrypt_params(self, params: dict[str, Any]) -> dict[str, Any]:
        out = dict(params)
        for key, value in list(out.items()):
            if isinstance(value, str) and value.startswith("enc:"):
                out[key] = self.fernet.decrypt(value[4:].encode()).decode()
        return out

    def _to_datasource(self, row: DataSourceRow) -> DataSource:
        params = self.decrypt_params(json.loads(row.params_json))
        last_test = None
        if row.last_test_json:
            raw = json.loads(row.last_test_json)
            last_test = ConnectionTestReport(
                steps=[
                    TestStepResult(
                        name=s["name"],
                        outcome=StepOutcome(s["outcome"]),
                        message=s.get("message", ""),
                    )
                    for s in raw["steps"]
                ],
                overall_passed=raw["overall_passed"],
                tested_at=datetime.fromisoformat(raw["tested_at"]),
            )
        return DataSource(
            id=row.id,
            name=row.name,
            config=ConnectionConfig(
                dialect=Dialect(row.dialect),
                params=params,
                readonly_intent=row.readonly_intent,
            ),
            status=DataSourceStatus(row.status),
            created_at=row.created_at,
            updated_at=row.updated_at,
            last_tested_at=row.last_tested_at,
            last_test=last_test,
            current_snapshot_version=row.current_snapshot_version,
            sync_enabled=row.sync_enabled,
            sync_cron=row.sync_cron,
            next_sync_at=row.next_sync_at,
        )

    def list_datasources(
        self,
        *,
        q: str | None = None,
        dialect: str | None = None,
        status: str | None = None,
    ) -> list[DataSource]:
        with self.Session() as session:
            rows = session.scalars(select(DataSourceRow)).all()
            items = [self._to_datasource(r) for r in rows]
        if q:
            ql = q.lower()
            items = [i for i in items if ql in i.name.lower()]
        if dialect:
            items = [i for i in items if i.config.dialect.value == dialect]
        if status:
            items = [i for i in items if i.status.value == status]
        return sorted(items, key=lambda i: i.updated_at, reverse=True)

    def get_datasource(self, ds_id: str) -> DataSource | None:
        with self.Session() as session:
            row = session.get(DataSourceRow, ds_id)
            return self._to_datasource(row) if row else None

    def get_by_name(self, name: str) -> DataSource | None:
        with self.Session() as session:
            row = session.scalars(select(DataSourceRow).where(DataSourceRow.name == name)).first()
            return self._to_datasource(row) if row else None

    def save_datasource(self, ds: DataSource) -> DataSource:
        payload = {
            "id": ds.id,
            "name": ds.name,
            "dialect": ds.config.dialect.value,
            "params_json": json.dumps(self.encrypt_params(ds.config.params)),
            "readonly_intent": ds.config.readonly_intent,
            "status": ds.status.value,
            "created_at": ds.created_at,
            "updated_at": ds.updated_at,
            "last_tested_at": ds.last_tested_at,
            "last_test_json": None
            if not ds.last_test
            else json.dumps(
                {
                    "steps": [
                        {"name": s.name, "outcome": s.outcome.value, "message": s.message}
                        for s in ds.last_test.steps
                    ],
                    "overall_passed": ds.last_test.overall_passed,
                    "tested_at": ds.last_test.tested_at.isoformat(),
                }
            ),
            "current_snapshot_version": ds.current_snapshot_version,
            "sync_enabled": ds.sync_enabled,
            "sync_cron": ds.sync_cron,
            "next_sync_at": ds.next_sync_at,
        }
        with self.Session() as session:
            existing = session.get(DataSourceRow, ds.id)
            if existing:
                for k, v in payload.items():
                    setattr(existing, k, v)
            else:
                session.add(DataSourceRow(**payload))
            session.commit()
        return ds

    def delete_datasource(self, ds_id: str) -> None:
        with self.Session() as session:
            session.execute(delete(DataSourceRow).where(DataSourceRow.id == ds_id))
            session.execute(delete(CatalogTableRow).where(CatalogTableRow.datasource_id == ds_id))
            session.execute(delete(JobRow).where(JobRow.datasource_id == ds_id))
            session.execute(delete(DriftRow).where(DriftRow.datasource_id == ds_id))
            session.execute(delete(SnapshotRow).where(SnapshotRow.datasource_id == ds_id))
            session.commit()

    def has_catalog(self, ds_id: str) -> bool:
        with self.Session() as session:
            row = session.scalars(
                select(CatalogTableRow).where(CatalogTableRow.datasource_id == ds_id).limit(1)
            ).first()
            return row is not None

    def load_catalog(self, ds_id: str) -> Catalog:
        with self.Session() as session:
            rows = session.scalars(
                select(CatalogTableRow).where(CatalogTableRow.datasource_id == ds_id)
            ).all()
            catalog = Catalog(datasource_id=ds_id)
            for row in rows:
                table = table_from_dict(json.loads(row.payload_json))
                catalog.tables[table.key] = table
            return catalog

    def replace_catalog(self, catalog: Catalog) -> None:
        with self.Session() as session:
            session.execute(
                delete(CatalogTableRow).where(CatalogTableRow.datasource_id == catalog.datasource_id)
            )
            for table in catalog.tables.values():
                session.add(
                    CatalogTableRow(
                        id=new_id("tbl"),
                        datasource_id=catalog.datasource_id,
                        schema_name=table.schema_name,
                        name=table.name,
                        payload_json=json.dumps(table_to_dict(table)),
                    )
                )
            session.commit()

    def apply_catalog_updates(
        self,
        ds_id: str,
        upserts: list[TableMeta],
        removals: list[str],
    ) -> Catalog:
        catalog = self.load_catalog(ds_id)
        for key in removals:
            catalog.remove_table(key)
        for table in upserts:
            catalog.upsert_table(table)
        self.replace_catalog(catalog)
        return catalog

    def save_job(self, job: Job) -> Job:
        with self.Session() as session:
            row = session.get(JobRow, job.id)
            payload = dict(
                id=job.id,
                datasource_id=job.datasource_id,
                kind=job.kind.value,
                status=job.status.value,
                started_at=job.started_at,
                finished_at=job.finished_at,
                progress_done=job.progress_done,
                progress_total=job.progress_total,
                errors_json=json.dumps([asdict(e) for e in job.errors]),
                message=job.message,
                snapshot_version=job.snapshot_version,
                version_bumped=job.version_bumped,
            )
            if row:
                for k, v in payload.items():
                    setattr(row, k, v)
            else:
                session.add(JobRow(**payload))
            session.commit()
        return job

    def list_jobs(self, ds_id: str) -> list[Job]:
        with self.Session() as session:
            rows = session.scalars(
                select(JobRow).where(JobRow.datasource_id == ds_id).order_by(JobRow.id.desc())
            ).all()
            return [self._to_job(r) for r in rows]

    def get_job(self, job_id: str) -> Job | None:
        with self.Session() as session:
            row = session.get(JobRow, job_id)
            return self._to_job(row) if row else None

    def active_job(self, ds_id: str) -> Job | None:
        with self.Session() as session:
            rows = session.scalars(
                select(JobRow).where(
                    JobRow.datasource_id == ds_id,
                    JobRow.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                )
            ).all()
            return self._to_job(rows[0]) if rows else None

    def _to_job(self, row: JobRow) -> Job:
        errors = [JobError(**e) for e in json.loads(row.errors_json or "[]")]
        return Job(
            id=row.id,
            datasource_id=row.datasource_id,
            kind=JobKind(row.kind),
            status=JobStatus(row.status),
            started_at=row.started_at,
            finished_at=row.finished_at,
            progress_done=row.progress_done,
            progress_total=row.progress_total,
            errors=errors,
            message=row.message,
            snapshot_version=row.snapshot_version,
            version_bumped=row.version_bumped,
        )

    def save_drifts(self, drifts: list[DriftRecord]) -> None:
        with self.Session() as session:
            for d in drifts:
                session.add(
                    DriftRow(
                        id=d.id,
                        datasource_id=d.datasource_id,
                        job_id=d.job_id,
                        kind=d.kind.value,
                        schema_name=d.schema_name,
                        table_name=d.table_name,
                        object_name=d.object_name,
                        before=d.before,
                        after=d.after,
                        detected_at=d.detected_at,
                    )
                )
            session.commit()

    def list_drifts(self, ds_id: str, kind: str | None = None) -> list[DriftRecord]:
        with self.Session() as session:
            rows = session.scalars(
                select(DriftRow).where(DriftRow.datasource_id == ds_id).order_by(DriftRow.detected_at.desc())
            ).all()
            items = [
                DriftRecord(
                    id=r.id,
                    datasource_id=r.datasource_id,
                    job_id=r.job_id,
                    kind=DriftKind(r.kind),
                    schema_name=r.schema_name,
                    table_name=r.table_name,
                    object_name=r.object_name,
                    before=r.before,
                    after=r.after,
                    detected_at=r.detected_at,
                )
                for r in rows
            ]
        if kind:
            items = [i for i in items if i.kind.value == kind]
        return items

    def save_snapshot(self, snap: Snapshot) -> Snapshot:
        with self.Session() as session:
            session.add(
                SnapshotRow(
                    id=new_id("snap"),
                    datasource_id=snap.datasource_id,
                    version=snap.version,
                    created_at=snap.created_at,
                    source_job_id=snap.source_job_id,
                    partial=snap.partial,
                    drift_count=snap.drift_count,
                    payload_json=json.dumps(
                        {k: table_to_dict(v) for k, v in snap.tables.items()}
                    ),
                )
            )
            session.commit()
        return snap

    def list_snapshots(self, ds_id: str) -> list[Snapshot]:
        ds = self.get_datasource(ds_id)
        current = ds.current_snapshot_version if ds else None
        with self.Session() as session:
            rows = session.scalars(
                select(SnapshotRow)
                .where(SnapshotRow.datasource_id == ds_id)
                .order_by(SnapshotRow.version.desc())
            ).all()
            return [
                Snapshot(
                    datasource_id=r.datasource_id,
                    version=r.version,
                    created_at=r.created_at,
                    source_job_id=r.source_job_id,
                    partial=r.partial,
                    drift_count=r.drift_count,
                    tables={k: table_from_dict(v) for k, v in json.loads(r.payload_json).items()},
                    is_current=r.version == current,
                )
                for r in rows
            ]

    def get_snapshot(self, ds_id: str, version: int) -> Snapshot | None:
        for snap in self.list_snapshots(ds_id):
            if snap.version == version:
                return snap
        return None
