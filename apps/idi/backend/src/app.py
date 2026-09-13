"""FastAPI composition root for IDI datasource and metadata APIs."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from datasources.api import create_router as create_datasources_router
from infra.store import Store
from metadata.api import create_router as create_metadata_router

store = Store()
app = FastAPI(title="IDI Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(create_datasources_router(store))
app.include_router(create_metadata_router(store))
