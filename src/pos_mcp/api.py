"""Thin async HTTP client for the POS API.

API errors are re-raised as ToolError so the model sees the API's own message
(e.g. the list of valid options) and can recover or ask the user.
"""

import os
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

POS_API_URL = os.getenv("POS_API_URL", "http://127.0.0.1:8000")
ACTOR = os.getenv("POS_MCP_ACTOR", "mcp:assistant")

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=POS_API_URL, timeout=15)
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
            "Is it running? Start it with: uvicorn pos_api.main:app"
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
