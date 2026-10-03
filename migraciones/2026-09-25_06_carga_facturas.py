#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carga factura_compra desde 2026-09-25_05_factura_compra.csv.

Uso:  python3 2026-09-25_06_carga_facturas.py --db RUTA_A_COPIA_LOCAL

OJO: --db a una COPIA LOCAL, no al red.db de OneDrive.
Requiere 2026-09-25_05_factura_compra.sql aplicado.
Idempotente: INSERT OR REPLACE sobre num_factura. NO activar WAL.
"""
import argparse, csv, os, sqlite3

def main():
    aqui = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--csv', default=os.path.join(aqui, '2026-09-25_05_factura_compra.csv'))
    a = ap.parse_args()

    con = sqlite3.connect(os.path.abspath(a.db))
    con.execute('PRAGMA foreign_keys = ON')
    ids = {i for i, in con.execute('SELECT id FROM estacion')}

    filas, vistos, huerfanos = [], set(), {}
    with open(a.csv, encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            nf = r['num_factura'].strip()
            if nf in vistos:
                raise SystemExit(f'ABORTA: num_factura repetido en el csv: {nf}')
            vistos.add(nf)
            eid = int(r['estacion_id'])
            if eid not in ids:
                huerfanos[eid] = huerfanos.get(eid, 0) + 1
                continue
            filas.append((nf, eid, r['fecha_bol'], r['producto'],
                          float(r['litros']), float(r['precio']),
                          r['bol'].strip() or None))
    if huerfanos:
        raise SystemExit(f'ABORTA: estacion_id inexistentes: {huerfanos}')

    con.executemany('INSERT OR REPLACE INTO factura_compra '
                    '(num_factura, estacion_id, fecha_bol, producto, litros, precio, bol) '
                    'VALUES (?,?,?,?,?,?,?)', filas)
    con.commit()

    tot, f0, f1, ne, lts = con.execute(
        'SELECT COUNT(*), MIN(fecha_bol), MAX(fecha_bol), COUNT(DISTINCT estacion_id), SUM(litros) '
        'FROM factura_compra').fetchone()
    print(f'insertadas: {len(filas):,}')
    print(f'factura_compra: {tot:,} facturas, {f0} .. {f1}, {ne} estaciones, {lts:,.0f} litros')
    for p, c, l in con.execute('SELECT producto, COUNT(*), SUM(litros) FROM factura_compra GROUP BY 1 ORDER BY 1'):
        print(f'   {p:8s} {c:6,} facturas  {l:15,.0f} lts')
    print('\nboletas repetidas por clase:')
    for k, n in con.execute('SELECT clase, COUNT(DISTINCT bol) FROM v_boleta_repetida GROUP BY 1 ORDER BY 1'):
        print(f'   {k:18s} {n}')
    con.close()

if __name__ == '__main__':
    main()
