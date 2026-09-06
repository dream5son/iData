"""Domain models for IDI datasource lifecycle and metadata catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class DataSourceStatus(str, Enum):
    DRAFT = "draft"
    TEST_FAILED = "test_failed"
    READY = "ready"
    DISABLED = "disabled"


class StepOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


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


class Dialect(str, Enum):
    ORACLE = "oracle"
    SQLSERVER = "sqlserver"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    DB2 = "db2"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    REDSHIFT = "redshift"
    DATABRICKS = "databricks"
    CLICKHOUSE = "clickhouse"
    DORIS = "doris"
    STARROCKS = "starrocks"
    TIDB = "tidb"
    GREENPLUM = "greenplum"


DIALECT_LABELS: dict[Dialect, str] = {
    Dialect.ORACLE: "Oracle",
    Dialect.SQLSERVER: "Microsoft SQL Server",
    Dialect.POSTGRESQL: "PostgreSQL",
    Dialect.MYSQL: "MySQL",
    Dialect.DB2: "IBM DB2",
    Dialect.SNOWFLAKE: "Snowflake",
    Dialect.BIGQUERY: "Google BigQuery",
    Dialect.REDSHIFT: "Amazon Redshift",
    Dialect.DATABRICKS: "Databricks Lakehouse",
    Dialect.CLICKHOUSE: "ClickHouse",
    Dialect.DORIS: "Apache Doris",
    Dialect.STARROCKS: "StarRocks",
    Dialect.TIDB: "TiDB",
    Dialect.GREENPLUM: "Greenplum",
}

DEFAULT_PORTS: dict[Dialect, int] = {
    Dialect.ORACLE: 1521,
    Dialect.SQLSERVER: 1433,
    Dialect.POSTGRESQL: 5432,
    Dialect.MYSQL: 3306,
    Dialect.DB2: 50000,
    Dialect.SNOWFLAKE: 443,
    Dialect.BIGQUERY: 443,
    Dialect.REDSHIFT: 5439,
    Dialect.DATABRICKS: 443,
    Dialect.CLICKHOUSE: 9000,
    Dialect.DORIS: 9030,
    Dialect.STARROCKS: 9030,
    Dialect.TIDB: 4000,
    Dialect.GREENPLUM: 5432,
}

SECRET_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "private_key",
        "service_account_json",
        "api_key",
    }
)


@dataclass
class ConnectionConfig:
    dialect: Dialect
    params: dict[str, Any]
    readonly_intent: bool = True

    def public_params(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in self.params.items():
            if key.lower() in SECRET_KEYS or key.startswith("secret_"):
                out[key] = None
                out[f"{key}__configured"] = bool(value)
            else:
                out[key] = value
        return out


@dataclass
class TestStepResult:
    name: str
    outcome: StepOutcome
    message: str = ""


@dataclass
class ConnectionTestReport:
    steps: list[TestStepResult]
    overall_passed: bool
    tested_at: datetime = field(default_factory=utcnow)

    @staticmethod
    def from_failure_at(index: int, names: list[str], message: str) -> ConnectionTestReport:
        steps: list[TestStepResult] = []
        for i, name in enumerate(names):
            if i < index:
                steps.append(TestStepResult(name=name, outcome=StepOutcome.PASSED))
            elif i == index:
                steps.append(TestStepResult(name=name, outcome=StepOutcome.FAILED, message=message))
            else:
                steps.append(TestStepResult(name=name, outcome=StepOutcome.SKIPPED, message="未执行"))
        return ConnectionTestReport(steps=steps, overall_passed=False)


@dataclass
class DataSource:
    id: str
    name: str
    config: ConnectionConfig
    status: DataSourceStatus = DataSourceStatus.DRAFT
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    last_tested_at: datetime | None = None
    last_test: ConnectionTestReport | None = None
    current_snapshot_version: int | None = None
    sync_enabled: bool = False
    sync_cron: str | None = None
    next_sync_at: datetime | None = None

    def transition_after_test(self, passed: bool) -> None:
        if self.status == DataSourceStatus.DISABLED:
            return
        self.status = DataSourceStatus.READY if passed else DataSourceStatus.TEST_FAILED

    def disable(self) -> None:
        self.status = DataSourceStatus.DISABLED
        self.updated_at = utcnow()

    def enable(self) -> None:
        if self.status != DataSourceStatus.DISABLED:
            raise ValueError("只有已停用的数据源可以启用")
        self.status = DataSourceStatus.DRAFT
        self.updated_at = utcnow()


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
