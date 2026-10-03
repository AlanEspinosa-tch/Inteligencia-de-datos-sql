"""API de monitoreo de precios y competencia — Grupo Treher.

Solo lectura sobre red.db. La API nunca escribe en la base.

Etapa 4: rutas de diagnostico (aqui) mas las rutas de datos, en routes.py.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__, config, db, routes


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    # Falla en el arranque, no en la primera peticion.
    config.validate()
    db.asegurar_fresco(forzar=True)
    yield


app = FastAPI(
    title="Red Treher — API de competencia",
    description="Solo lectura sobre red.db. La API nunca escribe en la base.",
    version=__version__,
    lifespan=ciclo_de_vida,
)

app.include_router(routes.router)

if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


@app.get("/health", tags=["diagnostico"])
def health():
    """Vivo, conectado, y que tan fresca esta la copia de la base."""
    try:
        estado = db.estado()
        estaciones = db.uno("SELECT COUNT(*) AS n FROM estacion")["n"]
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Sin acceso a red.db: %s" % exc)
    return {"ok": True, "version": __version__, "estaciones": estaciones, "base": estado}


@app.get("/api/db/info", tags=["diagnostico"])
def db_info():
    """Censo del modelo: objetos y conteos. Si esto deja de coincidir con
    lo documentado, la base cambio y la aplicacion puede estar mintiendo."""
    try:
        return {"config": config.resumen(), "censo": db.censo()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/db/refresh", tags=["diagnostico"])
def db_refresh():
    """Fuerza volver a copiar red.db. Util justo despues de una carga."""
    try:
        copio = db.asegurar_fresco(forzar=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"copiado": copio, "base": db.estado()}


# El frontend lo sirve esta misma API, montado al final para que las rutas de
# arriba ganen. Asi no hace falta CORS ni un segundo servidor: se abre
# http://127.0.0.1:8000/ y ya.
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
