"""Pruebas de la capa de conexion (etapa 3).

Se ejecuta con:   python -m pruebas.test_conexion
desde la carpeta app\\ y con el .env ya configurado.

Comprueba lo que de verdad importa: que se lee bien, que NO se escribe en
red.db, que no quedan journals sueltos y que la aritmetica geografica
coincide con la que ya esta guardada en la base.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, db, geo, queries   # noqa: E402

FALLAS = []


def check(nombre, condicion, detalle=""):
    estado = "OK  " if condicion else "FALLA"
    print("  [%s] %s%s" % (estado, nombre, ("  -> " + str(detalle)) if detalle else ""))
    if not condicion:
        FALLAS.append(nombre)


print("=" * 72)
print("0. LA CARPETA VIVE EN SHAREPOINT")
# La ruta absoluta cambia de una maquina a otra, y .env se sincroniza entre
# todas. red.db tiene que encontrarse solo, por posicion relativa.
import importlib, os                                      # noqa: E402
_guardado = os.environ.pop("RED_DB_PATH", None)
try:
    importlib.reload(config)
    check("sin RED_DB_PATH encuentra el red.db vecino",
          config.RED_DB_PATH == (config.APP_DIR.parent / "red.db").resolve()
          and config.RED_DB_PATH.exists(), config.RED_DB_PATH)
    os.environ["RED_DB_PATH"] = "C:\\Users\\OtraPersona\\NoExiste\\red.db"
    importlib.reload(config)
    check("una ruta de otra maquina no tumba el arranque",
          config.RED_DB_PATH == (config.APP_DIR.parent / "red.db").resolve(),
          config.RED_DB_PATH)
    check("y avisa por que la ignoro",
          config.AVISO_RUTA is not None and "SharePoint" in config.AVISO_RUTA)
finally:
    os.environ.pop("RED_DB_PATH", None)
    if _guardado is not None:
        os.environ["RED_DB_PATH"] = _guardado
    importlib.reload(config)
    importlib.reload(db)

print("\n1. CONFIGURACION")
config.validate()
for k, v in config.resumen().items():
    print("     %-24s %s" % (k, v))
check("red.db existe", config.RED_DB_PATH.exists())
check("la copia NO va en OneDrive",
      "onedrive" not in str(config.CACHE_DIR).lower()
      and "01.Competencia" not in str(config.CACHE_DIR),
      config.CACHE_DIR)

print("\n2. COPIA Y REFRESCO")
firma_antes = config.RED_DB_PATH.stat()
t0 = time.time()
copio = db.asegurar_fresco(forzar=True)
ms = (time.time() - t0) * 1000
check("primera copia realizada", copio)
print("       tardo %.0f ms para %.1f MB" % (ms, firma_antes.st_size / 1e6))
check("el archivo de trabajo existe", (config.CACHE_DIR / "red_work.db").exists())
check("segunda llamada no vuelve a copiar", db.asegurar_fresco() is False)

print("\n3. EL ORIGEN NO SE TOCA")
firma_despues = config.RED_DB_PATH.stat()
check("mtime de red.db sin cambios",
      int(firma_antes.st_mtime) == int(firma_despues.st_mtime))
check("tamano de red.db sin cambios", firma_antes.st_size == firma_despues.st_size)
sueltos = [p.name for p in config.RED_DB_PATH.parent.glob("red.db-*")]
check("sin journal/wal/shm sueltos en la carpeta", not sueltos, sueltos or "ninguno")

print("\n4. SOLO LECTURA DE VERDAD")
try:
    with db.conexion() as con:
        con.execute("CREATE TABLE prueba_escritura (x INTEGER)")
    check("la escritura fue rechazada", False, "se permitio escribir")
except sqlite3.Error as exc:
    check("la escritura fue rechazada", True, type(exc).__name__)

print("\n5. CENSO DEL MODELO")
censo = db.censo()
print("     sqlite %s, journal_mode=%s" % (censo["sqlite_version"], censo["journal_mode"]))
check("journal_mode sigue en delete (WAL rompe esta base)",
      censo["journal_mode"].lower() == "delete", censo["journal_mode"])
check("8 tablas", len(censo["tablas"]) == 8, len(censo["tablas"]))
check("8 vistas", len(censo["vistas"]) == 8, len(censo["vistas"]))
check("precio_diario_CNE presente", "precio_diario_CNE" in censo["tablas"])
# El catalogo y los criterios no crecen solos: aqui el conteo es exacto y
# cualquier cambio tiene que ser deliberado.
FIJAS = {"estacion": 93, "relacion_estacion": 96, "evento": 10,
         "evento_estacion": 13, "meta": 42}
for t, n in FIJAS.items():
    check("conteo %s = %d" % (t, n), censo["conteos"].get(t) == n, censo["conteos"].get(t))

# Las tablas de datos SI crecen con cada carga. Fijar un numero exacto las
# hacia fallar cada vez que alguien cargaba un archivo nuevo, que es ruido,
# no un hallazgo. Lo que si es un hallazgo es que BAJEN: eso significa que
# una carga borro algo. Estos minimos son de la carga del 2026-09-30.
MINIMOS = {"precio_diario_CNE": 61103, "venta_diaria": 72251, "factura_compra": 8790}
for t, n in MINIMOS.items():
    real = censo["conteos"].get(t, 0)
    check("%s no perdio renglones (>= %d)" % (t, n), real >= n,
          "%d %s" % (real, "(+%d desde la ultima revision)" % (real - n) if real > n else ""))

print("\n6. LITERALES DE PRODUCTO")
for entrada, salida in (("diésel", "DIESEL"), ("Diesel", "DIESEL"),
                        ("regular", "REGULAR"), ("PREMIUM", "PREMIUM")):
    check("normalizar %r -> %s" % (entrada, salida),
          queries.normalizar_producto(entrada) == salida)
try:
    queries.normalizar_producto("magna")
    check("rechaza producto invalido", False)
except ValueError:
    check("rechaza producto invalido", True)
filas = db.consultar(queries.RANGO_FECHAS)
print("     precios: %s .. %s  (%s dias)" % (filas[0]["desde"], filas[0]["hasta"], filas[0]["dias"]))

print("\n7. CONSULTAS DE LA APLICACION")
est = db.consultar(queries.ESTACIONES)
check("93 estaciones", len(est) == 93, len(est))
check("ninguna sin coordenadas",
      all(e["latitud"] and e["longitud"] for e in est))
check("ninguna sin nombre", all(e["nombre"] for e in est))
propias = [e for e in est if e["es_propia"] == 1 and e["activa"] == 1]
check("12 propias activas", len(propias) == 12, len(propias))
sin_precio = [e for e in est if not e["publica_precio"]]
check("11 estaciones sin precio publicado", len(sin_precio) == 11, len(sin_precio))
ult = db.consultar(queries.ULTIMO_PRECIO)
check("ultimo precio para 82 estaciones",
      len({u["estacion_id"] for u in ult}) == 82, len({u["estacion_id"] for u in ult}))
serie = db.consultar(queries.SERIE_PRECIO, (1, "REGULAR", "2026-08-01"))
check("serie historica de TREHER T no vacia", len(serie) > 0, "%d dias" % len(serie))

print("\n8. HAVERSINE CONTRA LAS DISTANCIAS YA GUARDADAS")
pares = db.consultar("""
    SELECT x.distancia_km AS guardada,
           a.latitud AS la, a.longitud AS lo,
           b.latitud AS lb, b.longitud AS lob
    FROM relacion_estacion x
    JOIN estacion a ON a.id = x.estacion_id
    JOIN estacion b ON b.id = x.relacionada_id""")
peor = 0.0
for p in pares:
    calc = geo.haversine_km(p["la"], p["lo"], p["lb"], p["lob"])
    peor = max(peor, abs(calc - p["guardada"]))
check("los 96 pares coinciden (< 10 m)", peor < 0.010,
      "desviacion maxima %.1f m en %d pares" % (peor * 1000, len(pares)))

print("\n9. ESTADO PARA /health")
for k, v in db.estado().items():
    print("     %-28s %s" % (k, v))

print("\n" + "=" * 72)
if FALLAS:
    print("FALLARON %d prueba(s): %s" % (len(FALLAS), ", ".join(FALLAS)))
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
