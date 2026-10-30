import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.db import get_db
from app.models.paciente import Paciente
from app.services import motor

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()


def _tick() -> None:
    with get_db() as db:
        pacientes = db.scalars(select(Paciente)).all()
        for paciente in pacientes:
            try:
                procesados = motor.procesar_guiones_vencidos(db, paciente.id)
                if procesados:
                    logger.info(
                        "Scheduler: %d guion(es) procesados para paciente %s",
                        len(procesados),
                        paciente.id,
                    )
            except Exception:
                logger.exception(
                    "Error procesando guiones vencidos para paciente %s", paciente.id
                )


def start_scheduler(interval_seconds: int = 20) -> BackgroundScheduler:
    if not _scheduler.running:
        _scheduler.add_job(
            _tick, "interval", seconds=interval_seconds, id="procesar_guiones_vencidos"
        )
        _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
