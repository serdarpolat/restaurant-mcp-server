"""Human-in-the-loop confirmation for risky write actions.

Two layers, strongest available first:

1. Elicitation: if the client supports it, the *user* (not the model) is asked
   to approve through the client's own UI. The model cannot answer for them.
2. Preview + token fallback: the first call executes nothing and returns a
   preview plus a short-lived token bound to the exact arguments. Only a second
   call with that token executes. This guarantees the action is previewed and
   that what runs is exactly what was previewed; asking the user in between
   relies on the model following the tool instructions.

   The second call must also carry the user's own reply, word for word. A token alone
   let a model execute after the user had said "no, don't cancel it" (seen in LM Studio):
   a reply that refuses, or does not clearly approve, does not run the action. A model
   could still invent a "yes"; elicitation, or the client's own tool-call approval, is
   the hard guarantee.

   Pending tokens are kept in a small file, not in memory: some clients (LM Studio)
   reach the server through a new process between the preview and the approval,
   and an in-memory token would be lost. A rejected token always comes back with a
   fresh preview and token, so the model can ask the user again instead of stopping.

Each guarded tool has a small resolver (see server.py) that builds the preview
and returns `gate(...)`. The MCP SDK runs the resolver before the tool body.
"""

import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp.server.elicitation import AcceptedElicitation, ElicitationResult
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.resolve import Elicit
from pydantic import BaseModel, Field

from pos_api.text import normalize

TOKEN_TTL_SECONDS = 300

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


def _store_path() -> Path:
    base = os.getenv("POS_MCP_STATE_DIR") or Path.home() / ".restaurant-mcp-server"
    return Path(base) / "pending_confirmations.json"


def _load() -> dict[str, dict[str, Any]]:
    """Pending tokens that have not expired: token -> {action, fingerprint, args, expires}."""
    try:
        pending = json.loads(_store_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    now = time.time()
    return {t: p for t, p in pending.items() if isinstance(p, dict) and p.get("expires", 0) > now}


def _save(pending: dict[str, dict[str, Any]]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(pending, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def _why_rejected(stored: dict[str, Any] | None, action: str, args: dict[str, Any]) -> str:
    if stored is None:
        return (
            "The confirmation token is unknown: it expired (tokens last "
            f"{TOKEN_TTL_SECONDS // 60} minutes), was already used, or was copied wrongly."
        )
    if stored["action"] != action:
        return f"The confirmation token was issued for {stored['action']}, not {action}."
    old = stored.get("args", {})
    changed = [
        f"{key} ({old.get(key)!r} -> {args.get(key)!r})"
        for key in sorted(set(old) | set(args))
        if json.dumps(old.get(key), default=str) != json.dumps(args.get(key), default=str)
    ]
    return "The arguments changed since the preview: " + ", ".join(changed) + "."


def _issue(action: str, args: dict[str, Any], preview: str, why: str | None) -> Gate:
    pending = _load()
    token = secrets.token_urlsafe(8)
    pending[token] = {
        "action": action,
        "fingerprint": _fingerprint(action, args),
        "args": args,
        "expires": time.time() + TOKEN_TTL_SECONDS,
    }
    _save(pending)
    response: dict[str, Any] = {
        "status": "confirmation_required",
        "preview": preview,
        "confirmation_token": token,
        "message": "NOTHING HAS BEEN CHANGED YET. Show this preview to the user and ask "
        "for explicit approval. Only if they approve, call this tool again with the same "
        "arguments plus this confirmation_token and user_reply = their reply, word for word.",
    }
    if why:
        response["status"] = "confirmation_invalid"
        response["message"] = (
            f"{why} Nothing was changed. Below is a fresh preview for the arguments you sent: "
            "show it to the user and ask again. Only if they approve, call this tool again "
            "with the same arguments plus the NEW confirmation_token."
        )
    return Gate(response)


# Normalized words. A refusal anywhere wins over a yes ("evet, ama iptal etme" = no).
_NO = re.compile(
    r"\b(hayir|yok|etme|yapma|vazgec|dur|bekle|no|nope|dont|don't|do not|not|"
    r"never|stop|wait|cancel that)\b"
)
_YES = re.compile(
    r"\b(evet|onay\w*|tamam|olur|peki|kabul|yap|yes|yep|yeah|ok|okay|confirm\w*|"
    r"approve\w*|sure|go ahead|do it|proceed)\b"
)


def approves(reply: str | None) -> bool:
    """Does the user's own reply approve the previewed action?"""
    text = " ".join(normalize(reply or "").split())  # "CONFIRM", "Hayır" -> "confirm", "hayir"
    return bool(_YES.search(text)) and not _NO.search(text)


def _not_approved(action: str, args: dict[str, Any], preview: str, reply: str | None) -> Gate:
    if not (reply or "").strip():
        why = (
            "user_reply is missing: pass the user's reply to the preview, word for word, "
            "together with the token."
        )
    else:
        why = (
            f"The user's reply ({reply.strip()[:80]!r}) does not approve this action. NOTHING "
            "WAS CHANGED. Do not call again unless the user clearly approves; tell them it was "
            "not done and ask what they want instead."
        )
    gate_ = _issue(action, args, preview, why)
    gate_.response["status"] = "not_approved"
    return gate_


def _supports_elicitation(ctx: Context) -> bool:
    caps = ctx.client_capabilities
    return bool(caps and caps.elicitation)


def gate(
    ctx: Context,
    action: str,
    args: dict[str, Any],
    preview: str,
    token: str | None,
    user_reply: str | None = None,
) -> Elicit[Approval] | Gate:
    if token:
        pending = _load()
        stored = pending.pop(token.strip(), None)
        _save(pending)  # a token works once, whatever the outcome
        if not (stored and stored["fingerprint"] == _fingerprint(action, args)):
            return _issue(action, args, preview, _why_rejected(stored, action, args))
        if not approves(user_reply):
            return _not_approved(action, args, preview, user_reply)
        return Gate()

    if _supports_elicitation(ctx):
        return Elicit(f"{preview}\n\nApprove?", Approval)

    return _issue(action, args, preview, None)


def blocked(outcome: ElicitationResult[Any]) -> dict[str, Any] | None:
    """None if the action may run, otherwise the response to return to the model."""
    if not isinstance(outcome, AcceptedElicitation):
        return DECLINED
    data = outcome.data
    if isinstance(data, Gate):
        return data.response
    return None if data.approve else DECLINED
