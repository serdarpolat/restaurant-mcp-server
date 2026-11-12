"""Human-in-the-loop confirmation for risky write actions.

Two layers, strongest available first:

1. Elicitation: if the client supports it, the *user* (not the model) is asked
   to approve through the client's own UI. The model cannot answer for them.
2. Preview + token fallback: the first call executes nothing and returns a
   preview plus a short-lived token bound to the exact arguments. Only a second
   call with that token executes. This guarantees the action is previewed and
   that what runs is exactly what was previewed; asking the user in between
   relies on the model following the tool instructions.

Each guarded tool has a small resolver (see server.py) that builds the preview
and returns `gate(...)`. The MCP SDK runs the resolver before the tool body.
"""

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from mcp.server.elicitation import AcceptedElicitation, ElicitationResult
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.resolve import Elicit
from pydantic import BaseModel, Field

TOKEN_TTL_SECONDS = 300
_pending: dict[str, tuple[str, float]] = {}  # token -> (fingerprint, expires_at)

DECLINED = {"status": "declined", "message": "The user declined. Nothing was changed."}


class Approval(BaseModel):
    approve: bool = Field(description="Approve this action?")


@dataclass
class Gate:
    """Decision made without asking the client: proceed, or answer the model with `response`."""

    response: dict[str, Any] | None = None


def _fingerprint(action: str, args: dict[str, Any]) -> str:
    raw = json.dumps({"action": action, "args": args}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _supports_elicitation(ctx: Context) -> bool:
    caps = ctx.client_capabilities
    return bool(caps and caps.elicitation)


def gate(
    ctx: Context, action: str, args: dict[str, Any], preview: str, token: str | None
) -> Elicit[Approval] | Gate:
    fingerprint = _fingerprint(action, args)

    if token:
        stored = _pending.pop(token, None)
        if stored and stored[0] == fingerprint and stored[1] > time.time():
            return Gate()
        return Gate(
            {
                "status": "confirmation_invalid",
                "message": "The confirmation token is invalid, expired, or the arguments "
                "changed. Call again without a token to get a fresh preview.",
            }
        )

    if _supports_elicitation(ctx):
        return Elicit(f"{preview}\n\nApprove?", Approval)

    now = time.time()
    for old in [t for t, (_, exp) in _pending.items() if exp < now]:
        del _pending[old]
    new_token = secrets.token_urlsafe(8)
    _pending[new_token] = (fingerprint, now + TOKEN_TTL_SECONDS)
    return Gate(
        {
            "status": "confirmation_required",
            "preview": preview,
            "confirmation_token": new_token,
            "message": "NOTHING HAS BEEN CHANGED YET. Show this preview to the user and ask "
            "for explicit approval. Only if they approve, call this tool again with the same "
            "arguments plus this confirmation_token.",
        }
    )


def blocked(outcome: ElicitationResult[Any]) -> dict[str, Any] | None:
    """None if the action may run, otherwise the response to return to the model."""
    if not isinstance(outcome, AcceptedElicitation):
        return DECLINED
    data = outcome.data
    if isinstance(data, Gate):
        return data.response
    return None if data.approve else DECLINED
