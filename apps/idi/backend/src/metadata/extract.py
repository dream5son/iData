"""Full extract and snapshot helpers."""

from __future__ import annotations

from datasources.models import DataSource, DataSourceStatus
from infra.dialects import get_adapter
from infra.ids import new_id, utcnow
from infra.store import Store
from metadata.models import Catalog, Job, JobError, JobKind, JobStatus, Snapshot


class MetadataBusyError(RuntimeError):
    pass


class NotReadyError(RuntimeError):
    pass


def create_snapshot_from_catalog(
    store: Store,
    ds: DataSource,
    job: Job,
    catalog: Catalog,
    *,
    partial: bool,
    drift_count: int,
) -> Snapshot:
    next_version = (ds.current_snapshot_version or 0) + 1
    snap = Snapshot(
        datasource_id=ds.id,
        version=next_version,
        created_at=utcnow(),
        source_job_id=job.id,
        partial=partial,
        drift_count=drift_count,
        tables=dict(catalog.tables),
        is_current=True,
    )
    store.save_snapshot(snap)
    ds.current_snapshot_version = next_version
    ds.updated_at = utcnow()
    store.save_datasource(ds)
    job.snapshot_version = next_version
    job.version_bumped = True
    return snap


def run_extract(store: Store, datasource_id: str) -> Job:
    ds = store.get_datasource(datasource_id)
    if not ds:
        raise KeyError("数据源不存在")
    if ds.status != DataSourceStatus.READY:
        raise NotReadyError("须先使数据源处于已就绪")

    lock = store.lock_for(datasource_id)
    if not lock.acquire(blocking=False):
        raise MetadataBusyError("已有进行中的抽取或同步")
    try:
        if store.active_job(datasource_id):
            raise MetadataBusyError("已有进行中的抽取或同步")

        job = Job(id=new_id("job"), datasource_id=datasource_id, kind=JobKind.EXTRACT)
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        store.save_job(job)

        try:
            adapter = get_adapter(ds.config.dialect)
            result = adapter.reflect(ds.config)
            catalog = Catalog(datasource_id=datasource_id)
            for table in result.tables:
                catalog.upsert_table(table)
            store.replace_catalog(catalog)

            job.progress_done = len(result.tables)
            job.progress_total = len(result.tables) + len(result.errors)
            job.errors = [JobError(object_name=n, reason=r) for n, r in result.errors]
            job.finished_at = utcnow()
            if result.errors and result.tables:
                job.status = JobStatus.PARTIAL
            elif result.errors and not result.tables:
                job.status = JobStatus.FAILED
                job.message = "抽取失败"
                store.save_job(job)
                return job
            else:
                job.status = JobStatus.SUCCEEDED

            create_snapshot_from_catalog(
                store,
                ds,
                job,
                catalog,
                partial=job.status == JobStatus.PARTIAL,
                drift_count=0,
            )
            store.save_job(job)
            return job
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.FAILED
            job.message = str(exc)
            job.finished_at = utcnow()
            store.save_job(job)
            return job
    finally:
        lock.release()
