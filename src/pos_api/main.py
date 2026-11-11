"""Mock restaurant POS API."""

from fastapi import FastAPI

app = FastAPI(
    title="Mock Restaurant POS API",
    version="0.1.0",
    description="A realistic mock POS used as the backend for restaurant-mcp-server.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
