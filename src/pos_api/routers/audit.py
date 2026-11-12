from typing import Annotated

from fastapi import APIRouter, Query
from sqlmodel import select

from pos_api.db.models import AuditLog
from pos_api.deps import SessionDep
from pos_api.schemas import AuditLogRead
from pos_api.timeutil import to_local

router = APIRouter(prefix="/audit-log", tags=["audit"])


@router.get("", response_model=list[AuditLogRead])
def list_audit_log(
    session: SessionDep,
    actor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
):
    stmt = select(AuditLog)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    rows = session.exec(stmt.order_by(AuditLog.id.desc()).limit(limit)).all()
    return [
        AuditLogRead.model_validate(r).model_copy(update={"created_at": to_local(r.created_at)})
        for r in rows
    ]
