import io
import logging

logger = logging.getLogger(__name__)


def extraer_texto_archivo(nombre_archivo: str, contenido: bytes) -> str:
    """Extrae texto plano de un .docx o .txt subido para cargar una Historia.
    Ante cualquier problema de parseo, devuelve string vacío en vez de romper
    la carga — el admin puede completar el contenido a mano igual."""
    nombre = (nombre_archivo or "").lower()
    try:
        if nombre.endswith(".docx"):
            from docx import Document

            documento = Document(io.BytesIO(contenido))
            parrafos = [p.text.strip() for p in documento.paragraphs if p.text.strip()]
            return "\n".join(parrafos)
        return contenido.decode("utf-8", errors="replace").strip()
    except Exception:
        logger.exception("No se pudo extraer texto de %r al importar una historia.", nombre_archivo)
        return ""
