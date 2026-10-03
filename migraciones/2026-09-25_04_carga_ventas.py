#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carga venta_diaria desde 2026-09-25_03_venta_diaria.csv (formato ya largo:
estacion_id, fecha, producto, litros, precio_venta; vacio = NULL).

Uso:
    python3 2026-09-25_04_carga_ventas.py --db RUTA_A_COPIA_LOCAL

OJO: --db debe apuntar a una COPIA LOCAL, no al red.db de OneDrive.
Requiere 2026-09-25_03_ventas_diarias.sql ya aplicado.
Idempotente: INSERT OR REPLACE sobre la PK (estacion_id, fecha, producto).
NO activar journal_mode=WAL.
"""
import argparse, csv, os, sqlite3, sys

def num(s):
    s = (s or '').strip()
    return None if s == '' else float(s)

def main():
    aqui = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--csv', default=os.path.join(aqui, '2026-09-25_03_venta_diaria.csv'))
    a = ap.parse_args()

    con = sqlite3.connect(os.path.abspath(a.db))
    con.execute('PRAGMA foreign_keys = ON')
    ids = {i for i, in con.execute('SELECT id FROM estacion')}

    filas, huerfanos = [], {}
    with open(a.csv, encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            eid = int(r['estacion_id'])
            if eid not in ids:
                huerfanos[eid] = huerfanos.get(eid, 0) + 1
                continue
            filas.append((eid, r['fecha'], r['producto'], num(r['litros']), num(r['precio_venta'])))

    if huerfanos:
        raise SystemExit(f'ABORTA: estacion_id inexistentes en estacion: {huerfanos}')

    con.executemany('INSERT OR REPLACE INTO venta_diaria '
                    '(estacion_id, fecha, producto, litros, precio_venta) VALUES (?,?,?,?,?)', filas)
    con.commit()

    tot, f0, f1, ne = con.execute(
        'SELECT COUNT(*), MIN(fecha), MAX(fecha), COUNT(DISTINCT estacion_id) FROM venta_diaria').fetchone()
    print(f'insertados : {len(filas):,}')
    print(f'venta_diaria: {tot:,} renglones, {f0} .. {f1}, {ne} estaciones')
    for p, c, nl, npv in con.execute(
            'SELECT producto, COUNT(*), SUM(litros IS NULL), SUM(precio_venta IS NULL) '
            'FROM venta_diaria GROUP BY 1 ORDER BY 1'):
        print(f'   {p:8s} {c:7,}   litros NULL={nl}  precio NULL={npv}')
    con.close()

if __name__ == '__main__':
    main()
