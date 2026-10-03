"""Acceso de SOLO LECTURA a red.db.

Este modulo existe por dos razones concretas:

1. red.db vive en un mount de OneDrive. Si la API lo leyera directo, la
   sincronizacion podria cambiar el archivo a media consulta. Por eso se
   trabaja SIEMPRE sobre una copia local, fuera de OneDrive.

2. La base se sigue poblando. La copia se refresca sola en cuanto el
   original cambia, asi que cargar datos nuevos no obliga a reiniciar nada.

Garantias que este modulo se compromete a cumplir:

  - NUNCA escribe en red.db. El original se abre con mode=ro y solo se lee.
  - NUNCA activa WAL. WAL rompe esta base: OneDrive no soporta el -shm.
  - La copia se toma con la API backup de SQLite, que da una instantanea
    consistente aunque alguien este escribiendo. Copiar bytes a pelo no lo
    garantiza; queda solo como plan B.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from . import config

_lock = threading.Lock()
_state = {
    "firma_origen": None,   # (tamano, mtime) del red.db copiado
    "copiado_en": None,     # epoch de la ultima copia
    "ultima_revision": 0.0, # monotonic de la ultima revision
    "refrescos": 0,
}


def _work_db() -> Path:
    return config.CACHE_DIR / "red_work.db"


def _uri_ro(p: Path) -> str:
    """URI de solo lectura. as_uri() resuelve las diferencias de Windows
    (file:///C:/...) y escapa los espacios de 'TRANSPORTES C MORALES...'."""
    return p.resolve().as_uri() + "?mode=ro"


def _firma(p: Path):
    st = p.stat()
    return (st.st_size, int(st.st_mtime))


def _instantanea(origen: Path, destino: Path) -> str:
    """Copia consistente de origen a destino. Devuelve el metodo usado."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    if tmp.exists():
        tmp.unlink()

    metodo = "backup"
    try:
        src = sqlite3.connect(_uri_ro(origen), uri=True, timeout=10.0)
        try:
            dst = sqlite3.connect(str(tmp))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except sqlite3.Error:
        # Plan B: el origen podria estar bloqueado por DBeaver.
        if tmp.exists():
            tmp.unlink()
        shutil.copy2(origen, tmp)
        metodo = "copia_bytes"

    os.replace(tmp, destino)   # atomico dentro del mismo volumen
    return metodo


def asegurar_fresco(forzar: bool = False) -> bool:
    """Refresca la copia si red.db cambio. True si hubo copia."""
    config.validate()
    ahora = time.monotonic()
    with _lock:
        if (not forzar
                and _state["firma_origen"] is not None
                and _work_db().exists()
                and (ahora - _state["ultima_revision"]) < config.CHECK_INTERVAL_SECONDS):
            return False

        _state["ultima_revision"] = ahora
        firma = _firma(config.RED_DB_PATH)

        if forzar or firma != _state["firma_origen"] or not _work_db().exists():
            _instantanea(config.RED_DB_PATH, _work_db())
            _state["firma_origen"] = firma
            _state["copiado_en"] = time.time()
            _state["refrescos"] += 1
            return True
        return False


@contextmanager
def conexion():
    """Conexion de solo lectura a la COPIA. Una por llamada: las conexiones
    de sqlite3 no son seguras entre hilos y FastAPI usa un pool."""
    asegurar_fresco()
    con = sqlite3.connect(_uri_ro(_work_db()), uri=True, timeout=5.0)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only = ON")   # cinturon ademas del tirante
        yield con
    finally:
        con.close()


def consultar(sql: str, params=()) -> list:
    with conexion() as con:
        return [dict(f) for f in con.execute(sql, params).fetchall()]


def uno(sql: str, params=()):
    filas = consultar(sql, params)
    return filas[0] if filas else None


def estado() -> dict:
    """Para /health: que tan fresca esta la copia."""
    asegurar_fresco()
    origen = config.RED_DB_PATH
    st = origen.stat()
    return {
        "origen": str(origen),
        "origen_bytes": st.st_size,
        "origen_modificado": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
        "copia": str(_work_db()),
        "copia_tomada": (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_state["copiado_en"]))
                         if _state["copiado_en"] else None),
        "refrescos_desde_el_arranque": _state["refrescos"],
        "revisa_cada_segundos": config.CHECK_INTERVAL_SECONDS,
    }


def censo() -> dict:
    """Inventario de objetos y conteos. Sirve para detectar que el modelo
    cambio sin que la aplicacion se entere."""
    with conexion() as con:
        objetos = con.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
        tablas, vistas, indices = [], [], []
        for fila in objetos:
            {"table": tablas, "view": vistas, "index": indices}.get(fila["type"], []).append(fila["name"])
        conteos = {}
        for nombre in tablas:
            conteos[nombre] = con.execute('SELECT COUNT(*) FROM "%s"' % nombre).fetchone()[0]
        version = con.execute("SELECT sqlite_version()").fetchone()[0]
        journal = con.execute("PRAGMA journal_mode").fetchone()[0]
    return {
        "sqlite_version": version,
        "journal_mode": journal,
        "tablas": tablas,
        "vistas": vistas,
        "indices": indices,
        "conteos": conteos,
    }
