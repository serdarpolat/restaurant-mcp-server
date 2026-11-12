"""Thin async HTTP client for the POS API.

Two modes:
- POS_API_URL set   -> talk to a running POS API over HTTP.
- POS_API_URL unset -> "embedded" mode: the POS API runs inside this process with its own
  SQLite demo database, so the MCP server works with zero setup.

API errors are re-raised as ToolError so the model sees the API's own message
(e.g. the list of valid options) and can recover or ask the user.
"""

import os
import sys
from pathlib import Path
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

POS_API_URL = os.getenv("POS_API_URL")
ACTOR = os.getenv("POS_MCP_ACTOR", "mcp:assistant")

_client: httpx.AsyncClient | None = None


def prepare_embedded() -> None:
    """Create/refresh the demo database for embedded mode. Logs to stderr (stdout is MCP)."""
    if "DATABASE_URL" not in os.environ:
        data_dir = Path.home() / ".restaurant-mcp-server"
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{(data_dir / 'restaurant.db').as_posix()}"
    from pos_api.db.seed import ensure_demo_data

    print("restaurant-pos: preparing demo data...", file=sys.stderr)
    print(f"restaurant-pos: demo data {ensure_demo_data()}", file=sys.stderr)


def _embedded_client() -> httpx.AsyncClient:
    from pos_api.main import app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://embedded")


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        if POS_API_URL:
            _client = httpx.AsyncClient(base_url=POS_API_URL, timeout=15)
        else:
            _client = _embedded_client()
    return _client


def set_client(client: httpx.AsyncClient | None) -> None:
    """Inject a client (used by tests to talk to the API in-process)."""
    global _client
    _client = client


async def request(method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        response = await get_client().request(
            method, path, params=params, json=json, headers={"X-Actor": ACTOR}
        )
    except httpx.HTTPError as exc:
        raise ToolError(
            f"Cannot reach the POS API at {POS_API_URL} ({type(exc).__name__}). "
            "Is it running? Start it with: restaurant-pos-api"
        ) from exc
    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise ToolError(f"POS API error {response.status_code}: {detail}")
    return response.json()


async def get(path: str, **params: Any) -> Any:
    return await request("GET", path, params=params)


async def post(path: str, json: Any) -> Any:
    return await request("POST", path, json=json)


async def patch(path: str, json: Any) -> Any:
    return await request("PATCH", path, json=json)
