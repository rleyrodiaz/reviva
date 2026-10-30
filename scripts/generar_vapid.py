"""Genera un par de claves VAPID nuevo para Web Push (solo hace falta correrlo
una vez por entorno). Guarda la privada en vapid_private_key.pem (NO subir a
git) e imprime la pública en el formato base64url que espera el navegador
para pegar en VAPID_PUBLIC_KEY en el .env.

Uso: .venv\\Scripts\\python.exe scripts\\generar_vapid.py
"""
import base64

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid02

v = Vapid02()
v.generate_keys()
v.save_key("vapid_private_key.pem")

raw = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
public_b64url = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

print("Clave privada guardada en vapid_private_key.pem (no la subas a git).")
print("\nVAPID_PUBLIC_KEY=" + public_b64url)
