#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carga precio_diario desde "PRECIOS COMPETENCIA 2026.csv".

Uso:
    python3 2026-09-25_02_carga_precios_cne.py --db RUTA_A_COPIA_LOCAL [--csv RUTA]

OJO: apuntar --db a una COPIA LOCAL, no al red.db de OneDrive. El mount FUSE
no deja a SQLite escribir en sitio. Flujo completo:
    copy red.db  %TEMP%\\work.db
    python3 2026-09-25_02_carga_precios_cne.py --db %TEMP%\\work.db
    del red.db-journal   (si existe)
    copy /Y %TEMP%\\work.db  red.db

Requiere 2026-09-25_01_marcas_y_precio_diario.sql ya aplicado.
Idempotente: INSERT OR REPLACE sobre la PK (estacion_id, fecha, producto).

Reglas de limpieza, todas verificadas contra el archivo del 25-sep-2026:
  - El CSV viene en formato ANCHO; se convierte a LARGO.
  - Precio 0 = SIN DATO. No se carga. (El archivo no usa celdas vacias.)
  - Fecha en DD/MM/AAAA -> AAAA-MM-DD.
  - Encoding UTF-8 con BOM, saltos CRLF.
  - Duplicados (permiso, fecha): existen y son identicos en precio; la PK
    los colapsa. Si alguna vez DIFIEREN, el script lo reporta y aborta.
"""
import argparse, csv, os, sqlite3, sys, collections

MAP = {'Regular': 'REGULAR', 'Premium': 'PREMIUM', 'Diesel': 'DIESEL'}


def main():
    aqui = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True, help='copia local de red.db')
    ap.add_argument('--csv', default=os.path.join(aqui, '..', 'PRECIOS COMPETENCIA 2026.csv'))
    a = ap.parse_args()

    con = sqlite3.connect(os.path.abspath(a.db))
    # NO activar WAL: ver meta.no_usar_wal
    ids = {p: i for p, i in con.execute('SELECT permiso, id FROM estacion')}
    print(f'base: {os.path.abspath(a.db)}')
    print(f'csv : {os.path.abspath(a.csv)}')
    print(f'estaciones en la base: {len(ids)}')

    largo, choques, sin_estacion = {}, [], collections.Counter()
    ceros = collections.Counter()
    n = 0
    with open(a.csv, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            n += 1
            eid = ids.get(r['Permiso CRE'].strip())
            if eid is None:
                sin_estacion[r['Permiso CRE'].strip()] += 1
                continue
            d, m, y = r['Fecha'].strip().split('/')
            fecha = f'{y}-{m.zfill(2)}-{d.zfill(2)}'
            for col, prod in MAP.items():
                raw = (r[col] or '').strip()
                if raw == '':
                    continue
                v = float(raw)
                if v == 0:
                    ceros[prod] += 1
                    continue
                if not (10 <= v <= 45):
                    raise SystemExit(f'ABORTA: precio fuera de 10-45: {r["Permiso CRE"]} {fecha} {prod} = {v}')
                k = (eid, fecha, prod)
                if k in largo and largo[k] != v:
                    choques.append((k, largo[k], v))
                largo[k] = v

    print(f'\nrenglones leidos del csv : {n:,}')
    print(f'ceros omitidos           : {dict(ceros)}  (total {sum(ceros.values()):,})')
    if sin_estacion:
        print(f'permisos SIN estacion en la base: {len(sin_estacion)}')
        for p, c in sin_estacion.items():
            print(f'   {p}  ({c} renglones)')
    if choques:
        print(f'\nABORTA: {len(choques)} duplicados con precios DISTINTOS:')
        for k, v1, v2 in choques[:20]:
            print('   ', k, v1, '!=', v2)
        sys.exit(1)

    con.executemany(
        'INSERT OR REPLACE INTO precio_diario (estacion_id, fecha, producto, precio) VALUES (?,?,?,?)',
        [(k[0], k[1], k[2], v) for k, v in largo.items()])
    con.commit()

    tot, f0, f1 = con.execute('SELECT COUNT(*), MIN(fecha), MAX(fecha) FROM precio_diario').fetchone()
    print(f'\ninsertados: {len(largo):,}')
    print(f'precio_diario: {tot:,} renglones, {f0} .. {f1}')
    for prod, c in con.execute('SELECT producto, COUNT(*) FROM precio_diario GROUP BY 1 ORDER BY 1'):
        print(f'   {prod:8s} {c:,}')
    con.close()


if __name__ == '__main__':
    main()
