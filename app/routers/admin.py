import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session, joinedload

from app.db import Base, engine, get_db_dep
from app.models.activity_log import ActivityLog
from app.models.conversacion import Conversacion
from app.models.enums import (
    AccionActividad,
    EstadoGuion,
    EstadoHechoFamiliar,
    ModoEnvio,
    TamanoFuente,
    TemaVisual,
    UserRole,
)
from app.models.familia import Familia
from app.models.familia_membership import FamiliaMembership
from app.models.guion import Guion
from app.models.hecho_familiar import HechoFamiliar
from app.models.historia import Historia
from app.models.historia_sesion import HistoriaSesion
from app.models.interaccion import Interaccion
from app.models.paciente import Paciente
from app.models.personaje import Personaje
from app.models.push_subscription import PushSubscription
from app.models.rama_respuesta_libre import RamaRespuestaLibre
from app.models.usuario import Usuario
from app.services import historia_engine, motor
from app.services.activity_log import registrar_actividad
from app.services.assets import static_version
from app.services.auth import (
    MENSAJE_REQUIERE_ADMIN,
    clear_session,
    hash_password,
    require_admin_familia,
    require_familia_member,
    require_superadmin,
    require_user,
)
from app.services.familias import contadores_pendientes, es_admin_de, familias_navbar, list_familias_propias
from app.services.importador_historia import extraer_texto_archivo

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["static_version"] = static_version
templates.env.globals["es_admin_de"] = es_admin_de
templates.env.globals["familias_navbar"] = familias_navbar
templates.env.globals["contadores_pendientes"] = contadores_pendientes
templates.env.globals["mensaje_requiere_admin"] = MENSAJE_REQUIERE_ADMIN


def _paciente_de_familia(db: Session, familia_id: int) -> Paciente | None:
    # MVP: una familia tiene un único paciente.
    return db.scalar(select(Paciente).where(Paciente.familia_id == familia_id))


def _url_conversacion(familia_id: int, personaje_id: int, conversacion_id: int) -> str:
    return f"/admin/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}"


def _url_personaje(familia_id: int, personaje_id: int) -> str:
    return f"/admin/familias/{familia_id}/personajes/{personaje_id}"


def _resolver_contenido_historia(contenido: str, archivo: UploadFile | None) -> str:
    """Si se subió un archivo con contenido legible, ese texto manda (se
    puede seguir editando a mano después); si no, se usa lo tipeado."""
    if archivo is not None and archivo.filename:
        datos = archivo.file.read()
        if datos:
            texto = extraer_texto_archivo(archivo.filename, datos)
            if texto.strip():
                return texto.strip()
    return contenido.strip()


def _guiones_de_entrada(db: Session, guiones: list[Guion]) -> list[Guion]:
    """Un guion es "de entrada" si el admin lo marcó explícitamente como tal
    (campo es_entrada). No se infiere de la ausencia de referencias: un guion
    huérfano (que nadie lo apunta como destino) no es lo mismo que un guion
    de entrada real, y no queremos reactivar huérfanos en silencio."""
    return [g for g in guiones if g.es_entrada]


def _guiones_huerfanos(db: Session, guiones: list[Guion]) -> set[int]:
    """IDs de guiones que no son de entrada y a los que tampoco ninguna otra
    rama apunta como destino — es decir, no hay forma de que se disparen
    nunca. Es solo para mostrar una advertencia; nunca se usa para reactivar
    nada."""
    if not guiones:
        return set()
    ids = [g.id for g in guiones]
    destinos_ramas = db.scalars(
        select(RamaRespuestaLibre.guion_siguiente_id).where(
            RamaRespuestaLibre.guion_id.in_(ids), RamaRespuestaLibre.guion_siguiente_id.is_not(None)
        )
    ).all()
    referenciados = set(destinos_ramas)
    return {g.id for g in guiones if not g.es_entrada and g.id not in referenciados}


# Fecha "sin programar" para los guiones que no son de entrada: tanto el
# modo de envío como la fecha son propiedades del guion de entrada (de la
# conversación), no de cada nodo — el resto se activa recién cuando una
# opción/rama lo elige como destino (ahí _activar_guion_siguiente les pone
# la fecha real). Un valor lejano evita que el scheduler los dispare antes
# de ser alcanzados.
FECHA_SIN_PROGRAMAR = datetime(2099, 1, 1)


def _datos_diagrama(guiones: list[Guion], huerfanos: set[int]) -> str:
    """Nodos y aristas para el mapa visual de la conversación (editable: se
    puede mover, crear, tipear y conectar desde ahí) — un nodo por guion, una
    arista por opción/rama (a su destino, o "fin" si no tiene). Se manda como
    JSON ya armado porque Jinja2 acá no tiene el filtro `tojson` de Flask."""
    nodos = []
    aristas = []
    for g in guiones:
        ramas_no_fallback = [r for r in g.ramas_libres if not r.es_fallback]
        bifurcacion = len(ramas_no_fallback) >= 2
        nodos.append({
            "id": g.id,
            "texto": g.texto_mensaje,
            "estado": g.estado.value,
            "es_entrada": g.es_entrada,
            "huerfano": g.id in huerfanos,
            "bifurcacion": bifurcacion,
            "pos_x": g.pos_x,
            "pos_y": g.pos_y,
            "ancho": g.ancho,
            "alto": g.alto,
        })
        for r in g.ramas_libres:
            aristas.append({
                "id": r.id, "tipo": "rama",
                "origen": g.id, "destino": r.guion_siguiente_id,
                "etiqueta": "sin match" if r.es_fallback else r.criterio[:30],
                "criterio": r.criterio,
                "fallback": r.es_fallback,
            })
    crudo = json.dumps({"nodos": nodos, "aristas": aristas})
    return crudo.replace("</", "<\\/")


@router.get("/familias", response_class=HTMLResponse)
def listar_familias(
    request: Request, user: Usuario = Depends(require_user), db: Session = Depends(get_db_dep)
):
    familias = list_familias_propias(user, db)
    return templates.TemplateResponse(
        "admin/familias_list.html", {"request": request, "user": user, "familias": familias}
    )


@router.post("/familias")
def crear_familia(
    nombre_familia: str = Form(...),
    nombre_paciente: str = Form(...),
    admin_email: str = Form(...),
    admin_nombre: str = Form(""),
    admin_password: str = Form(""),
    user: Usuario = Depends(require_superadmin),
    db: Session = Depends(get_db_dep),
):
    """Alta de una familia nueva completa: la familia, su paciente, y un
    admin_familia para que alguien la pueda manejar — sin esto, la familia
    queda creada pero nadie puede entrar a administrarla. El admin puede ser
    alguien nuevo (nombre+contraseña) o alguien que ya administra otra
    familia (mismo email, se le agrega una membresía más)."""
    admin_email = admin_email.strip().lower()
    admin = db.scalar(select(Usuario).where(Usuario.email == admin_email))
    if admin is None:
        if not admin_nombre.strip() or not admin_password:
            raise HTTPException(
                status_code=400,
                detail="Para un administrador nuevo hacen falta su nombre y una contraseña.",
            )
        admin = Usuario(
            nombre=admin_nombre.strip(),
            email=admin_email,
            password_hash=hash_password(admin_password),
        )
        db.add(admin)
        db.flush()

    familia = Familia(nombre=nombre_familia.strip())
    db.add(familia)
    db.flush()

    db.add(Paciente(familia_id=familia.id, nombre=nombre_paciente.strip()))
    db.add(FamiliaMembership(usuario_id=admin.id, familia_id=familia.id, rol=UserRole.admin_familia))
    db.flush()
    return RedirectResponse(f"/admin/familias/{familia.id}", status_code=303)


@router.post("/familias/{familia_id}/borrar")
def borrar_familia(
    familia_id: int,
    user: Usuario = Depends(require_superadmin),
    db: Session = Depends(get_db_dep),
):
    """Borra la familia entera: personajes, conversaciones, guiones,
    paciente, hechos familiares e interacciones se van en cascada (todas
    las FK relevantes tienen ondelete=CASCADE). Irreversible — por eso es
    solo de superadmin, y el form que llama a esto pide confirmación."""
    familia = db.get(Familia, familia_id)
    if familia is None:
        raise HTTPException(status_code=404, detail="Familia no encontrada")
    nombre = familia.nombre
    # El registro de actividad va ANTES del delete: su FK a familia_id exige
    # que la fila todavía exista al insertar — después, el ondelete=SET NULL
    # la deja huérfana sola (se muestra como "—" en el Activity log).
    registrar_actividad(
        db, AccionActividad.familia_borrada, usuario_id=user.id, familia_id=familia_id,
        target_type="familia", target_id=familia_id, detalle=f"nombre={nombre}",
    )
    db.flush()
    # delete() de Core (no db.delete(familia) del ORM): deja que el
    # ondelete=CASCADE de cada FK haga todo el borrado en cascada en la
    # base directamente — el ORM, si maneja el borrado él mismo, por
    # default intenta poner en NULL la FK de los hijos antes de borrar al
    # padre, lo que rompe contra columnas NOT NULL como pacientes.familia_id.
    db.execute(delete(Familia).where(Familia.id == familia_id))
    return RedirectResponse("/admin/familias", status_code=303)


def _admins_restantes(db: Session, familia_id: int, excluir_membership_id: int | None = None) -> int:
    q = select(func.count()).select_from(FamiliaMembership).where(
        FamiliaMembership.familia_id == familia_id, FamiliaMembership.rol == UserRole.admin_familia
    )
    if excluir_membership_id is not None:
        q = q.where(FamiliaMembership.id != excluir_membership_id)
    return db.scalar(q)


@router.get("/familias/{familia_id}/usuarios", response_class=HTMLResponse)
def listar_usuarios_familia(
    familia_id: int,
    request: Request,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    familia = db.get(Familia, familia_id)
    memberships = db.scalars(
        select(FamiliaMembership)
        .join(Usuario)
        .where(FamiliaMembership.familia_id == familia_id)
        .order_by(Usuario.nombre)
    ).all()
    return templates.TemplateResponse(
        "admin/usuarios.html",
        {
            "request": request,
            "user": user,
            "familia": familia,
            "memberships": memberships,
            "roles": list(UserRole),
            # La fila del superadmin es informativa (no es una membership
            # real) y solo se muestra cuando quien mira es, de verdad, el
            # superadmin — nunca a un admin_familia viendo su propia familia.
            "mostrar_superadmin": user.es_superadmin,
        },
    )


@router.post("/familias/{familia_id}/usuarios")
def agregar_usuario_familia(
    familia_id: int,
    email: str = Form(...),
    nombre: str = Form(""),
    password: str = Form(""),
    rol: UserRole = Form(...),
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    """Agrega a alguien a la familia — lo puede hacer tanto superadmin como
    cualquier admin_familia de ESTA familia (no hace falta ser superadmin,
    a diferencia de crear una familia nueva)."""
    email = email.strip().lower()
    objetivo = db.scalar(select(Usuario).where(Usuario.email == email))
    if objetivo is None:
        if not nombre.strip() or not password:
            raise HTTPException(
                status_code=400,
                detail="Para una persona nueva hacen falta su nombre y una contraseña.",
            )
        objetivo = Usuario(nombre=nombre.strip(), email=email, password_hash=hash_password(password))
        db.add(objetivo)
        db.flush()

    existente = db.scalar(
        select(FamiliaMembership).where(
            FamiliaMembership.usuario_id == objetivo.id, FamiliaMembership.familia_id == familia_id
        )
    )
    if existente is not None:
        raise HTTPException(status_code=400, detail="Esa persona ya es parte de esta familia.")

    db.add(FamiliaMembership(usuario_id=objetivo.id, familia_id=familia_id, rol=rol))
    db.flush()
    registrar_actividad(
        db, AccionActividad.usuario_agregado_a_familia, usuario_id=user.id, familia_id=familia_id,
        target_type="usuario", target_id=objetivo.id, detalle=f"email={email} rol={rol.value}",
    )
    return RedirectResponse(f"/admin/familias/{familia_id}/usuarios", status_code=303)


@router.post("/familias/{familia_id}/usuarios/{membership_id}/rol")
def cambiar_rol_usuario_familia(
    familia_id: int,
    membership_id: int,
    rol: UserRole = Form(...),
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    membership = db.get(FamiliaMembership, membership_id)
    if membership is None or membership.familia_id != familia_id:
        raise HTTPException(status_code=404, detail="No encontrado")
    if membership.rol == UserRole.admin_familia and rol != UserRole.admin_familia:
        if _admins_restantes(db, familia_id, excluir_membership_id=membership_id) == 0:
            raise HTTPException(
                status_code=400,
                detail="No se puede dejar la familia sin ningún admin — asigná otro admin primero.",
            )
    membership.rol = rol
    registrar_actividad(
        db, AccionActividad.rol_cambiado, usuario_id=user.id, familia_id=familia_id,
        target_type="usuario", target_id=membership.usuario_id, detalle=f"nuevo_rol={rol.value}",
    )
    return RedirectResponse(f"/admin/familias/{familia_id}/usuarios", status_code=303)


@router.post("/familias/{familia_id}/usuarios/{membership_id}/borrar")
def quitar_usuario_familia(
    familia_id: int,
    membership_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    """Saca a la persona de ESTA familia (no borra su Usuario — puede seguir
    teniendo acceso a otras familias)."""
    membership = db.get(FamiliaMembership, membership_id)
    if membership is None or membership.familia_id != familia_id:
        raise HTTPException(status_code=404, detail="No encontrado")
    if membership.rol == UserRole.admin_familia:
        if _admins_restantes(db, familia_id, excluir_membership_id=membership_id) == 0:
            raise HTTPException(status_code=400, detail="No se puede dejar la familia sin ningún admin.")
    usuario_id = membership.usuario_id
    db.delete(membership)
    registrar_actividad(
        db, AccionActividad.usuario_quitado_de_familia, usuario_id=user.id, familia_id=familia_id,
        target_type="usuario", target_id=usuario_id,
    )
    return RedirectResponse(f"/admin/familias/{familia_id}/usuarios", status_code=303)


def _alerta_ia_sin_saldo(db: Session) -> ActivityLog | None:
    """Para el banner del dashboard: el aviso más reciente de "sin saldo de
    IA" (evento global, ver ia_cliente._registrar_saldo_agotado), si pasó
    en las últimas 24hs — pasado ese tiempo se asume que ya se resolvió (se
    recargaron créditos) y deja de mostrarse solo, sin necesidad de un
    estado "resuelto" aparte."""
    hace_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.scalar(
        select(ActivityLog)
        .where(ActivityLog.accion == AccionActividad.ia_sin_saldo, ActivityLog.creado_en >= hace_24h)
        .order_by(ActivityLog.creado_en.desc())
    )


@router.get("/familias/{familia_id}", response_class=HTMLResponse)
def dashboard_familia(
    familia_id: int,
    request: Request,
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    user.ultima_familia_id = familia_id
    familia = db.get(Familia, familia_id)
    personajes = db.scalars(
        select(Personaje).where(Personaje.familia_id == familia_id)
    ).all()
    paciente = _paciente_de_familia(db, familia_id)
    return templates.TemplateResponse(
        "admin/familia_dashboard.html",
        {
            "request": request,
            "user": user,
            "familia": familia,
            "personajes": personajes,
            "paciente": paciente,
            "alerta_ia_sin_saldo": _alerta_ia_sin_saldo(db) if es_admin_de(user, familia_id) else None,
            "temas": list(TemaVisual),
            "tamanos_fuente": list(TamanoFuente),
        },
    )


@router.post("/familias/{familia_id}/pacientes/{paciente_id}/configuracion")
def configurar_paciente(
    familia_id: int,
    paciente_id: int,
    tema: TemaVisual = Form(...),
    tamano_fuente: TamanoFuente = Form(...),
    push_habilitado: bool = Form(False),
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    paciente = db.get(Paciente, paciente_id)
    paciente.tema = tema
    paciente.tamano_fuente = tamano_fuente
    paciente.push_habilitado = push_habilitado
    return RedirectResponse(f"/admin/familias/{familia_id}", status_code=303)


@router.post("/familias/{familia_id}/personajes")
def crear_personaje(
    familia_id: int,
    nombre: str = Form(...),
    foto: str = Form(""),
    relacion_con_paciente: str = Form(""),
    tono_escritura: str = Form(""),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    personaje = Personaje(
        familia_id=familia_id,
        nombre=nombre.strip(),
        foto=foto.strip() or None,
        relacion_con_paciente=relacion_con_paciente.strip() or None,
        tono_escritura=tono_escritura.strip() or None,
    )
    db.add(personaje)
    return RedirectResponse(f"/admin/familias/{familia_id}", status_code=303)


@router.post("/familias/{familia_id}/personajes/{personaje_id}/borrar")
def borrar_personaje(
    familia_id: int,
    personaje_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    """Borra el personaje completo: sus conversaciones, guiones, opciones,
    ramas e interacciones del paciente con él. Cualquier guion de otro
    personaje que lo tuviera como destino queda sin destino en vez de romperse."""
    personaje = db.get(Personaje, personaje_id)
    db.delete(personaje)
    return RedirectResponse(f"/admin/familias/{familia_id}", status_code=303)


@router.post("/familias/{familia_id}/personajes/{personaje_id}/editar")
def editar_personaje(
    familia_id: int,
    personaje_id: int,
    nombre: str = Form(...),
    foto: str = Form(""),
    relacion_con_paciente: str = Form(""),
    tono_escritura: str = Form(""),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    personaje = db.get(Personaje, personaje_id)
    personaje.nombre = nombre.strip()
    personaje.foto = foto.strip() or None
    personaje.relacion_con_paciente = relacion_con_paciente.strip() or None
    personaje.tono_escritura = tono_escritura.strip() or None
    return RedirectResponse(_url_personaje(familia_id, personaje_id), status_code=303)


@router.post("/familias/{familia_id}/personajes/{personaje_id}/vaciar-chat")
def vaciar_chat_personaje(
    familia_id: int,
    personaje_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    """Borra lo que el paciente ya chateó con este personaje (lo que ve en su
    pantalla de chat) sin tocar los guiones ni las conversaciones armadas en
    el editor: no cambia estado ni fecha de ningún guion. Si después de vaciar
    el chat querés que vuelva a ver algo, usá "Reabrir" en la conversación
    correspondiente."""
    paciente = _paciente_de_familia(db, familia_id)
    interacciones = db.scalars(
        select(Interaccion)
        .join(Guion)
        .where(Guion.personaje_id == personaje_id, Interaccion.paciente_id == paciente.id)
    ).all()
    for interaccion in interacciones:
        db.delete(interaccion)

    # Las sesiones de Historia son la otra fuente de mensajes del chat — si no
    # se borran también, el chat no queda vacío de verdad.
    sesiones_historia = db.scalars(
        select(HistoriaSesion)
        .join(Historia)
        .where(Historia.personaje_id == personaje_id, HistoriaSesion.paciente_id == paciente.id)
    ).all()
    for sesion in sesiones_historia:
        db.delete(sesion)

    return RedirectResponse(f"/admin/familias/{familia_id}", status_code=303)


@router.get("/familias/{familia_id}/personajes/{personaje_id}", response_class=HTMLResponse)
def detalle_personaje(
    familia_id: int,
    personaje_id: int,
    request: Request,
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    personaje = db.get(Personaje, personaje_id)
    conversaciones = db.scalars(
        select(Conversacion)
        .where(Conversacion.personaje_id == personaje_id)
        .order_by(Conversacion.creada_en)
    ).all()
    return templates.TemplateResponse(
        "admin/personaje_detail.html",
        {
            "request": request,
            "user": user,
            "familia_id": familia_id,
            "personaje": personaje,
            "conversaciones": conversaciones,
        },
    )


@router.post("/familias/{familia_id}/personajes/{personaje_id}/conversaciones")
def crear_conversacion(
    familia_id: int,
    personaje_id: int,
    nombre: str = Form(...),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    conversacion = Conversacion(personaje_id=personaje_id, nombre=nombre.strip())
    db.add(conversacion)
    db.flush()
    # Se crea solo con el nombre: todo lo demás (guiones, fecha, modo) se
    # arma directamente en el mapa de la conversación.
    return RedirectResponse(
        _url_conversacion(familia_id, personaje_id, conversacion.id), status_code=303
    )


@router.post("/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/editar")
def editar_conversacion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    nombre: str = Form(...),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    conversacion = db.get(Conversacion, conversacion_id)
    conversacion.nombre = nombre.strip()
    return RedirectResponse(_url_personaje(familia_id, personaje_id), status_code=303)


@router.post("/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/reabrir")
def reabrir_conversacion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    fecha_programada: str = Form(...),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    # "Reabrir la conversación" = reactivar sus guiones de entrada (los que
    # ninguna opción/rama tiene como destino) con una fecha nueva, sin tener
    # que ir guion por guion.
    conversacion = db.get(Conversacion, conversacion_id)
    nueva_fecha = datetime.fromisoformat(fecha_programada)
    for guion in _guiones_de_entrada(db, conversacion.guiones):
        guion.estado = EstadoGuion.borrador
        guion.fecha_programada = nueva_fecha
    return RedirectResponse(_url_personaje(familia_id, personaje_id), status_code=303)


@router.post("/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/borrar")
def borrar_conversacion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    conversacion = db.get(Conversacion, conversacion_id)
    db.delete(conversacion)
    return RedirectResponse(_url_personaje(familia_id, personaje_id), status_code=303)


@router.get("/familias/{familia_id}/personajes/{personaje_id}/historias", response_class=HTMLResponse)
def listar_historias(
    familia_id: int,
    personaje_id: int,
    request: Request,
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    personaje = db.get(Personaje, personaje_id)
    historias = db.scalars(
        select(Historia).where(Historia.personaje_id == personaje_id).order_by(Historia.creada_en)
    ).all()
    return templates.TemplateResponse(
        "admin/historias_list.html",
        {
            "request": request,
            "user": user,
            "familia_id": familia_id,
            "personaje": personaje,
            "historias": historias,
        },
    )


@router.post("/familias/{familia_id}/personajes/{personaje_id}/historias")
def crear_historia(
    familia_id: int,
    personaje_id: int,
    titulo: str = Form(...),
    epoca: str = Form(""),
    lugar: str = Form(""),
    participantes: str = Form(""),
    contenido: str = Form(""),
    duracion_maxima_minutos: int = Form(10),
    archivo: UploadFile | None = File(None),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    texto_final = _resolver_contenido_historia(contenido, archivo)
    if not texto_final:
        # Ni texto tipeado ni archivo con contenido legible: no hay nada que guardar.
        return RedirectResponse(
            f"/admin/familias/{familia_id}/personajes/{personaje_id}/historias", status_code=303
        )
    historia = Historia(
        personaje_id=personaje_id,
        titulo=titulo.strip(),
        epoca=epoca.strip() or None,
        lugar=lugar.strip() or None,
        participantes=participantes.strip() or None,
        contenido=texto_final,
        duracion_maxima_minutos=duracion_maxima_minutos,
    )
    db.add(historia)
    return RedirectResponse(
        f"/admin/familias/{familia_id}/personajes/{personaje_id}/historias", status_code=303
    )


@router.get(
    "/familias/{familia_id}/personajes/{personaje_id}/historias/{historia_id}",
    response_class=HTMLResponse,
)
def detalle_historia(
    familia_id: int,
    personaje_id: int,
    historia_id: int,
    request: Request,
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    personaje = db.get(Personaje, personaje_id)
    historia = db.get(Historia, historia_id)
    sesiones = db.scalars(
        select(HistoriaSesion)
        .where(HistoriaSesion.historia_id == historia_id)
        .order_by(HistoriaSesion.iniciada_en.desc())
    ).all()
    fecha_programada_valor = ""
    if historia.fecha_programada is not None:
        fecha_programada_valor = historia.fecha_programada.strftime("%Y-%m-%dT%H:%M")
    return templates.TemplateResponse(
        "admin/historia_detail.html",
        {
            "request": request,
            "user": user,
            "familia_id": familia_id,
            "personaje": personaje,
            "historia": historia,
            "sesiones": sesiones,
            "modos_envio": list(ModoEnvio),
            "fecha_programada_valor": fecha_programada_valor,
        },
    )


@router.post("/familias/{familia_id}/personajes/{personaje_id}/historias/{historia_id}/editar")
def editar_historia(
    familia_id: int,
    personaje_id: int,
    historia_id: int,
    titulo: str = Form(...),
    epoca: str = Form(""),
    lugar: str = Form(""),
    participantes: str = Form(""),
    contenido: str = Form(""),
    duracion_maxima_minutos: int = Form(10),
    archivo: UploadFile | None = File(None),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    historia = db.get(Historia, historia_id)
    texto_final = _resolver_contenido_historia(contenido, archivo)
    historia.titulo = titulo.strip()
    historia.epoca = epoca.strip() or None
    historia.lugar = lugar.strip() or None
    historia.participantes = participantes.strip() or None
    if texto_final:
        historia.contenido = texto_final
    historia.duracion_maxima_minutos = duracion_maxima_minutos
    return RedirectResponse(
        f"/admin/familias/{familia_id}/personajes/{personaje_id}/historias/{historia_id}", status_code=303
    )


@router.post("/familias/{familia_id}/personajes/{personaje_id}/historias/{historia_id}/configuracion")
def configurar_historia(
    familia_id: int,
    personaje_id: int,
    historia_id: int,
    modo_envio: ModoEnvio = Form(...),
    fecha_programada: str = Form(""),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    """Igual que configurar_conversacion pero para una Historia: en manual
    (el modo de siempre) la fecha no participa de nada, solo se puede
    proponer a mano. En automático, el scheduler la propone solo apenas
    se cumple la fecha."""
    historia = db.get(Historia, historia_id)
    historia.modo_envio = modo_envio
    historia.fecha_programada = datetime.fromisoformat(fecha_programada) if fecha_programada else None
    return RedirectResponse(
        f"/admin/familias/{familia_id}/personajes/{personaje_id}/historias/{historia_id}", status_code=303
    )


@router.post("/familias/{familia_id}/personajes/{personaje_id}/historias/{historia_id}/borrar")
def borrar_historia(
    familia_id: int,
    personaje_id: int,
    historia_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    historia = db.get(Historia, historia_id)
    db.delete(historia)
    return RedirectResponse(
        f"/admin/familias/{familia_id}/personajes/{personaje_id}/historias", status_code=303
    )


@router.post("/familias/{familia_id}/personajes/{personaje_id}/historias/{historia_id}/proponer")
def proponer_historia(
    familia_id: int,
    personaje_id: int,
    historia_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    """En manual, igual que un guion de entrada manual: genera el primer
    mensaje y lo deja esperando aprobación en la Bandeja, no le llega nada
    al paciente todavía. En automático (disparo manual anticipado, antes de
    la fecha) arranca directo, sin pasar por la bandeja — como el
    scheduler mismo haría."""
    historia = db.get(Historia, historia_id)
    if historia.modo_envio == ModoEnvio.manual:
        historia_engine.proponer(db, historia)
    else:
        paciente = _paciente_de_familia(db, familia_id)
        historia_engine.iniciar_sesion(db, historia, paciente.id)
    return RedirectResponse(
        f"/admin/familias/{familia_id}/personajes/{personaje_id}/historias/{historia_id}", status_code=303
    )


@router.post("/familias/{familia_id}/personajes/{personaje_id}/historias/{historia_id}/bandeja/aprobar")
def aprobar_historia_desde_bandeja(
    familia_id: int,
    personaje_id: int,
    historia_id: int,
    mensaje: str = Form(...),
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    historia = db.get(Historia, historia_id)
    if historia.mensaje_propuesto is not None:
        paciente = _paciente_de_familia(db, familia_id)
        historia_engine.aprobar_propuesta(db, historia, paciente.id, mensaje.strip())
        registrar_actividad(
            db, AccionActividad.historia_aprobada, usuario_id=user.id, familia_id=familia_id,
            target_type="historia", target_id=historia_id,
        )
    return RedirectResponse(f"/admin/familias/{familia_id}/bandeja", status_code=303)


@router.post("/familias/{familia_id}/personajes/{personaje_id}/historias/{historia_id}/bandeja/desactivar")
def desactivar_historia_desde_bandeja(
    familia_id: int,
    personaje_id: int,
    historia_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    historia = db.get(Historia, historia_id)
    if historia.mensaje_propuesto is not None:
        historia_engine.desactivar_propuesta(historia)
        registrar_actividad(
            db, AccionActividad.historia_desactivada, usuario_id=user.id, familia_id=familia_id,
            target_type="historia", target_id=historia_id,
        )
    return RedirectResponse(f"/admin/familias/{familia_id}/bandeja", status_code=303)


@router.get(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}",
    response_class=HTMLResponse,
)
def detalle_conversacion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    request: Request,
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    personaje = db.get(Personaje, personaje_id)
    conversacion = db.get(Conversacion, conversacion_id)
    guiones = db.scalars(
        select(Guion)
        .where(Guion.conversacion_id == conversacion_id)
        .order_by(Guion.fecha_programada)
    ).all()
    otros_guiones = db.scalars(
        select(Guion)
        .join(Personaje)
        .where(Personaje.familia_id == familia_id, Guion.conversacion_id != conversacion_id)
        .order_by(Personaje.nombre, Guion.fecha_programada)
    ).all()
    huerfanos = _guiones_huerfanos(db, guiones)
    guion_entrada = next((g for g in guiones if g.es_entrada), None)
    fecha_entrada_valor = ""
    if guion_entrada is not None and guion_entrada.fecha_programada != FECHA_SIN_PROGRAMAR:
        fecha_entrada_valor = guion_entrada.fecha_programada.strftime("%Y-%m-%dT%H:%M")
    return templates.TemplateResponse(
        "admin/conversacion_detail.html",
        {
            "request": request,
            "user": user,
            "familia_id": familia_id,
            "personaje": personaje,
            "conversacion": conversacion,
            "guiones": guiones,
            "otros_guiones": otros_guiones,
            "huerfanos": huerfanos,
            "guion_entrada": guion_entrada,
            "fecha_entrada_valor": fecha_entrada_valor,
            "diagrama_json": _datos_diagrama(guiones, huerfanos),
            "modos_envio": list(ModoEnvio),
        },
    )


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/configuracion"
)
def configurar_conversacion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    fecha_programada: str = Form(...),
    modo_envio: ModoEnvio = Form(...),
    reabrir: str = Form(""),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    """Panel de arriba del mapa: fecha y modo de envío son del guion de
    entrada, no de cada nodo. El modo de envío decide si la conversación
    arranca con una aprobación o sola; una vez arrancada, el resto de la
    cadena fluye sin pedir aprobación de nuevo en cada paso.

    En automático, la fecha manda: "Guardar" solo la actualiza para que el
    scheduler la respete más adelante; "Reabrir" además lo vuelve a
    borrador ya mismo. En manual la fecha no participa de nada — ni falta
    que hace "reabrir" distinto de "guardar": en cuanto se guarda con modo
    manual, el guion de entrada pasa derecho a la bandeja de aprobación,
    listo para que lo apruebes o lo desactives."""
    guiones = db.scalars(select(Guion).where(Guion.conversacion_id == conversacion_id)).all()
    guion_entrada = next((g for g in guiones if g.es_entrada), None)
    if guion_entrada is None:
        raise HTTPException(status_code=400, detail="Todavía no hay un nodo de entrada: creá el primero en el mapa.")
    guion_entrada.fecha_programada = datetime.fromisoformat(fecha_programada)
    guion_entrada.modo_envio = modo_envio
    if modo_envio == ModoEnvio.manual:
        guion_entrada.estado = EstadoGuion.pendiente_aprobacion
    elif reabrir:
        guion_entrada.estado = EstadoGuion.borrador
    registrar_actividad(
        db, AccionActividad.conversacion_configurada, usuario_id=user.id, familia_id=familia_id,
        target_type="conversacion", target_id=conversacion_id,
        detalle=f"modo={modo_envio.value} fecha={fecha_programada} reabrir={bool(reabrir)}",
    )
    return RedirectResponse(_url_conversacion(familia_id, personaje_id, conversacion_id), status_code=303)


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones/{guion_id}/posicion"
)
def guardar_posicion_guion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_id: int,
    pos_x: int = Form(...),
    pos_y: int = Form(...),
    ancho: str = Form(""),
    alto: str = Form(""),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    guion = db.get(Guion, guion_id)
    guion.pos_x = pos_x
    guion.pos_y = pos_y
    if ancho:
        guion.ancho = int(ancho)
    if alto:
        guion.alto = int(alto)
    return JSONResponse({"ok": True})


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones/{guion_id}/texto-rapido"
)
def editar_texto_rapido_guion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_id: int,
    texto: str = Form(...),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    """Edición de texto in-line desde el mapa visual — igual que el campo
    "Mensaje" de la tarjeta de abajo, solo que sin recargar la página."""
    guion = db.get(Guion, guion_id)
    texto_limpio = texto.strip()
    if not texto_limpio:
        raise HTTPException(status_code=400, detail="El mensaje no puede quedar vacío.")
    guion.texto_mensaje = texto_limpio
    return JSONResponse({"ok": True, "texto": texto_limpio})


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones/{guion_id}/conectar"
)
def conectar_guion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_id: int,
    destino_id: str = Form(""),
    etiqueta: str = Form(""),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    """Arrastrar de un guion a otro en el mapa crea la rama libre que los
    conecta. Sin destino (se soltó en un espacio vacío, con confirmación del
    lado del cliente) el camino termina en "fin". Dejar la etiqueta vacía no
    crea una rama nueva: reapunta el fallback existente (el camino "sin
    match", con o sin destino) — todo guion tiene uno solo."""
    origen = db.get(Guion, guion_id)
    destino = None
    if destino_id:
        destino = db.get(Guion, int(destino_id))
        if destino is None or destino.conversacion_id != conversacion_id:
            raise HTTPException(status_code=400, detail="El destino tiene que ser un guion de esta misma conversación.")
    destino_final_id = destino.id if destino else None
    etiqueta_limpia = etiqueta.strip()

    if not etiqueta_limpia:
        fallback = next((r for r in origen.ramas_libres if r.es_fallback), None)
        fallback.guion_siguiente_id = destino_final_id
        return JSONResponse({
            "ok": True,
            "arista": {
                "id": fallback.id, "tipo": "rama",
                "origen": origen.id, "destino": destino_final_id, "etiqueta": "sin match",
                "criterio": None, "fallback": True,
            },
        })

    nueva = RamaRespuestaLibre(guion_id=origen.id, criterio=etiqueta_limpia, guion_siguiente_id=destino_final_id)
    db.add(nueva)
    db.flush()
    return JSONResponse({
        "ok": True,
        "arista": {
            "id": nueva.id, "tipo": "rama",
            "origen": origen.id, "destino": destino_final_id, "etiqueta": etiqueta_limpia[:30],
            "criterio": etiqueta_limpia, "fallback": False,
        },
    })


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones"
)
def crear_guion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    texto_mensaje: str = Form(...),
    pos_x: str = Form(""),
    pos_y: str = Form(""),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    """El guion se crea entero desde el mapa: solo pide el mensaje. La IA
    clasifica lo que conteste el paciente contra las ramas que se conecten
    desde el menú del mapa. La fecha y el modo de envío son del guion de
    entrada, se configuran en el panel de arriba. El primer guion que se
    crea en una conversación (o el primero después de borrar el anterior)
    se vuelve su guion de entrada automáticamente, sin elegirlo a mano. El
    resto de los guiones no necesita modo propio: una vez que la
    conversación arrancó, fluyen solos sin pasar por la bandeja."""
    guiones_actuales = db.scalars(
        select(Guion).where(Guion.conversacion_id == conversacion_id)
    ).all()
    es_entrada = not any(g.es_entrada for g in guiones_actuales)

    guion = Guion(
        personaje_id=personaje_id,
        conversacion_id=conversacion_id,
        fecha_programada=FECHA_SIN_PROGRAMAR,
        texto_mensaje=texto_mensaje.strip(),
        modo_envio=ModoEnvio.manual if es_entrada else ModoEnvio.automatico,
        estado=EstadoGuion.borrador,
        es_entrada=es_entrada,
        pos_x=int(pos_x) if pos_x else None,
        pos_y=int(pos_y) if pos_y else None,
    )
    db.add(guion)
    db.flush()
    # Toda rama libre necesita su fallback desde el arranque, para que la
    # conversación nunca quede sin salida si la IA no puede clasificar.
    db.add(RamaRespuestaLibre(guion_id=guion.id, es_fallback=True))
    registrar_actividad(
        db, AccionActividad.guion_creado, usuario_id=user.id, familia_id=familia_id,
        target_type="guion", target_id=guion.id,
    )
    return RedirectResponse(_url_conversacion(familia_id, personaje_id, conversacion_id), status_code=303)


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones/importar"
)
def importar_guion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_origen_id: int = Form(...),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    """Trae una copia de un guion de otra conversación (o de otro personaje)
    a esta conversación. Las ramas se copian pero sin destino, porque los
    guiones a los que apuntaban no son parte de esta conversación."""
    original = db.get(Guion, guion_origen_id)
    copia = Guion(
        personaje_id=personaje_id,
        conversacion_id=conversacion_id,
        fecha_programada=original.fecha_programada + timedelta(days=1),
        texto_mensaje=original.texto_mensaje,
        modo_envio=original.modo_envio,
        estado=EstadoGuion.borrador,
    )
    db.add(copia)
    db.flush()
    for r in original.ramas_libres:
        db.add(RamaRespuestaLibre(guion_id=copia.id, criterio=r.criterio, es_fallback=r.es_fallback))
    return RedirectResponse(_url_conversacion(familia_id, personaje_id, conversacion_id), status_code=303)


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones/{guion_id}/editar"
)
def editar_guion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_id: int,
    texto_mensaje: str = Form(...),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    # El tipo de respuesta no se edita acá: cambiarlo dejaría huérfanas las
    # opciones/ramas ya cargadas. Si hace falta, se borra y se crea de nuevo.
    # La fecha y si es de entrada son del panel de la conversación / se fijan
    # solos al crear el guion: acá solo se toca el texto.
    guion = db.get(Guion, guion_id)
    guion.texto_mensaje = texto_mensaje.strip()
    return RedirectResponse(_url_conversacion(familia_id, personaje_id, conversacion_id), status_code=303)


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones/{guion_id}/duplicar"
)
def duplicar_guion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_id: int,
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    original = db.get(Guion, guion_id)
    copia = Guion(
        personaje_id=original.personaje_id,
        conversacion_id=original.conversacion_id,
        fecha_programada=original.fecha_programada + timedelta(days=1),
        texto_mensaje=original.texto_mensaje,
        modo_envio=original.modo_envio,
        estado=EstadoGuion.borrador,
        nodo_padre_id=original.nodo_padre_id,
    )
    db.add(copia)
    db.flush()
    for r in original.ramas_libres:
        db.add(RamaRespuestaLibre(
            guion_id=copia.id, criterio=r.criterio, es_fallback=r.es_fallback,
            guion_siguiente_id=r.guion_siguiente_id,
        ))
    return RedirectResponse(_url_conversacion(familia_id, personaje_id, conversacion_id), status_code=303)


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones/{guion_id}/reabrir"
)
def reabrir_guion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_id: int,
    fecha_programada: str = Form(...),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    guion = db.get(Guion, guion_id)
    if guion.estado != EstadoGuion.borrador:
        guion.estado = EstadoGuion.borrador
        guion.fecha_programada = datetime.fromisoformat(fecha_programada)
    return RedirectResponse(_url_conversacion(familia_id, personaje_id, conversacion_id), status_code=303)


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones/{guion_id}/borrar"
)
def borrar_guion(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    guion = db.get(Guion, guion_id)
    db.delete(guion)
    registrar_actividad(
        db, AccionActividad.guion_borrado, usuario_id=user.id, familia_id=familia_id,
        target_type="guion", target_id=guion_id,
    )
    return RedirectResponse(_url_conversacion(familia_id, personaje_id, conversacion_id), status_code=303)


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones/{guion_id}/ramas"
)
def agregar_rama(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_id: int,
    criterio: str = Form(...),
    guion_siguiente_id: str = Form(""),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    db.add(
        RamaRespuestaLibre(
            guion_id=guion_id,
            criterio=criterio.strip(),
            guion_siguiente_id=int(guion_siguiente_id) if guion_siguiente_id else None,
        )
    )
    return RedirectResponse(_url_conversacion(familia_id, personaje_id, conversacion_id), status_code=303)


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}"
    "/guiones/{guion_id}/ramas/{rama_id}/editar"
)
def editar_rama(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_id: int,
    rama_id: int,
    criterio: str = Form(...),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    """Cambia el criterio de una rama ya creada — desde el mapa, al hacer
    click en la conexión. El fallback no tiene criterio propio (es "lo que no
    matcheó con ninguna otra"), así que no se puede editar."""
    rama = db.get(RamaRespuestaLibre, rama_id)
    if rama is None or rama.es_fallback:
        raise HTTPException(status_code=400, detail="Esta rama no se puede editar.")
    criterio_limpio = criterio.strip()
    if not criterio_limpio:
        raise HTTPException(status_code=400, detail="El criterio no puede quedar vacío.")
    rama.criterio = criterio_limpio
    return JSONResponse({
        "ok": True,
        "arista": {
            "id": rama.id, "tipo": "rama",
            "origen": rama.guion_id, "destino": rama.guion_siguiente_id, "etiqueta": criterio_limpio[:30],
            "criterio": criterio_limpio, "fallback": False,
        },
    })


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}"
    "/guiones/{guion_id}/ramas/{rama_id}/borrar"
)
def borrar_rama(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_id: int,
    rama_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    rama = db.get(RamaRespuestaLibre, rama_id)
    if rama is not None and not rama.es_fallback:
        # El fallback no se borra: todo guion de tipo libre necesita uno para
        # no trabar la conversación si la IA no puede clasificar la respuesta.
        db.delete(rama)
    return RedirectResponse(_url_conversacion(familia_id, personaje_id, conversacion_id), status_code=303)


@router.post(
    "/familias/{familia_id}/personajes/{personaje_id}/conversaciones/{conversacion_id}/guiones/{guion_id}/fallback"
)
def editar_fallback(
    familia_id: int,
    personaje_id: int,
    conversacion_id: int,
    guion_id: int,
    guion_siguiente_id: str = Form(""),
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    guion = db.get(Guion, guion_id)
    fallback = next((r for r in guion.ramas_libres if r.es_fallback), None)
    if fallback is not None:
        fallback.guion_siguiente_id = int(guion_siguiente_id) if guion_siguiente_id else None
    return RedirectResponse(_url_conversacion(familia_id, personaje_id, conversacion_id), status_code=303)


@router.get("/familias/{familia_id}/bandeja", response_class=HTMLResponse)
def bandeja_aprobacion(
    familia_id: int,
    request: Request,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    pendientes = db.scalars(
        select(Guion)
        .join(Personaje)
        .where(Personaje.familia_id == familia_id, Guion.estado == EstadoGuion.pendiente_aprobacion)
        .order_by(Guion.fecha_programada)
    ).all()
    pendientes_historias = db.scalars(
        select(Historia)
        .join(Personaje)
        .where(Personaje.familia_id == familia_id, Historia.mensaje_propuesto.is_not(None))
        .order_by(Historia.propuesta_en)
    ).all()
    return templates.TemplateResponse(
        "admin/bandeja.html",
        {
            "request": request, "user": user, "familia_id": familia_id,
            "pendientes": pendientes, "pendientes_historias": pendientes_historias,
        },
    )


@router.post("/familias/{familia_id}/bandeja/{guion_id}/aprobar")
def aprobar_desde_bandeja(
    familia_id: int,
    guion_id: int,
    texto_mensaje: str = Form(...),
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    guion = db.get(Guion, guion_id)
    if guion.estado == EstadoGuion.pendiente_aprobacion:
        # Si ya no está pendiente (doble click, otra pestaña, el scheduler
        # llegó primero) no hay nada que aprobar — evitamos el 500 y
        # simplemente volvemos a la bandeja actualizada.
        guion.texto_mensaje = texto_mensaje.strip()
        paciente = _paciente_de_familia(db, familia_id)
        motor.aprobar_guion(db, guion, paciente.id)
        registrar_actividad(
            db, AccionActividad.guion_aprobado, usuario_id=user.id, familia_id=familia_id,
            target_type="guion", target_id=guion_id,
        )
    return RedirectResponse(f"/admin/familias/{familia_id}/bandeja", status_code=303)


@router.post("/familias/{familia_id}/bandeja/{guion_id}/desactivar")
def desactivar_desde_bandeja(
    familia_id: int,
    guion_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    """Sacar este envío de la bandeja sin aprobarlo. La fecha no participa
    en nada para un guion manual, así que no hace falta reprogramar: queda
    en borrador hasta que alguien lo reabra a mano (editándolo o, si es el
    guion de entrada, desde el panel de la conversación) o lo alcance una
    opción/rama."""
    guion = db.get(Guion, guion_id)
    if guion.estado == EstadoGuion.pendiente_aprobacion:
        guion.estado = EstadoGuion.borrador
        registrar_actividad(
            db, AccionActividad.guion_desactivado, usuario_id=user.id, familia_id=familia_id,
            target_type="guion", target_id=guion_id,
        )
    return RedirectResponse(f"/admin/familias/{familia_id}/bandeja", status_code=303)


@router.get("/familias/{familia_id}/hechos", response_class=HTMLResponse)
def listar_hechos(
    familia_id: int,
    request: Request,
    tab: str = "pendientes",
    user: Usuario = Depends(require_familia_member),
    db: Session = Depends(get_db_dep),
):
    tab_activa = tab if tab in ("pendientes", "validados", "descartados") else "pendientes"
    pendientes = db.scalars(
        select(HechoFamiliar)
        .where(HechoFamiliar.familia_id == familia_id, HechoFamiliar.estado == EstadoHechoFamiliar.pendiente)
        .order_by(HechoFamiliar.creado_en)
    ).all()
    validados = db.scalars(
        select(HechoFamiliar)
        .where(HechoFamiliar.familia_id == familia_id, HechoFamiliar.estado == EstadoHechoFamiliar.validado)
        .order_by(HechoFamiliar.creado_en.desc())
    ).all()
    descartados = db.scalars(
        select(HechoFamiliar)
        .where(HechoFamiliar.familia_id == familia_id, HechoFamiliar.estado == EstadoHechoFamiliar.descartado)
        .order_by(HechoFamiliar.creado_en.desc())
    ).all()
    return templates.TemplateResponse(
        "admin/hechos_list.html",
        {
            "request": request,
            "user": user,
            "familia_id": familia_id,
            "tab_activa": tab_activa,
            "pendientes": pendientes,
            "validados": validados,
            "descartados": descartados,
        },
    )


@router.post("/familias/{familia_id}/hechos")
def crear_hecho_manual(
    familia_id: int,
    texto: str = Form(...),
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    """Un hecho que el admin ya sabe que es cierto (no salió de lo que dijo
    el paciente en una sesión) — por eso entra directo a validado, sin el
    paso de revisión que sí necesita lo rescatado de la IA."""
    texto_limpio = texto.strip()
    if not texto_limpio:
        raise HTTPException(400, "El texto no puede estar vacío.")
    hecho = HechoFamiliar(
        familia_id=familia_id,
        texto=texto_limpio,
        estado=EstadoHechoFamiliar.validado,
        creado_por_id=user.id,
    )
    db.add(hecho)
    return RedirectResponse(f"/admin/familias/{familia_id}/hechos?tab=validados", status_code=303)


@router.post("/familias/{familia_id}/hechos/{hecho_id}/editar")
def editar_hecho(
    familia_id: int,
    hecho_id: int,
    texto: str = Form(...),
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    texto_limpio = texto.strip()
    if not texto_limpio:
        raise HTTPException(400, "El texto no puede estar vacío.")
    hecho = db.get(HechoFamiliar, hecho_id)
    if hecho is not None:
        hecho.texto = texto_limpio
    return RedirectResponse(f"/admin/familias/{familia_id}/hechos?tab=validados", status_code=303)


@router.post("/familias/{familia_id}/hechos/{hecho_id}/borrar")
def borrar_hecho(
    familia_id: int,
    hecho_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    """Borra un hecho validado para siempre — a diferencia de "descartar",
    que lo saca de circulación pero lo deja a la vista por si se reconsidera."""
    hecho = db.get(HechoFamiliar, hecho_id)
    if hecho is not None:
        db.delete(hecho)
    return RedirectResponse(f"/admin/familias/{familia_id}/hechos?tab=validados", status_code=303)


@router.post("/familias/{familia_id}/hechos/{hecho_id}/validar")
def validar_hecho(
    familia_id: int,
    hecho_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    hecho = db.get(HechoFamiliar, hecho_id)
    hecho.estado = EstadoHechoFamiliar.validado
    return RedirectResponse(f"/admin/familias/{familia_id}/hechos", status_code=303)


@router.post("/familias/{familia_id}/hechos/{hecho_id}/descartar")
def descartar_hecho(
    familia_id: int,
    hecho_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    hecho = db.get(HechoFamiliar, hecho_id)
    hecho.estado = EstadoHechoFamiliar.descartado
    return RedirectResponse(f"/admin/familias/{familia_id}/hechos", status_code=303)


@router.post("/familias/{familia_id}/hechos/{hecho_id}/reconsiderar")
def reconsiderar_hecho(
    familia_id: int,
    hecho_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
):
    """Un hecho descartado no se borra — queda a la vista y se puede volver a
    mandar a revisión por si el admin cambió de opinión."""
    hecho = db.get(HechoFamiliar, hecho_id)
    hecho.estado = EstadoHechoFamiliar.pendiente
    return RedirectResponse(f"/admin/familias/{familia_id}/hechos", status_code=303)


# ---------- Activity log / Settings (por familia, admin_familia o superadmin) ----------

ACCION_LABELS = {
    "usuario_login": "Login",
    "familia_borrada": "Familia borrada",
    "usuario_agregado_a_familia": "Usuario agregado",
    "rol_cambiado": "Rol cambiado",
    "usuario_quitado_de_familia": "Usuario quitado",
    "guion_creado": "Guion creado",
    "guion_borrado": "Guion borrado",
    "guion_aprobado": "Guion aprobado (bandeja)",
    "guion_desactivado": "Guion desactivado (bandeja)",
    "historia_aprobada": "Historia aprobada (bandeja)",
    "historia_desactivada": "Historia desactivada (bandeja)",
    "conversacion_configurada": "Conversación configurada",
    "db_inicializada": "DB inicializada",
    "db_reset_parcial": "Reset parcial de datos",
    "db_reset_total": "Reset total",
    "ia_sin_saldo": "Sin saldo de IA",
}

ACTIVITY_LOG_PAGE_SIZE = 50


@router.get("/familias/{familia_id}/activity-log", response_class=HTMLResponse)
def activity_log_page(
    familia_id: int,
    request: Request,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
    accion: str = Query(default=""),
    target_type: str = Query(default=""),
    usuario_id: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    page: int = Query(default=1),
):
    familia = db.get(Familia, familia_id)
    all_entries = db.scalars(
        select(ActivityLog)
        .options(joinedload(ActivityLog.usuario))
        .where(
            or_(
                ActivityLog.familia_id == familia_id,
                # "Sin saldo de IA" es un evento global (afecta a toda la
                # app por igual, no a una familia puntual) — se muestra en
                # el log de todas, a diferencia del resto de los eventos sin
                # familia_id (ej. logins), que quedan como están.
                ActivityLog.accion == AccionActividad.ia_sin_saldo,
            )
        )
        .order_by(ActivityLog.creado_en.desc())
    ).unique().all()

    all_target_types = sorted({e.target_type for e in all_entries if e.target_type})
    all_usuarios: dict[int, Usuario] = {}
    for e in all_entries:
        if e.usuario and e.usuario_id not in all_usuarios:
            all_usuarios[e.usuario_id] = e.usuario

    f_accion = accion.strip()
    f_target_type = target_type.strip()
    try:
        f_usuario_id = int(usuario_id)
    except (ValueError, TypeError):
        f_usuario_id = 0
    if f_usuario_id not in all_usuarios:
        f_usuario_id = 0
    f_date_from = date_from.strip()
    f_date_to = date_to.strip()

    entries = list(all_entries)
    if f_accion:
        entries = [e for e in entries if e.accion.value == f_accion]
    if f_target_type:
        entries = [e for e in entries if e.target_type == f_target_type]
    if f_usuario_id:
        entries = [e for e in entries if e.usuario_id == f_usuario_id]
    if f_date_from:
        try:
            d_from = date.fromisoformat(f_date_from)
            entries = [e for e in entries if e.creado_en.date() >= d_from]
        except ValueError:
            f_date_from = ""
    if f_date_to:
        try:
            d_to = date.fromisoformat(f_date_to)
            entries = [e for e in entries if e.creado_en.date() <= d_to]
        except ValueError:
            f_date_to = ""

    total = len(entries)
    all_total = len(all_entries)
    total_pages = max((total + ACTIVITY_LOG_PAGE_SIZE - 1) // ACTIVITY_LOG_PAGE_SIZE, 1)
    page = min(max(page, 1), total_pages)
    page_entries = entries[(page - 1) * ACTIVITY_LOG_PAGE_SIZE: page * ACTIVITY_LOG_PAGE_SIZE]

    active_filters = sum([
        bool(f_accion), bool(f_target_type), bool(f_usuario_id), bool(f_date_from), bool(f_date_to),
    ])

    return templates.TemplateResponse(
        "admin/activity_log.html",
        {
            "request": request,
            "user": user,
            "familia": familia,
            "entries": page_entries,
            "accion_labels": ACCION_LABELS,
            "all_acciones": list(AccionActividad),
            "all_target_types": all_target_types,
            "all_usuarios": sorted(all_usuarios.values(), key=lambda u: u.nombre.lower()),
            "f_accion": f_accion,
            "f_target_type": f_target_type,
            "f_usuario_id": f_usuario_id,
            "f_date_from": f_date_from,
            "f_date_to": f_date_to,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "all_total": all_total,
            "active_filters": active_filters,
        },
    )


# Tablas que se pueden regenerar selectivamente desde Settings — a diferencia
# de Personajes/Guiones (contenido armado a mano por el admin), son datos que
# se van generando solos con el uso, así que borrarlos no destruye ningún
# guion diseñado. A diferencia del reset total (ver más abajo), esto queda
# acotado a UNA familia — cada entrada define cómo llegar desde el modelo
# hasta familia_id para poder filtrar.
RESET_TABLES = {
    "interacciones": {
        "label": "Interacciones",
        "model": Interaccion,
        "desc": "Historial de mensajes de guiones (envíos y respuestas) de esta familia.",
        "scope": lambda familia_id: Interaccion.guion_id.in_(
            select(Guion.id).join(Personaje).where(Personaje.familia_id == familia_id)
        ),
    },
    "historias_sesiones": {
        "label": "Sesiones de historia",
        "model": HistoriaSesion,
        "desc": "Sesiones de Historia y sus mensajes (no las historias/plantillas en sí) de esta familia.",
        "scope": lambda familia_id: HistoriaSesion.historia_id.in_(
            select(Historia.id).join(Personaje).where(Personaje.familia_id == familia_id)
        ),
    },
    "hechos": {
        "label": "Hechos familiares",
        "model": HechoFamiliar,
        "desc": "Hechos detectados a partir de las Historias (pendientes, validados y descartados) de esta familia.",
        "scope": lambda familia_id: HechoFamiliar.familia_id == familia_id,
    },
    "push": {
        "label": "Suscripciones push",
        "model": PushSubscription,
        "desc": "Suscripciones push guardadas de esta familia — su paciente deja de recibir notificaciones hasta que las vuelva a habilitar.",
        "scope": lambda familia_id: PushSubscription.paciente_id.in_(
            select(Paciente.id).where(Paciente.familia_id == familia_id)
        ),
    },
    "activity_log": {
        "label": "Activity log",
        "model": ActivityLog,
        "desc": "El historial de esta misma pantalla, de esta familia.",
        "scope": lambda familia_id: ActivityLog.familia_id == familia_id,
    },
}
RESET_DELETE_ORDER = ["interacciones", "historias_sesiones", "hechos", "push", "activity_log"]


@router.get("/familias/{familia_id}/settings", response_class=HTMLResponse)
def settings_page(
    familia_id: int,
    request: Request,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
    msg: str = "",
):
    familia = db.get(Familia, familia_id)
    stats = {
        key: db.scalar(select(func.count()).select_from(cfg["model"]).where(cfg["scope"](familia_id)))
        for key, cfg in RESET_TABLES.items()
    }
    return templates.TemplateResponse(
        "admin/settings.html",
        {
            "request": request,
            "user": user,
            "familia": familia,
            "msg": msg,
            "reset_tables": RESET_TABLES,
            "stats": stats,
        },
    )


@router.post("/familias/{familia_id}/settings/reset-tables")
def settings_reset_tables(
    familia_id: int,
    user: Usuario = Depends(require_admin_familia),
    db: Session = Depends(get_db_dep),
    confirm: str = Form(""),
    tables: list[str] = Form(default=[]),
):
    if confirm.strip() != "BORRAR":
        return RedirectResponse(f"/admin/familias/{familia_id}/settings?msg=confirm_error", status_code=303)

    selected = [key for key in RESET_DELETE_ORDER if key in tables and key in RESET_TABLES]
    if not selected:
        return RedirectResponse(f"/admin/familias/{familia_id}/settings?msg=no_selection", status_code=303)

    for key in selected:
        cfg = RESET_TABLES[key]
        db.execute(delete(cfg["model"]).where(cfg["scope"](familia_id)))

    registrar_actividad(
        db, AccionActividad.db_reset_parcial, usuario_id=user.id, familia_id=familia_id,
        detalle=f"tablas={selected}",
    )
    return RedirectResponse(f"/admin/familias/{familia_id}/settings?msg=reset_tables_ok", status_code=303)


# ---------- Settings global (solo superadmin): inicializar/resetear TODO el sistema ----------

@router.get("/settings", response_class=HTMLResponse)
def settings_superadmin_page(
    request: Request,
    user: Usuario = Depends(require_superadmin),
    db: Session = Depends(get_db_dep),
    msg: str = "",
):
    stats = {
        "familias": db.scalar(select(func.count()).select_from(Familia)),
        "usuarios": db.scalar(select(func.count()).select_from(Usuario)),
    }
    return templates.TemplateResponse(
        "admin/settings_superadmin.html",
        {"request": request, "user": user, "msg": msg, "stats": stats},
    )


@router.post("/settings/init")
def settings_init(
    user: Usuario = Depends(require_superadmin),
    db: Session = Depends(get_db_dep),
):
    Base.metadata.create_all(bind=engine)
    registrar_actividad(db, AccionActividad.db_inicializada, usuario_id=user.id)
    return RedirectResponse("/admin/settings?msg=init_ok", status_code=303)


@router.post("/settings/reset")
def settings_reset(
    user: Usuario = Depends(require_superadmin),
    db: Session = Depends(get_db_dep),
    confirm: str = Form(""),
):
    """La zona nuclear: borra TODO (todas las familias, personajes, guiones,
    usuarios) y recrea el esquema vacío. Para no perder el acceso, el único
    usuario que sobrevive es el que ejecuta esta acción — se vuelve a crear
    con el mismo email/contraseña que ya tenía, ahora como único superadmin.
    Se usa una conexión cruda (no la Session de ORM) porque drop_all/
    create_all deja obsoleta cualquier transacción ya abierta."""
    if confirm.strip() != "RESET":
        return RedirectResponse("/admin/settings?msg=confirm_error", status_code=303)

    saved_email = user.email
    saved_nombre = user.nombre
    saved_hash = user.password_hash

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO usuarios (nombre, email, password_hash, es_superadmin) "
                "VALUES (:nombre, :email, :pw, true) RETURNING id"
            ),
            {"nombre": saved_nombre, "email": saved_email, "pw": saved_hash},
        )
        new_user_id = result.scalar()
        conn.execute(
            text(
                "INSERT INTO activity_log (usuario_id, accion, creado_en) "
                "VALUES (:uid, 'db_reset_total', NOW())"
            ),
            {"uid": new_user_id},
        )

    response = RedirectResponse("/login", status_code=303)
    clear_session(response)
    return response
