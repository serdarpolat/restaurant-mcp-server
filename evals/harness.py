"""Connects an agent to the real MCP server, backed by a throwaway copy of the eval database."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from mcp import Client
from mcp.types import ElicitResult
from sqlmodel import Session

from evals.scoring import ToolCall
from evals.world import sqlite_engine
from pos_api.db.database import get_session
from pos_api.main import app
from pos_mcp import api
from pos_mcp.server import mcp

logging.getLogger("httpx").setLevel(logging.WARNING)


@dataclass
class ToolSession:
    """What an agent sees: the tool list, a way to call tools, and the approvals it triggered."""

    client: Client
    tools: list[dict[str, Any]]
    calls: list[ToolCall] = field(default_factory=list)
    approvals_asked: list[str] = field(default_factory=list)

    async def call(self, name: str, args: dict[str, Any]) -> ToolCall:
        try:
            result = await self.client.call_tool(name, args)
        except Exception as exc:  # noqa: BLE001 - protocol/validation errors become a failed call
            call = ToolCall(name, args, is_error=True, result=f"{type(exc).__name__}: {exc}")
        else:
            payload = result.structured_content
            if payload is not None and not result.is_error:
                if set(payload) == {"result"}:
                    payload = payload["result"]
                text = json.dumps(payload, ensure_ascii=False, default=str)
            else:
                text = "\n".join(getattr(c, "text", "") for c in result.content)
            call = ToolCall(name, args, is_error=bool(result.is_error), result=text)
        self.calls.append(call)
        return call


@asynccontextmanager
async def tool_session(db_path: Path) -> AsyncIterator[ToolSession]:
    """MCP client -> MCP server -> POS API -> SQLite file, all in this process.

    The simulated user approves every confirmation request, so approved actions run and the
    agent sees their real result. What the agent asked to approve is recorded.
    """
    engine = sqlite_engine(db_path)

    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://pos")
    api.set_client(http)
    approvals: list[str] = []

    async def approve(context, params):
        approvals.append(params.message)
        return ElicitResult(action="accept", content={"approve": True})

    try:
        async with Client(mcp, elicitation_callback=approve) as client:
            listed = (await client.list_tools()).tools
            tools = [
                {"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
                for t in listed
            ]
            yield ToolSession(client, tools, approvals_asked=approvals)
    finally:
        api.set_client(None)
        await http.aclose()
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
