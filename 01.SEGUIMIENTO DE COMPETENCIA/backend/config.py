r"""Configuracion. Todo sale de variables de entorno o del archivo .env.

NO HAY CREDENCIALES. red.db es un archivo SQLite: no hay host, puerto,
usuario ni contrasena que proteger.

RED_DB_PATH NO DEBERIA HACER FALTA, y lo normal es dejarlo vacio.

La carpeta del proyecto vive en SharePoint y se sincroniza entre varias
maquinas. Cada usuario la ve en una ruta distinta:

    C:\Users\preci\...\Tesoreria y Finanzas Treher - ...\01.Competencia
    C:\Users\TREHER\...\Finanzas Treher - ...\01.Competencia

Y `.env` esta DENTRO de esa carpeta, asi que tambien se sincroniza: una ruta
absoluta escrita por un usuario le llega al otro y le revienta el arranque.
Paso exactamente eso el 2026-09-29.

Por eso `red.db` se busca por POSICION RELATIVA: siempre esta junto a la
carpeta `app`, sea cual sea la ruta absoluta. RED_DB_PATH queda solo para el
caso excepcional de tener la base en otro lado, y aun asi, si apunta a algo
que no existe pero el archivo vecino si, se usa el vecino y se avisa.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # el .env es opcional si las variables ya estan en el entorno
    load_dotenv = None

APP_DIR = Path(__file__).resolve().parent.parent          # .../app
if load_dotenv is not None:
    load_dotenv(APP_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "si", "on")


def _default_cache_dir() -> Path:
    """Carpeta de la copia de trabajo. FUERA de OneDrive, a proposito."""
    base = os.getenv("LOCALAPPDATA") or os.getenv("XDG_CACHE_HOME")
    if not base:
        base = str(Path.home() / ".cache")
    return Path(base) / "treher-red"


# red.db vive junto a la carpeta app/, no dentro de ella.
RED_DB_VECINA = (APP_DIR.parent / "red.db").resolve()

_raw_db = os.getenv("RED_DB_PATH", "").strip().strip('"').strip("'")
_config_db = Path(_raw_db).expanduser() if _raw_db else None

AVISO_RUTA = None       # se llena si hubo que ignorar lo que decia .env


def _resolver_db():
    """Decide que archivo usar, prefiriendo siempre uno que exista."""
    global AVISO_RUTA
    if _config_db is not None:
        if _config_db.exists():
            return _config_db
        if RED_DB_VECINA.exists():
            AVISO_RUTA = (
                "RED_DB_PATH apunta a una ruta que no existe en esta maquina:\n"
                "    %s\n"
                "Casi seguro es la ruta de otro usuario, sincronizada por SharePoint.\n"
                "Se usara el red.db que esta junto a la carpeta app:\n"
                "    %s\n"
                "Para que no vuelva a pasar, deja RED_DB_PATH vacio en .env."
                % (_config_db, RED_DB_VECINA))
            return RED_DB_VECINA
        return _config_db          # que falle con el mensaje de validate()
    return RED_DB_VECINA


RED_DB_PATH = _resolver_db()

_raw_cache = os.getenv("CACHE_DIR", "").strip()
CACHE_DIR = Path(_raw_cache).expanduser() if _raw_cache else _default_cache_dir()

# Cada cuanto se revisa si red.db cambio. No es cada cuanto se copia:
# la copia solo ocurre si el archivo original es distinto.
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
DEBUG = _bool("DEBUG", False)


class ConfigError(RuntimeError):
    pass


def validate() -> None:
    """Falla temprano y con un mensaje que diga que hacer."""
    if AVISO_RUTA:
        print("\n[aviso] " + AVISO_RUTA + "\n", flush=True)

    if not RED_DB_PATH.exists():
        raise ConfigError(
            "No encuentro red.db.\n"
            "  Busque en : %s\n"
            "%s"
            "\nQue revisar, en este orden:\n"
            "  1. Que red.db este en la misma carpeta que 'app', no dentro de ella.\n"
            "  2. Que SharePoint ya haya bajado el archivo: abre la carpeta en el\n"
            "     Explorador y confirma que red.db no tenga el icono de nube.\n"
            "  3. Solo si la base vive en otro lado, pon la ruta en .env.\n"
            "     Ojo: .env se sincroniza entre maquinas, asi que una ruta absoluta\n"
            "     le va a romper el arranque a los demas."
            % (RED_DB_PATH,
               ("  Y antes en: %s (lo decia RED_DB_PATH)\n" % _config_db)
               if _config_db is not None and _config_db != RED_DB_PATH else "")
        )
    if RED_DB_PATH.name != "red.db":
        raise ConfigError(
            "RED_DB_PATH debe apuntar a un archivo llamado red.db, no a %s. "
            "El nombre es fijo para no romper la conexion de DBeaver." % RED_DB_PATH.name
        )


def resumen() -> dict:
    return {
        "red_db_path": str(RED_DB_PATH),
        "red_db_desde": "RED_DB_PATH" if _config_db == RED_DB_PATH else "carpeta vecina",
        "aviso_ruta": AVISO_RUTA,
        "cache_dir": str(CACHE_DIR),
        "check_interval_seconds": CHECK_INTERVAL_SECONDS,
        "api": "%s:%d" % (API_HOST, API_PORT),
        "cors_origins": CORS_ORIGINS,
        "debug": DEBUG,
    }
