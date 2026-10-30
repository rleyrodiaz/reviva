import logging
import secrets

from fastapi import Depends, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

logging.getLogger("passlib").setLevel(logging.ERROR)
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db_dep
from app.exceptions import AccessDenied, NeedsLogin
from app.models.enums import UserRole
from app.models.usuario import Usuario

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

COOKIE_NAME = "session"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd_context.verify(password, hashed)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key)


def _new_session_id() -> str:
    return secrets.token_hex(8)


def create_session_cookie(user_id: int, session_id: str) -> str:
    return _serializer().dumps({"uid": user_id, "sid": session_id})


def get_current_user(request: Request, db: Session = Depends(get_db_dep)) -> Usuario | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    max_age = get_settings().session_max_age_hours * 3600
    try:
        data = _serializer().loads(cookie, max_age=max_age)
    except SignatureExpired:
        request.state.session_expired = True
        return None
    except (BadSignature, KeyError, ValueError):
        return None
    request.state.session_id = data.get("sid")
    return db.get(Usuario, int(data["uid"]))


def require_user(user: Usuario | None = Depends(get_current_user)) -> Usuario:
    if user is None:
        raise NeedsLogin()
    return user


def require_superadmin(user: Usuario = Depends(require_user)) -> Usuario:
    if not user.es_superadmin:
        raise AccessDenied()
    return user


def require_familia_access(familia_id: int, user: Usuario) -> None:
    """Superadmin entra a cualquier familia; el resto solo a las que tiene
    membresía (un usuario puede tener membresía en más de una familia)."""
    if user.es_superadmin:
        return
    if not any(m.familia_id == familia_id for m in user.memberships):
        raise AccessDenied()


def require_admin_familia(familia_id: int, user: Usuario = Depends(require_user)) -> Usuario:
    require_familia_access(familia_id, user)
    if user.es_superadmin:
        return user
    membership = next((m for m in user.memberships if m.familia_id == familia_id), None)
    if membership is None or membership.rol != UserRole.admin_familia:
        raise AccessDenied()
    return user


def set_session(response, user_id: int) -> str:
    settings = get_settings()
    session_id = _new_session_id()
    response.set_cookie(
        COOKIE_NAME,
        create_session_cookie(user_id, session_id),
        max_age=settings.session_max_age_hours * 3600,
        httponly=True,
        samesite="lax",
    )
    return session_id


def clear_session(response) -> None:
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax")
