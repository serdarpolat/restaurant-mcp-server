"""Mock restaurant POS API."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from pos_api.db.database import create_db_and_tables
from pos_api.errors import DomainError
from pos_api.routers import audit, inventory, menu, orders, reports, staff, tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(
    title="Mock Restaurant POS API",
    version="0.1.0",
    description=(
        "A realistic mock POS used as the backend for restaurant-mcp-server. "
        "All timestamps are in the restaurant's local time zone. "
        "Write requests can carry an `X-Actor` header, recorded in the audit log."
    ),
    lifespan=lifespan,
)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


for module in (menu, tables, orders, inventory, reports, staff, audit):
    app.include_router(module.router)
