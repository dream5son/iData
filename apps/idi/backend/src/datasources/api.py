"""Datasource REST boundary."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from datasources import service as svc
from infra.dialects import list_dialects
from infra.store import Store


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


def create_router(store: Store) -> APIRouter:
    router = APIRouter()

    @router.get("/api/dialects")
    def dialects() -> list[dict[str, Any]]:
        return list_dialects()

    @router.get("/api/datasources")
    def list_ds(
        q: str | None = None,
        dialect: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return [svc.serialize_datasource(d) for d in store.list_datasources(q=q, dialect=dialect, status=status)]

    @router.post("/api/datasources", status_code=201)
    def create_ds(body: CreateBody) -> dict[str, Any]:
        try:
            ds = svc.create_datasource(store, body.model_dump())
        except svc.ValidationError as exc:
            raise HTTPException(status_code=400, detail=exc.errors) from exc
        return svc.serialize_datasource(ds)

    @router.get("/api/datasources/{ds_id}")
    def get_ds(ds_id: str) -> dict[str, Any]:
        ds = store.get_datasource(ds_id)
        if not ds:
            raise HTTPException(404, "数据源不存在")
        return svc.serialize_datasource(ds)

    @router.patch("/api/datasources/{ds_id}")
    def patch_ds(ds_id: str, body: UpdateBody) -> dict[str, Any]:
        try:
            ds = svc.update_datasource(store, ds_id, body.model_dump(exclude_unset=True))
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except svc.ValidationError as exc:
            raise HTTPException(400, detail=exc.errors) from exc
        return svc.serialize_datasource(ds)

    @router.post("/api/datasources/{ds_id}/disable")
    def disable_ds(ds_id: str) -> dict[str, Any]:
        ds = store.get_datasource(ds_id)
        if not ds:
            raise HTTPException(404, "数据源不存在")
        ds.disable()
        store.save_datasource(ds)
        return svc.serialize_datasource(ds)

    @router.post("/api/datasources/{ds_id}/enable")
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

    @router.delete("/api/datasources/{ds_id}")
    def delete_ds(ds_id: str, body: DeleteBody) -> dict[str, str]:
        try:
            svc.delete_datasource(store, ds_id, cascade=body.cascade, confirm=body.confirm)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except svc.ValidationError as exc:
            raise HTTPException(400, detail=exc.errors) from exc
        return {"status": "deleted"}

    @router.post("/api/datasources/test")
    def test_form(body: TestBody) -> dict[str, Any]:
        try:
            return svc.test_ephemeral(body.model_dump())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, str(exc)) from exc

    @router.post("/api/datasources/{ds_id}/test")
    def test_ds(ds_id: str) -> dict[str, Any]:
        try:
            ds = svc.test_saved(store, ds_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return svc.serialize_datasource(ds)

    return router
