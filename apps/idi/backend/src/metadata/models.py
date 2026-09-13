"""Metadata catalog, job, drift, and snapshot models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from infra.ids import utcnow


class JobKind(str, Enum):
    EXTRACT = "extract"
    SYNC = "sync"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class DriftKind(str, Enum):
    TABLE_ADDED = "table_added"
    TABLE_REMOVED = "table_removed"
    COLUMN_ADDED = "column_added"
    COLUMN_REMOVED = "column_removed"
    TYPE_CHANGED = "type_changed"
    COLUMN_CONSTRAINT_CHANGED = "column_constraint_changed"
    INDEX_OR_PARTITION_CHANGED = "index_or_partition_changed"


@dataclass
class ColumnMeta:
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    default: str | None = None
    precision: str | None = None
    comment: str | None = None


@dataclass
class IndexMeta:
    name: str
    columns: list[str]
    unique: bool = False
    index_type: str | None = None


@dataclass
class TableMeta:
    schema_name: str
    name: str
    table_type: str = "BASE TABLE"
    created_at: str | None = None
    storage_size: str | None = None
    comment: str | None = None
    columns: list[ColumnMeta] = field(default_factory=list)
    indexes: list[IndexMeta] = field(default_factory=list)
    partition_keys: list[str] = field(default_factory=list)
    bucket_keys: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.schema_name}.{self.name}"


@dataclass
class Catalog:
    datasource_id: str
    tables: dict[str, TableMeta] = field(default_factory=dict)

    def upsert_table(self, table: TableMeta) -> None:
        self.tables[table.key] = table

    def remove_table(self, key: str) -> None:
        self.tables.pop(key, None)


@dataclass
class JobError:
    object_name: str
    reason: str


@dataclass
class Job:
    id: str
    datasource_id: str
    kind: JobKind
    status: JobStatus = JobStatus.QUEUED
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress_done: int = 0
    progress_total: int | None = None
    errors: list[JobError] = field(default_factory=list)
    message: str = ""
    snapshot_version: int | None = None
    version_bumped: bool = False


@dataclass
class DriftRecord:
    id: str
    datasource_id: str
    job_id: str
    kind: DriftKind
    schema_name: str
    table_name: str
    object_name: str
    before: str | None
    after: str | None
    detected_at: datetime = field(default_factory=utcnow)


@dataclass
class Snapshot:
    datasource_id: str
    version: int
    created_at: datetime
    source_job_id: str
    partial: bool
    drift_count: int
    tables: dict[str, TableMeta]
    is_current: bool = False
