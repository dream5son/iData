"""Structural diff between two catalogs."""

from __future__ import annotations

from infra.ids import new_id, utcnow
from metadata.models import Catalog, DriftKind, DriftRecord, TableMeta


def _col_sig(col) -> str:
    return (
        f"type={col.data_type}|null={col.nullable}|pk={col.is_primary_key}|"
        f"default={col.default}|precision={col.precision}"
    )


def _idx_sig(idx) -> str:
    return f"cols={','.join(idx.columns)}|unique={idx.unique}|type={idx.index_type}"


def diff_catalogs(
    datasource_id: str,
    job_id: str,
    before: Catalog,
    after: Catalog,
) -> list[DriftRecord]:
    drifts: list[DriftRecord] = []
    before_keys = set(before.tables)
    after_keys = set(after.tables)

    for key in sorted(after_keys - before_keys):
        table = after.tables[key]
        drifts.append(
            DriftRecord(
                id=new_id("dft"),
                datasource_id=datasource_id,
                job_id=job_id,
                kind=DriftKind.TABLE_ADDED,
                schema_name=table.schema_name,
                table_name=table.name,
                object_name=table.name,
                before=None,
                after=table.key,
                detected_at=utcnow(),
            )
        )

    for key in sorted(before_keys - after_keys):
        table = before.tables[key]
        drifts.append(
            DriftRecord(
                id=new_id("dft"),
                datasource_id=datasource_id,
                job_id=job_id,
                kind=DriftKind.TABLE_REMOVED,
                schema_name=table.schema_name,
                table_name=table.name,
                object_name=table.name,
                before=table.key,
                after=None,
                detected_at=utcnow(),
            )
        )

    for key in sorted(before_keys & after_keys):
        drifts.extend(_diff_table(datasource_id, job_id, before.tables[key], after.tables[key]))
    return drifts


def _diff_table(
    datasource_id: str,
    job_id: str,
    old: TableMeta,
    new: TableMeta,
) -> list[DriftRecord]:
    drifts: list[DriftRecord] = []
    old_cols = {c.name: c for c in old.columns}
    new_cols = {c.name: c for c in new.columns}

    for name in sorted(set(new_cols) - set(old_cols)):
        drifts.append(
            DriftRecord(
                id=new_id("dft"),
                datasource_id=datasource_id,
                job_id=job_id,
                kind=DriftKind.COLUMN_ADDED,
                schema_name=new.schema_name,
                table_name=new.name,
                object_name=name,
                before=None,
                after=_col_sig(new_cols[name]),
            )
        )
    for name in sorted(set(old_cols) - set(new_cols)):
        drifts.append(
            DriftRecord(
                id=new_id("dft"),
                datasource_id=datasource_id,
                job_id=job_id,
                kind=DriftKind.COLUMN_REMOVED,
                schema_name=old.schema_name,
                table_name=old.name,
                object_name=name,
                before=_col_sig(old_cols[name]),
                after=None,
            )
        )
    for name in sorted(set(old_cols) & set(new_cols)):
        o, n = old_cols[name], new_cols[name]
        if o.data_type != n.data_type or o.precision != n.precision:
            drifts.append(
                DriftRecord(
                    id=new_id("dft"),
                    datasource_id=datasource_id,
                    job_id=job_id,
                    kind=DriftKind.TYPE_CHANGED,
                    schema_name=new.schema_name,
                    table_name=new.name,
                    object_name=name,
                    before=_col_sig(o),
                    after=_col_sig(n),
                )
            )
        elif (
            o.nullable != n.nullable
            or o.is_primary_key != n.is_primary_key
            or o.default != n.default
        ):
            drifts.append(
                DriftRecord(
                    id=new_id("dft"),
                    datasource_id=datasource_id,
                    job_id=job_id,
                    kind=DriftKind.COLUMN_CONSTRAINT_CHANGED,
                    schema_name=new.schema_name,
                    table_name=new.name,
                    object_name=name,
                    before=_col_sig(o),
                    after=_col_sig(n),
                )
            )

    old_idx = {i.name: i for i in old.indexes}
    new_idx = {i.name: i for i in new.indexes}
    if set(old_idx) != set(new_idx) or any(
        _idx_sig(old_idx[n]) != _idx_sig(new_idx[n]) for n in set(old_idx) & set(new_idx)
    ):
        drifts.append(
            DriftRecord(
                id=new_id("dft"),
                datasource_id=datasource_id,
                job_id=job_id,
                kind=DriftKind.INDEX_OR_PARTITION_CHANGED,
                schema_name=new.schema_name,
                table_name=new.name,
                object_name=new.name,
                before=";".join(_idx_sig(i) for i in old.indexes),
                after=";".join(_idx_sig(i) for i in new.indexes),
            )
        )
    elif old.partition_keys != new.partition_keys or old.bucket_keys != new.bucket_keys:
        drifts.append(
            DriftRecord(
                id=new_id("dft"),
                datasource_id=datasource_id,
                job_id=job_id,
                kind=DriftKind.INDEX_OR_PARTITION_CHANGED,
                schema_name=new.schema_name,
                table_name=new.name,
                object_name=new.name,
                before=f"part={old.partition_keys}|bucket={old.bucket_keys}",
                after=f"part={new.partition_keys}|bucket={new.bucket_keys}",
            )
        )
    return drifts
