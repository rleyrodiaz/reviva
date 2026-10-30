from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.exceptions import AccessDenied, NeedsLogin
from app.routers import admin, auth, chat, push
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Estimulación Cognitiva", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(chat.router)
app.include_router(push.router)


@app.get("/")
def root():
    return RedirectResponse("/login", status_code=303)


@app.get("/manifest.json")
def manifest():
    return FileResponse("app/static/manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    # Servido en la raíz (no en /static) para que su scope cubra toda la app.
    return FileResponse(
        "app/static/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.exception_handler(NeedsLogin)
async def needs_login_handler(request: Request, exc: NeedsLogin):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(AccessDenied)
async def access_denied_handler(request: Request, exc: AccessDenied):
    return PlainTextResponse("Acceso denegado.", status_code=403)
