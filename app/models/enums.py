import enum


class UserRole(str, enum.Enum):
    superadmin = "superadmin"
    admin_familia = "admin_familia"
    familiar = "familiar"


class ModoEnvio(str, enum.Enum):
    manual = "manual"
    automatico = "automatico"


class EstadoGuion(str, enum.Enum):
    borrador = "borrador"
    pendiente_aprobacion = "pendiente_aprobacion"
    enviado = "enviado"


class TemaVisual(str, enum.Enum):
    claro = "claro"
    oscuro = "oscuro"


class TamanoFuente(str, enum.Enum):
    normal = "normal"
    grande = "grande"
    muy_grande = "muy_grande"


class EstadoHistoriaSesion(str, enum.Enum):
    activa = "activa"
    finalizada = "finalizada"


class OrigenMensajeHistoria(str, enum.Enum):
    personaje = "personaje"
    paciente = "paciente"


class EstadoHechoFamiliar(str, enum.Enum):
    pendiente = "pendiente"
    validado = "validado"
    descartado = "descartado"


class AccionActividad(str, enum.Enum):
    usuario_login = "usuario_login"
    familia_borrada = "familia_borrada"
    usuario_agregado_a_familia = "usuario_agregado_a_familia"
    rol_cambiado = "rol_cambiado"
    usuario_quitado_de_familia = "usuario_quitado_de_familia"
    guion_creado = "guion_creado"
    guion_borrado = "guion_borrado"
    guion_aprobado = "guion_aprobado"
    guion_desactivado = "guion_desactivado"
    historia_aprobada = "historia_aprobada"
    historia_desactivada = "historia_desactivada"
    conversacion_configurada = "conversacion_configurada"
    db_inicializada = "db_inicializada"
    db_reset_parcial = "db_reset_parcial"
    db_reset_total = "db_reset_total"
    ia_sin_saldo = "ia_sin_saldo"
