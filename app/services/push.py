import json
import logging

from pywebpush import WebPushException, webpush
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.paciente import Paciente

logger = logging.getLogger(__name__)


def enviar_push_paciente(db: Session, paciente: Paciente, titulo: str, cuerpo: str, url: str) -> None:
    """Adaptador aislado: manda una notificación push real (sonido/vibración
    del sistema operativo, funciona con la app cerrada). Si el paciente no
    tiene push habilitado, no hay claves VAPID configuradas, o no tiene
    ninguna suscripción activa, no hace nada — nunca debe romper el envío
    del guion en sí."""
    if not paciente.push_habilitado:
        return

    settings = get_settings()
    if not settings.vapid_public_key:
        logger.warning("VAPID no configurado; se omite el push.")
        return

    payload = json.dumps({"titulo": titulo, "cuerpo": cuerpo, "url": url})
    for sub in list(paciente.push_subscriptions):
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=settings.vapid_private_key_path,
                vapid_claims={"sub": f"mailto:{settings.vapid_claims_email}"},
            )
        except WebPushException as e:
            status = e.response.status_code if e.response is not None else None
            logger.warning("Push falló para suscripción %s (status=%s): %s", sub.id, status, e)
            if status in (404, 410):
                # Suscripción vencida o revocada por el navegador: la limpiamos.
                db.delete(sub)
        except Exception:
            logger.exception("Error inesperado enviando push a suscripción %s", sub.id)
