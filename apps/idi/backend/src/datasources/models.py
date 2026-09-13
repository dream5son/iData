"""Datasource lifecycle models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from infra.ids import utcnow


class DataSourceStatus(str, Enum):
    DRAFT = "draft"
    TEST_FAILED = "test_failed"
    READY = "ready"
    DISABLED = "disabled"


class StepOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


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
