from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db_dep
from app.models.enums import AccionActividad
from app.models.usuario import Usuario
from app.services.activity_log import registrar_actividad
from app.services.assets import static_version
from app.services.auth import clear_session, get_current_user, set_session, verify_password
from app.services.familias import list_familias_propias

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["static_version"] = static_version


def _home_url(user: Usuario, db: Session) -> str:
    # Con una sola familia propia vamos directo a ella, como siempre — el
    # listado de familias solo hace falta mostrarlo cuando hay que elegir
    # (superadmin, o un admin_familia con más de una familia).
    familias = list_familias_propias(user, db)
    if not user.es_superadmin and len(familias) == 1:
        return f"/admin/familias/{familias[0].id}"
    return "/admin/familias"


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    error: str = "",
    user: Usuario | None = Depends(get_current_user),
    db: Session = Depends(get_db_dep),
):
    if user is not None:
        return RedirectResponse(_home_url(user, db), status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@router.post("/login")
def login_submit(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db_dep),
):
    usuario = db.scalar(select(Usuario).where(Usuario.email == email.lower().strip()))
    if not usuario or not verify_password(password, usuario.password_hash):
        return RedirectResponse(
            f"/login?error={quote('Email o contraseña incorrectos.')}", status_code=303
        )
    response = RedirectResponse(_home_url(usuario, db), status_code=303)
    session_id = set_session(response, usuario.id)
    registrar_actividad(db, AccionActividad.usuario_login, usuario_id=usuario.id, session_id=session_id)
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    clear_session(response)
    return response
