import os

_STATIC_DIR = os.path.join("app", "static")


def static_version(rel_path: str) -> int:
    """mtime del archivo estático, para invalidar el cache del navegador cada
    vez que cambia — sin esto, un CSS/JS editado puede seguir sirviéndose
    viejo desde el cache del navegador hasta un hard refresh manual (nos pasó
    más de una vez con admin.css)."""
    try:
        return int(os.path.getmtime(os.path.join(_STATIC_DIR, rel_path)))
    except OSError:
        return 0
