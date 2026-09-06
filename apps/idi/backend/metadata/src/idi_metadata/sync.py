"""Incremental sync with drift detection."""

from __future__ import annotations

from croniter import croniter

from idi_backend.adapters import get_adapter
from idi_backend.domain import (
    Catalog,
    DataSourceStatus,
    Job,
    JobError,
    JobKind,
    JobStatus,
    new_id,
    utcnow,
)
from idi_backend.store import Store
from idi_metadata.diff import diff_catalogs
from idi_metadata.extract import MetadataBusyError, create_snapshot_from_catalog


def validate_cron(expr: str) -> bool:
    try:
        croniter(expr)
        return True
    except (ValueError, KeyError, TypeError):
        return False


def next_cron_time(expr: str):
    return croniter(expr, utcnow()).get_next(type(utcnow()))


def run_sync(store: Store, datasource_id: str, *, scheduled: bool = False) -> Job:
    ds = store.get_datasource(datasource_id)
    if not ds:
        raise KeyError("数据源不存在")

    if ds.status != DataSourceStatus.READY:
        job = Job(id=new_id("job"), datasource_id=datasource_id, kind=JobKind.SYNC)
        job.status = JobStatus.SKIPPED
        job.message = f"数据源状态为 {ds.status.value}，跳过同步"
        job.started_at = utcnow()
        job.finished_at = utcnow()
        store.save_job(job)
        return job

    lock = store.lock_for(datasource_id)
    if not lock.acquire(blocking=False):
        raise MetadataBusyError("已有进行中的抽取或同步")
    try:
        if store.active_job(datasource_id):
            raise MetadataBusyError("已有进行中的抽取或同步")

        job = Job(id=new_id("job"), datasource_id=datasource_id, kind=JobKind.SYNC)
        job.status = JobStatus.RUNNING
        job.started_at = utcnow()
        store.save_job(job)

        try:
            before = store.load_catalog(datasource_id)
            adapter = get_adapter(ds.config.dialect)
            result = adapter.reflect(ds.config)
            after = Catalog(datasource_id=datasource_id)
            for table in result.tables:
                after.upsert_table(table)

            drifts = diff_catalogs(datasource_id, job.id, before, after)
            store.replace_catalog(after)
            if drifts:
                store.save_drifts(drifts)

            job.progress_done = len(after.tables)
            job.progress_total = len(after.tables) + len(result.errors)
            job.errors = [JobError(object_name=n, reason=r) for n, r in result.errors]
            job.finished_at = utcnow()

            if result.errors and after.tables:
                job.status = JobStatus.PARTIAL
            elif result.errors and not after.tables:
                job.status = JobStatus.FAILED
                job.message = "同步失败"
                store.save_job(job)
                return job
            else:
                job.status = JobStatus.SUCCEEDED

            if drifts and job.status in {JobStatus.SUCCEEDED, JobStatus.PARTIAL}:
                create_snapshot_from_catalog(
                    store,
                    ds,
                    job,
                    after,
                    partial=job.status == JobStatus.PARTIAL,
                    drift_count=len(drifts),
                )
            else:
                job.version_bumped = False
                job.snapshot_version = ds.current_snapshot_version
                job.message = (
                    f"与版本 {ds.current_snapshot_version} 一致，未升版"
                    if ds.current_snapshot_version
                    else "无漂移"
                )

            if scheduled and ds.sync_cron:
                ds.next_sync_at = next_cron_time(ds.sync_cron)
                store.save_datasource(ds)

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
