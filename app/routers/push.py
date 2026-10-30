from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db_dep
from app.models.push_subscription import PushSubscription

router = APIRouter(prefix="/push")


@router.get("/vapid-public-key")
def vapid_public_key():
    return JSONResponse({"public_key": get_settings().vapid_public_key})


@router.post("/{paciente_id}/suscribir")
async def suscribir(paciente_id: int, request: Request, db: Session = Depends(get_db_dep)):
    body = await request.json()
    endpoint = body.get("endpoint")
    keys = body.get("keys") or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    if not endpoint or not p256dh or not auth:
        return JSONResponse({"ok": False, "error": "Suscripción incompleta."}, status_code=400)

    existente = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if existente:
        existente.paciente_id = paciente_id
        existente.p256dh = p256dh
        existente.auth = auth
    else:
        db.add(PushSubscription(paciente_id=paciente_id, endpoint=endpoint, p256dh=p256dh, auth=auth))
    return JSONResponse({"ok": True})


@router.post("/{paciente_id}/desuscribir")
async def desuscribir(paciente_id: int, request: Request, db: Session = Depends(get_db_dep)):
    body = await request.json()
    endpoint = body.get("endpoint")
    if endpoint:
        existente = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
        if existente:
            db.delete(existente)
    return JSONResponse({"ok": True})
