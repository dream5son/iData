"""Dialect adapter registry: one interface, many SQL dialects."""

from __future__ import annotations

import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from idi_backend.domain import (
    ColumnMeta,
    ConnectionConfig,
    ConnectionTestReport,
    Dialect,
    IndexMeta,
    StepOutcome,
    TableMeta,
    TestStepResult,
    utcnow,
)

TEST_STEP_NAMES = [
    "network",
    "credentials",
    "readonly_txn",
    "dialect",
]


@dataclass
class ReflectResult:
    tables: list[TableMeta]
    errors: list[tuple[str, str]]


class DialectAdapter(ABC):
    dialect: Dialect

    @abstractmethod
    def required_params(self) -> list[str]:
        ...

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        missing = [key for key in self.required_params() if not params.get(key)]
        if "port" in self.required_params() or "host" in params:
            port = params.get("port")
            if port is not None and not str(port).isdigit():
                missing.append("port")
        return missing

    def test_connection(self, config: ConnectionConfig) -> ConnectionTestReport:
        steps: list[TestStepResult] = []
        try:
            self._check_network(config.params)
            steps.append(TestStepResult("network", StepOutcome.PASSED, "网络可达"))
        except Exception as exc:  # noqa: BLE001 — boundary: surface readable failure
            return ConnectionTestReport.from_failure_at(0, TEST_STEP_NAMES, str(exc))

        try:
            engine = self._create_engine(config)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            steps.append(TestStepResult("credentials", StepOutcome.PASSED, "鉴权成功"))
        except Exception as exc:  # noqa: BLE001
            return ConnectionTestReport(
                steps=steps
                + [
                    TestStepResult("credentials", StepOutcome.FAILED, f"认证失败: {exc}"),
                    TestStepResult("readonly_txn", StepOutcome.SKIPPED, "未执行"),
                    TestStepResult("dialect", StepOutcome.SKIPPED, "未执行"),
                ],
                overall_passed=False,
                tested_at=utcnow(),
            )

        try:
            self._check_readonly(engine)
            steps.append(TestStepResult("readonly_txn", StepOutcome.PASSED, "只读事务可用"))
        except Exception as exc:  # noqa: BLE001
            return ConnectionTestReport(
                steps=steps
                + [
                    TestStepResult("readonly_txn", StepOutcome.FAILED, str(exc)),
                    TestStepResult("dialect", StepOutcome.SKIPPED, "未执行"),
                ],
                overall_passed=False,
                tested_at=utcnow(),
            )

        try:
            self._check_dialect(engine)
            steps.append(TestStepResult("dialect", StepOutcome.PASSED, "方言探测成功"))
        except Exception as exc:  # noqa: BLE001
            return ConnectionTestReport(
                steps=steps + [TestStepResult("dialect", StepOutcome.FAILED, str(exc))],
                overall_passed=False,
                tested_at=utcnow(),
            )

        engine.dispose()
        return ConnectionTestReport(steps=steps, overall_passed=True, tested_at=utcnow())

    def reflect(self, config: ConnectionConfig) -> ReflectResult:
        engine = self._create_engine(config)
        try:
            return self._reflect_engine(engine)
        finally:
            engine.dispose()

    def _check_network(self, params: dict[str, Any]) -> None:
        if params.get("__sqlite_path"):
            return
        host = params.get("host") or params.get("account") or params.get("endpoint")
        port = int(params.get("port") or 0)
        if not host:
            raise ConnectionError("缺少主机或 endpoint")
        if host in {"demo.local", "localhost", "127.0.0.1"} and params.get("__skip_tcp"):
            return
        if not port:
            raise ConnectionError("缺少端口")
        with socket.create_connection((host, port), timeout=float(params.get("connect_timeout", 3))):
            pass

    def _check_readonly(self, engine: Engine) -> None:
        with engine.connect() as conn:
            if engine.dialect.name == "sqlite":
                conn.execute(text("PRAGMA query_only = ON"))
                try:
                    conn.execute(text("CREATE TABLE idi_probe_should_fail (id INTEGER)"))
                except Exception:
                    return
                raise RuntimeError("目标连接不支持只读收口：探测写操作未被拒绝")
            trans = conn.begin()
            try:
                conn.execute(text("SET TRANSACTION READ ONLY"))
            except Exception:
                # Some dialects ignore SET; still refuse if writes succeed later.
                pass
            try:
                conn.execute(text("CREATE TABLE idi_probe_should_fail (id INT)"))
                trans.rollback()
                raise RuntimeError("目标连接不支持只读事务或账号具备不可接受的写能力")
            except RuntimeError:
                raise
            except Exception:
                trans.rollback()

    def _check_dialect(self, engine: Engine) -> None:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 WHERE 1 = 0"))

    @abstractmethod
    def _create_engine(self, config: ConnectionConfig) -> Engine:
        ...

    def _reflect_engine(self, engine: Engine) -> ReflectResult:
        insp = inspect(engine)
        tables: list[TableMeta] = []
        errors: list[tuple[str, str]] = []
        schema_names = insp.get_schema_names() or [None]
        for schema in schema_names:
            try:
                table_names = insp.get_table_names(schema=schema)
            except Exception as exc:  # noqa: BLE001
                errors.append((str(schema), str(exc)))
                continue
            for name in table_names:
                key = f"{schema or 'main'}.{name}"
                try:
                    tables.append(self._reflect_table(insp, schema, name))
                except Exception as exc:  # noqa: BLE001
                    errors.append((key, str(exc)))
        return ReflectResult(tables=tables, errors=errors)

    def _reflect_table(self, insp: Any, schema: str | None, name: str) -> TableMeta:
        schema_name = schema or "main"
        columns: list[ColumnMeta] = []
        pk = set(insp.get_pk_constraint(name, schema=schema).get("constrained_columns") or [])
        for col in insp.get_columns(name, schema=schema):
            columns.append(
                ColumnMeta(
                    name=col["name"],
                    data_type=str(col.get("type")),
                    nullable=bool(col.get("nullable", True)),
                    is_primary_key=col["name"] in pk,
                    default=str(col["default"]) if col.get("default") is not None else None,
                    precision=None,
                    comment=col.get("comment"),
                )
            )
        indexes: list[IndexMeta] = []
        for idx in insp.get_indexes(name, schema=schema):
            indexes.append(
                IndexMeta(
                    name=idx.get("name") or "unnamed",
                    columns=list(idx.get("column_names") or []),
                    unique=bool(idx.get("unique")),
                    index_type=idx.get("type"),
                )
            )
        return TableMeta(
            schema_name=schema_name,
            name=name,
            table_type="BASE TABLE",
            comment=None,
            columns=columns,
            indexes=indexes,
        )


class SqlAlchemyUrlAdapter(DialectAdapter):
    """Shared adapter for URL-based SQLAlchemy dialects, with SQLite bridge for local proof."""

    def __init__(self, dialect: Dialect, driver_prefix: str, required: list[str]):
        self.dialect = dialect
        self.driver_prefix = driver_prefix
        self._required = required

    def required_params(self) -> list[str]:
        return list(self._required)

    def _create_engine(self, config: ConnectionConfig) -> Engine:
        params = config.params
        sqlite_path = params.get("__sqlite_path")
        if sqlite_path:
            return create_engine(f"sqlite+pysqlite:///{sqlite_path}", future=True)
        user = params.get("username") or params.get("user") or ""
        password = params.get("password") or ""
        host = params.get("host")
        port = params.get("port")
        database = params.get("database") or params.get("project") or ""
        url = f"{self.driver_prefix}://{user}:{password}@{host}:{port}/{database}"
        return create_engine(url, future=True, pool_pre_ping=True)


class HostPortAdapter(SqlAlchemyUrlAdapter):
    def required_params(self) -> list[str]:
        base = ["host", "port", "database", "username", "password"]
        return base


class SnowflakeAdapter(DialectAdapter):
    dialect = Dialect.SNOWFLAKE

    def required_params(self) -> list[str]:
        return ["account", "username", "password", "database", "warehouse"]

    def _create_engine(self, config: ConnectionConfig) -> Engine:
        if config.params.get("__sqlite_path"):
            return create_engine(f"sqlite+pysqlite:///{config.params['__sqlite_path']}", future=True)
        p = config.params
        url = (
            f"snowflake://{p['username']}:{p['password']}@{p['account']}/"
            f"{p['database']}?warehouse={p['warehouse']}"
        )
        return create_engine(url, future=True)


class BigQueryAdapter(DialectAdapter):
    dialect = Dialect.BIGQUERY

    def required_params(self) -> list[str]:
        return ["project", "dataset"]

    def _create_engine(self, config: ConnectionConfig) -> Engine:
        if config.params.get("__sqlite_path"):
            return create_engine(f"sqlite+pysqlite:///{config.params['__sqlite_path']}", future=True)
        project = config.params["project"]
        return create_engine(f"bigquery://{project}", future=True)


class DatabricksAdapter(DialectAdapter):
    dialect = Dialect.DATABRICKS

    def required_params(self) -> list[str]:
        return ["host", "http_path", "token"]

    def _create_engine(self, config: ConnectionConfig) -> Engine:
        if config.params.get("__sqlite_path"):
            return create_engine(f"sqlite+pysqlite:///{config.params['__sqlite_path']}", future=True)
        p = config.params
        host = p["host"].replace("https://", "")
        url = f"databricks://token:{p['token']}@{host}?http_path={p['http_path']}"
        return create_engine(url, future=True)


_REGISTRY: dict[Dialect, DialectAdapter] = {}


def _register(adapter: DialectAdapter) -> None:
    _REGISTRY[adapter.dialect] = adapter


def get_adapter(dialect: Dialect) -> DialectAdapter:
    try:
        return _REGISTRY[dialect]
    except KeyError as exc:
        raise ValueError(f"未适配方言: {dialect}") from exc


def list_dialects() -> list[dict[str, Any]]:
    from idi_backend.domain import DEFAULT_PORTS, DIALECT_LABELS

    return [
        {
            "id": d.value,
            "label": DIALECT_LABELS[d],
            "default_port": DEFAULT_PORTS.get(d),
            "required_params": get_adapter(d).required_params(),
        }
        for d in Dialect
    ]


def _bootstrap() -> None:
    host_port = [
        (Dialect.POSTGRESQL, "postgresql+psycopg"),
        (Dialect.MYSQL, "mysql+pymysql"),
        (Dialect.SQLSERVER, "mssql+pyodbc"),
        (Dialect.ORACLE, "oracle+oracledb"),
        (Dialect.DB2, "db2+ibm_db"),
        (Dialect.REDSHIFT, "postgresql+psycopg"),
        (Dialect.CLICKHOUSE, "clickhouse+native"),
        (Dialect.DORIS, "mysql+pymysql"),
        (Dialect.STARROCKS, "mysql+pymysql"),
        (Dialect.TIDB, "mysql+pymysql"),
        (Dialect.GREENPLUM, "postgresql+psycopg"),
    ]
    for dialect, prefix in host_port:
        _register(
            SqlAlchemyUrlAdapter(
                dialect,
                prefix,
                ["host", "port", "database", "username", "password"],
            )
        )
    _register(SnowflakeAdapter())
    _register(BigQueryAdapter())
    _register(DatabricksAdapter())


_bootstrap()
