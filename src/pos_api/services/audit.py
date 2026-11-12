import json

from sqlmodel import Session

from pos_api.db.models import AuditLog
from pos_api.timeutil import now


def record(session: Session, actor: str, action: str, payload: dict) -> None:
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            payload=json.dumps(payload, ensure_ascii=False, default=str),
            created_at=now(),
        )
    )
