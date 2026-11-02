class NeedsLogin(Exception):
    pass


class AccessDenied(Exception):
    def __init__(self, mensaje: str = "No tenés permiso para hacer esto."):
        self.mensaje = mensaje
        super().__init__(mensaje)
