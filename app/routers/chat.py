from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db_dep
from app.models.enums import EstadoGuion, EstadoHistoriaSesion, OrigenMensajeHistoria
from app.models.guion import Guion
from app.models.historia import Historia
from app.models.historia_mensaje import HistoriaMensaje
from app.models.historia_sesion import HistoriaSesion
from app.models.interaccion import Interaccion
from app.models.opcion_respuesta import OpcionRespuesta
from app.models.paciente import Paciente
from app.models.personaje import Personaje
from app.services import historia_engine, motor
from app.services.assets import static_version

router = APIRouter(prefix="/chat")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["static_version"] = static_version


def _get_paciente_or_404(db: Session, paciente_id: int) -> Paciente:
    paciente = db.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return paciente


def _sesion_historia_activa(db: Session, personaje_id: int, paciente_id: int) -> HistoriaSesion | None:
    return db.scalar(
        select(HistoriaSesion)
        .join(Historia)
        .where(
            Historia.personaje_id == personaje_id,
            HistoriaSesion.paciente_id == paciente_id,
            HistoriaSesion.estado == EstadoHistoriaSesion.activa,
        )
        .order_by(HistoriaSesion.iniciada_en.desc())
    )


@router.get("/{paciente_id}/estado")
def estado(paciente_id: int, db: Session = Depends(get_db_dep)):
    """Para el polling de notificación de mensaje nuevo: combina el último id
    de Interaccion (guiones) y de HistoriaMensaje — cualquiera de los dos que
    suba le indica al navegador que llegó algo nuevo desde su último chequeo."""
    ultimo_interaccion = db.scalar(
        select(func.max(Interaccion.id)).where(Interaccion.paciente_id == paciente_id)
    )
    ultimo_historia = db.scalar(
        select(func.max(HistoriaMensaje.id))
        .join(HistoriaSesion)
        .where(HistoriaSesion.paciente_id == paciente_id)
    )
    combinado = (ultimo_interaccion or 0) + (ultimo_historia or 0)
    return JSONResponse({"ultima_interaccion_id": combinado})


@router.get("/{paciente_id}", response_class=HTMLResponse)
def lista_contactos(paciente_id: int, request: Request, db: Session = Depends(get_db_dep)):
    paciente = _get_paciente_or_404(db, paciente_id)
    personajes = db.scalars(
        select(Personaje).where(Personaje.familia_id == paciente.familia_id)
    ).all()

    contactos = []
    for p in personajes:
        ultima_interaccion = db.scalar(
            select(Interaccion)
            .join(Guion)
            .where(Guion.personaje_id == p.id, Interaccion.paciente_id == paciente.id)
            .order_by(Interaccion.timestamp_envio.desc())
            .limit(1)
        )
        ultimo_mensaje_historia = db.scalar(
            select(HistoriaMensaje)
            .join(HistoriaSesion)
            .join(Historia)
            .where(Historia.personaje_id == p.id, HistoriaSesion.paciente_id == paciente.id)
            .order_by(HistoriaMensaje.creado_en.desc())
            .limit(1)
        )

        candidatos = []
        if ultima_interaccion:
            ts = ultima_interaccion.timestamp_respuesta or ultima_interaccion.timestamp_envio
            texto = ultima_interaccion.texto_enviado or ultima_interaccion.guion.texto_mensaje
            esperando = ultima_interaccion.timestamp_respuesta is None
            candidatos.append((ts, texto, esperando))
        if ultimo_mensaje_historia:
            # Si la sesión ya se cerró, ese último mensaje es la despedida del
            # personaje — no espera respuesta, aunque el origen sea "personaje".
            sesion_activa = ultimo_mensaje_historia.sesion.estado == EstadoHistoriaSesion.activa
            esperando = sesion_activa and ultimo_mensaje_historia.origen == OrigenMensajeHistoria.personaje
            candidatos.append((ultimo_mensaje_historia.creado_en, ultimo_mensaje_historia.texto, esperando))

        ultimo = max(candidatos, key=lambda c: c[0]) if candidatos else None
        contactos.append(
            {
                "personaje": p,
                "ultimo_texto": ultimo[1] if ultimo else None,
                "ultimo_timestamp": ultimo[0] if ultimo else None,
                "esperando_respuesta": bool(ultimo and ultimo[2]),
            }
        )

    return templates.TemplateResponse(
        "chat/contactos.html", {"request": request, "paciente": paciente, "contactos": contactos}
    )


@router.get("/{paciente_id}/{personaje_id}", response_class=HTMLResponse)
def conversacion(
    paciente_id: int, personaje_id: int, request: Request, db: Session = Depends(get_db_dep)
):
    paciente = _get_paciente_or_404(db, paciente_id)
    personaje = db.get(Personaje, personaje_id)
    if personaje is None or personaje.familia_id != paciente.familia_id:
        raise HTTPException(status_code=404, detail="Personaje no encontrado")

    interacciones = db.scalars(
        select(Interaccion)
        .join(Guion)
        .where(Guion.personaje_id == personaje_id, Interaccion.paciente_id == paciente_id)
        .order_by(Interaccion.timestamp_envio)
    ).all()

    eventos = []
    for i in interacciones:
        eventos.append(
            {"lado": "in", "texto": i.texto_enviado or i.guion.texto_mensaje, "ts": i.timestamp_envio}
        )
        if i.respuesta_texto:
            eventos.append({"lado": "out", "texto": i.respuesta_texto, "ts": i.timestamp_respuesta})
        if i.cierre_generado:
            # Fallback sin destino armado: la IA generó un cierre en vez de
            # dejar la respuesta sin contestar (ver motor.registrar_respuesta_libre).
            eventos.append({"lado": "in", "texto": i.cierre_generado, "ts": i.timestamp_respuesta})

    sesiones_historia = db.scalars(
        select(HistoriaSesion)
        .join(Historia)
        .where(Historia.personaje_id == personaje_id, HistoriaSesion.paciente_id == paciente_id)
    ).all()
    for s in sesiones_historia:
        for m in s.mensajes:
            eventos.append(
                {
                    "lado": "in" if m.origen == OrigenMensajeHistoria.personaje else "out",
                    "texto": m.texto,
                    "ts": m.creado_en,
                }
            )
    eventos.sort(key=lambda e: e["ts"])

    esperando_tipo = None
    esperando_opciones = None
    sesion_activa = _sesion_historia_activa(db, personaje_id, paciente_id)
    if sesion_activa and sesion_activa.mensajes and sesion_activa.mensajes[-1].origen == OrigenMensajeHistoria.personaje:
        esperando_tipo = "historia"
    elif interacciones and interacciones[-1].timestamp_respuesta is None:
        ultimo_guion = interacciones[-1].guion
        esperando_tipo = ultimo_guion.tipo_respuesta.value
        esperando_opciones = ultimo_guion.opciones if esperando_tipo == "opciones" else None

    return templates.TemplateResponse(
        "chat/conversacion.html",
        {
            "request": request,
            "paciente": paciente,
            "personaje": personaje,
            "eventos": eventos,
            "esperando_tipo": esperando_tipo,
            "esperando_opciones": esperando_opciones,
        },
    )


@router.post("/{paciente_id}/{personaje_id}/responder")
def responder(
    paciente_id: int,
    personaje_id: int,
    texto: str = Form(""),
    opcion_id: str = Form(""),
    db: Session = Depends(get_db_dep),
):
    """Devuelve JSON (lo consume el chat vía fetch, ver chat.js) con el
    próximo mensaje del personaje — si lo hay — para que el cliente lo
    muestre con una demora creíble en vez de todo de golpe."""
    _get_paciente_or_404(db, paciente_id)

    sesion_activa = _sesion_historia_activa(db, personaje_id, paciente_id)
    if sesion_activa and sesion_activa.mensajes and sesion_activa.mensajes[-1].origen == OrigenMensajeHistoria.personaje:
        if not texto.strip():
            raise HTTPException(status_code=400, detail="Hace falta un texto.")
        historia_engine.registrar_respuesta(db, sesion_activa, texto.strip())
        db.flush()
        db.refresh(sesion_activa)
        ultimo = sesion_activa.mensajes[-1]
        sigue_activa = sesion_activa.estado == EstadoHistoriaSesion.activa
        return JSONResponse({
            "ok": True,
            "respuesta_texto": ultimo.texto,
            "siguiente_tipo": "libre" if sigue_activa else None,
            "siguiente_opciones": None,
        })

    interaccion = db.scalar(
        select(Interaccion)
        .join(Guion)
        .where(
            Guion.personaje_id == personaje_id,
            Interaccion.paciente_id == paciente_id,
            Interaccion.timestamp_respuesta.is_(None),
        )
        .order_by(Interaccion.timestamp_envio.desc())
        .limit(1)
    )
    if interaccion is None:
        raise HTTPException(status_code=400, detail="No hay nada esperando respuesta en este momento.")

    if opcion_id:
        opcion = db.get(OpcionRespuesta, int(opcion_id))
        siguiente = motor.registrar_respuesta_opciones(interaccion, opcion)
    elif texto.strip():
        siguiente = motor.registrar_respuesta_libre(interaccion, texto.strip())
    else:
        raise HTTPException(status_code=400, detail="Hace falta un texto o elegir una opción.")

    db.flush()
    # Un guion que no es de entrada siempre es automático: se manda ya, en
    # vez de esperar el próximo tick del scheduler.
    motor.procesar_guiones_vencidos(db, paciente_id)

    if siguiente is None:
        # Si cayó en un fallback sin destino armado, motor.py ya generó un
        # cierre con IA en vez de dejar al paciente sin ninguna respuesta.
        return JSONResponse({
            "ok": True,
            "respuesta_texto": interaccion.cierre_generado,
            "siguiente_tipo": None,
            "siguiente_opciones": None,
        })

    db.refresh(siguiente)
    if siguiente.estado != EstadoGuion.enviado:
        # Caso raro: el destino es un guion de entrada manual — no se manda
        # solo, queda esperando aprobación en la bandeja. Nada para mostrar
        # en el chat todavía.
        return JSONResponse({"ok": True, "respuesta_texto": None, "siguiente_tipo": None, "siguiente_opciones": None})

    nueva_interaccion = db.scalar(
        select(Interaccion)
        .where(Interaccion.guion_id == siguiente.id, Interaccion.paciente_id == paciente_id)
        .order_by(Interaccion.id.desc())
    )
    texto_enviado = nueva_interaccion.texto_enviado if nueva_interaccion else siguiente.texto_mensaje
    tipo = siguiente.tipo_respuesta.value
    opciones = None
    if tipo == "opciones":
        opciones = [{"id": o.id, "texto": o.texto_opcion} for o in siguiente.opciones]
    return JSONResponse({
        "ok": True,
        "respuesta_texto": texto_enviado,
        "siguiente_tipo": tipo,
        "siguiente_opciones": opciones,
    })
