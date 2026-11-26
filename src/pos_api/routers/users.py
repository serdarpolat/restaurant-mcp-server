from fastapi import APIRouter
from sqlmodel import select

from pos_api.db.models import User
from pos_api.deps import SessionDep
from pos_api.errors import NotFound
from pos_api.schemas import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(session: SessionDep, limit: int = 50):
    return session.exec(select(User).order_by(User.id.desc()).limit(limit)).all()


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, session: SessionDep):
    user = session.get(User, user_id)
    if not user:
        raise NotFound(f"User #{user_id} not found.")
    return user
