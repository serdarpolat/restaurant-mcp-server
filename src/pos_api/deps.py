from typing import Annotated

from fastapi import Depends, Header
from sqlmodel import Session

from pos_api.db.database import get_session

SessionDep = Annotated[Session, Depends(get_session)]


def get_actor(x_actor: Annotated[str | None, Header()] = None) -> str:
    """Who is calling. The MCP server sends e.g. 'mcp:claude-desktop'."""
    return (x_actor or "api").strip()[:100]


ActorDep = Annotated[str, Depends(get_actor)]
