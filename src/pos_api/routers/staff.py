from fastapi import APIRouter
from sqlmodel import select

from pos_api.db.models import Staff
from pos_api.deps import SessionDep
from pos_api.schemas import StaffRead

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("", response_model=list[StaffRead])
def list_staff(session: SessionDep):
    return session.exec(select(Staff).order_by(Staff.id)).all()
