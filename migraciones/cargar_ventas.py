r"""Carga ventas diarias a red.db desde el Excel del operador.

    python migraciones\cargar_ventas.py "ruta\al\archivo.xlsx"          (simula)
    python migraciones\cargar_ventas.py "ruta\al\archivo.xlsx" --aplicar (escribe)

POR OMISION NO ESCRIBE NADA. Muestra que cambiaria y se detiene. Solo con
--aplicar toca red.db, y entonces sigue el procedimiento completo: censo,
respaldo con fecha en migraciones\, copia local, migracion sobre la copia,
verificacion, limpieza de journals y sobrescritura.

FORMATO DE ENTRADA
------------------
Una fila por estacion y dia, con los tres productos a lo ancho:

    Estacion | Fecha | Diesel | Premium | Regular | $DIESEL | $PREMIUM | $REGULAR

Los encabezados se comparan sin acentos, sin mayusculas y sin espacios
sobrantes, asi que "Regular " y "REGULAR" dan igual. La fecha acepta
DD/MM/AAAA, AAAA-MM-DD y fechas reales de Excel.

REGLAS QUE APLICA, todas heredadas de la carga original
-------------------------------------------------------
- Celda vacia, 0 o casi-cero (1E-10) significan "no se ofrecio el producto
  ese dia", NO cero litros. Se cargan como NULL para que no sesguen los
  promedios: AVG y SUM ignoran NULL solos.
- Si litros y precio quedan ambos nulos, el renglon no se inserta. La
  ausencia es el dato.
- Los precios se redondean a 2 decimales, como en la carga original.
- La llave es (estacion_id, fecha, producto): volver a correr el mismo
  archivo no duplica nada, y un archivo con dias nuevos solo agrega esos.
"""
from __future__ import annotations

import csv
import os
import shutil
import sqlite3
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent          # migraciones\
CARPETA = AQUI.parent                           # 01.Competencia\
RED = CARPETA / "red.db"
MAPEO = AQUI / "alias_ventas.csv"

PRODUCTOS = ("DIESEL", "PREMIUM", "REGULAR")
CASI_CERO = 1e-6


# --------------------------------------------------------------- utilidades

def norm(texto) -> str:
    """Sin acentos, sin mayusculas, sin espacios de sobra."""
    s = str(texto or "").strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split())


def a_fecha(valor) -> str:
    """Devuelve AAAA-MM-DD. Acepta lo que suele salir de Excel."""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    s = str(valor).strip()
    if not s:
        raise ValueError("fecha vacia")
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, formato).date().isoformat()
        except ValueError:
            pass
    # Serial de Excel, epoca 1899-12-30
    try:
        n = float(s)
        if 30000 < n < 80000:
            return date.fromordinal(date(1899, 12, 30).toordinal() + int(n)).isoformat()
    except ValueError:
        pass
    raise ValueError("no entiendo la fecha %r" % valor)


def a_numero(valor):
    """None cuando la celda esta vacia, en 0 o en casi-cero.

    Los tres significan lo mismo en el origen: ese dia no se ofrecio el
    producto. Cargarlos como 0 ensuciaria cualquier promedio.
    """
    if valor is None:
        return None
    s = str(valor).strip().replace(",", "").replace("$", "")
    if not s:
        return None
    try:
        n = float(s)
    except ValueError:
        return None
    return None if abs(n) < CASI_CERO else n


# ------------------------------------------------------------------ lectura

def leer(ruta: Path):
    """Devuelve la lista de filas como diccionarios con claves normalizadas."""
    if ruta.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            sys.exit("Para leer .xlsx falta openpyxl:\n"
                     "    pip install openpyxl\n"
                     "O guarda la hoja como CSV y pasa ese archivo.")
        hoja = load_workbook(ruta, data_only=True).active
        filas = list(hoja.values)
        if not filas:
            sys.exit("La hoja esta vacia.")
        cab = [norm(c) for c in filas[0]]
        return [dict(zip(cab, f)) for f in filas[1:] if any(c is not None for c in f)]

    texto = ruta.read_text(encoding="utf-8-sig")
    delim = "\t" if texto.count("\t") > texto.count(",") else ","
    lector = csv.reader(texto.splitlines(), delimiter=delim)
    filas = [f for f in lector if any(c.strip() for c in f)]
    cab = [norm(c) for c in filas[0]]
    return [dict(zip(cab, f)) for f in filas[1:]]


def columna(fila: dict, *nombres):
    for n in nombres:
        if n in fila:
            return fila[n]
    raise KeyError("falta la columna %s. Encontre: %s"
                   % (nombres[0], ", ".join(sorted(fila))))


def cargar_mapeo() -> dict:
    """Nombres del Excel que no coinciden con estacion.alias.

    Vive en un CSV aparte para que agregar uno nuevo sea editar una linea,
    no tocar este script.
    """
    if not MAPEO.exists():
        return {}
    m = {}
    for f in csv.DictReader(MAPEO.read_text(encoding="utf-8-sig").splitlines()):
        claves = {norm(k): v for k, v in f.items()}
        m[norm(claves.get("EXCEL"))] = str(claves.get("ALIAS") or "").strip()
    return m


# ------------------------------------------------------------------ armado

def armar(filas, con):
    """Convierte las filas anchas del Excel en renglones de venta_diaria."""
    por_alias = {}
    for eid, alias, razon in con.execute(
            "SELECT id, alias, razon_social FROM estacion WHERE es_propia = 1"):
        por_alias[norm(alias or razon)] = eid
    mapeo = cargar_mapeo()

    salida, sin_estacion, omitidos = [], {}, 0
    for i, f in enumerate(filas, start=2):
        crudo = str(columna(f, "ESTACION", "ESTACIÓN") or "").strip()
        clave = norm(crudo)
        clave = norm(mapeo.get(clave, clave))
        eid = por_alias.get(clave)
        if eid is None:
            sin_estacion.setdefault(crudo, []).append(i)
            continue
        try:
            fecha = a_fecha(columna(f, "FECHA"))
        except ValueError as exc:
            sys.exit("Fila %d: %s" % (i, exc))

        for prod in PRODUCTOS:
            litros = a_numero(columna(f, prod))
            precio = a_numero(columna(f, "$" + prod))
            if litros is None and precio is None:
                omitidos += 1
                continue
            salida.append((eid, fecha, prod, litros,
                           None if precio is None else round(precio, 2)))
    return salida, sin_estacion, omitidos


def comparar(con, renglones):
    """Separa en nuevos, cambiados e identicos, sin escribir nada."""
    nuevos, cambiados, iguales = [], [], 0
    for eid, fecha, prod, litros, precio in renglones:
        prev = con.execute(
            "SELECT litros, precio_venta FROM venta_diaria "
            "WHERE estacion_id = ? AND fecha = ? AND producto = ?",
            (eid, fecha, prod)).fetchone()
        if prev is None:
            nuevos.append((eid, fecha, prod, litros, precio))
        elif (prev[0], prev[1]) != (litros, precio):
            cambiados.append((eid, fecha, prod, prev[0], prev[1], litros, precio))
        else:
            iguales += 1
    return nuevos, cambiados, iguales


UPSERT = """
INSERT INTO venta_diaria (estacion_id, fecha, producto, litros, precio_venta)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (estacion_id, fecha, producto) DO UPDATE SET
    litros       = excluded.litros,
    precio_venta = excluded.precio_venta
"""


def censo(ruta: Path):
    c = sqlite3.connect("file:%s?mode=ro" % ruta.as_posix(), uri=True)
    objetos = c.execute("SELECT type, name FROM sqlite_master "
                        "WHERE name NOT LIKE 'sqlite_%'").fetchall()
    tablas = sorted(n for t, n in objetos if t == "table")
    conteos = {n: c.execute('SELECT COUNT(*) FROM "%s"' % n).fetchone()[0] for n in tablas}
    forma = (len(tablas), len([1 for t, _ in objetos if t == "view"]))
    c.close()
    return forma, conteos


# -------------------------------------------------------------------- main

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    aplicar = "--aplicar" in sys.argv
    if not args:
        sys.exit(__doc__)
    origen = Path(args[0]).expanduser()
    if not origen.exists():
        sys.exit("No encuentro el archivo: %s" % origen)
    if not RED.exists():
        sys.exit("No encuentro red.db junto a migraciones: %s" % RED)

    filas = leer(origen)
    print("Archivo   : %s" % origen.name)
    print("Renglones : %d" % len(filas))

    con = sqlite3.connect("file:%s?mode=ro" % RED.as_posix(), uri=True)
    renglones, sin_estacion, omitidos = armar(filas, con)

    if sin_estacion:
        print("\nNO RECONOZCO ESTAS ESTACIONES:")
        for nombre, lineas in sorted(sin_estacion.items()):
            print("   %-20s en %d filas (primera: %d)" % (nombre, len(lineas), lineas[0]))
        print("\nAgregalas a %s con el alias que usan en red.db." % MAPEO.name)
        con.close()
        sys.exit(1)

    nuevos, cambiados, iguales = comparar(con, renglones)
    fechas = sorted({r[1] for r in renglones})
    print("Fechas    : %s a %s" % (fechas[0], fechas[-1]))
    print("Productos : %d renglones (%d omitidos por venir vacios)" % (len(renglones), omitidos))
    print("\n  nuevos    : %d" % len(nuevos))
    print("  cambiados : %d" % len(cambiados))
    print("  identicos : %d" % iguales)

    if cambiados:
        alias = {eid: a for eid, a in con.execute(
            "SELECT id, COALESCE(alias, razon_social) FROM estacion")}
        print("\n  CUIDADO: estos renglones YA EXISTIAN con otro valor.")
        for eid, fecha, prod, la, pa, ln, pn in cambiados[:25]:
            print("    %-20s %s %-8s litros %s -> %s | precio %s -> %s"
                  % (alias[eid], fecha, prod, la, ln, pa, pn))
        if len(cambiados) > 25:
            print("    ... y %d mas" % (len(cambiados) - 25))
    con.close()

    if not aplicar:
        print("\nSIMULACION. No se escribio nada.")
        print("Para aplicarlo:  python %s \"%s\" --aplicar" % (Path(__file__).name, origen))
        return
    if not nuevos and not cambiados:
        print("\nNada que cargar: el archivo ya esta en la base.")
        return

    # ---------------------------------------------------------- escritura
    print("\nAplicando. Cierra DBeaver si lo tienes abierto.")
    forma0, conteos0 = censo(RED)

    sello = datetime.now().strftime("%Y-%m-%d_%H%M")
    respaldo = AQUI / ("red_respaldo_previo_%s_ventas.db" % sello)
    shutil.copy2(RED, respaldo)
    print("  respaldo  : migraciones\\%s" % respaldo.name)

    trabajo = Path(os.getenv("TEMP", "/tmp")) / "red_carga.db"
    if trabajo.exists():
        trabajo.unlink()
    shutil.copy2(RED, trabajo)

    w = sqlite3.connect(str(trabajo))
    w.execute("PRAGMA foreign_keys = ON")
    w.executemany(UPSERT, renglones)
    w.commit()
    integridad = w.execute("PRAGMA integrity_check").fetchone()[0]
    fk = w.execute("PRAGMA foreign_key_check").fetchall()
    diario = w.execute("PRAGMA journal_mode").fetchone()[0]
    total = w.execute("SELECT COUNT(*) FROM venta_diaria").fetchone()[0]
    w.close()

    print("  integrity : %s" % integridad)
    print("  claves    : %s" % ("sin violaciones" if not fk else fk))
    print("  journal   : %s" % diario)
    if integridad != "ok" or fk or diario.lower() != "delete":
        sys.exit("  ALGO SALIO MAL. red.db NO se toco. Revisa el respaldo.")
    if total != conteos0["venta_diaria"] + len(nuevos):
        sys.exit("  El conteo no cuadra (%d, esperaba %d). red.db NO se toco."
                 % (total, conteos0["venta_diaria"] + len(nuevos)))

    for suelto in CARPETA.glob("red.db-*"):
        suelto.unlink()
        print("  borrado   : %s" % suelto.name)

    shutil.copy2(trabajo, RED)
    forma1, conteos1 = censo(RED)
    if forma1 != forma0:
        sys.exit("  El modelo cambio de forma. Restaura %s" % respaldo.name)
    for tabla, n in conteos0.items():
        esperado = n + len(nuevos) if tabla == "venta_diaria" else n
        if conteos1[tabla] != esperado:
            sys.exit("  %s quedo en %d y esperaba %d. Restaura %s"
                     % (tabla, conteos1[tabla], esperado, respaldo.name))

    print("\nLISTO. venta_diaria: %d -> %d renglones (+%d nuevos, %d actualizados)."
          % (conteos0["venta_diaria"], conteos1["venta_diaria"], len(nuevos), len(cambiados)))
    print("Refresca la conexion en DBeaver y, si la aplicacion esta abierta,")
    print("llama a POST /api/db/refresh o solo recarga la pagina.")


if __name__ == "__main__":
    main()
