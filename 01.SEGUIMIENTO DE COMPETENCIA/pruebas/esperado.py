"""Genera pruebas/esperado.json con metricas calculadas DESDE SQL.

Lo usa test_mapa.mjs para contrastar lo que la interfaz muestra contra un
calculo hecho por otro camino. Si los dos coinciden, el error tendria que
estar en los dos a la vez.

    python -m pruebas.esperado
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import db, queries                      # noqa: E402

SALIDA = Path(__file__).resolve().parent / "esperado.json"


def para(estacion_id: int) -> dict:
    fecha = db.uno(queries.ULTIMA_FECHA_ESTACION, (estacion_id,))["fecha"]
    mios = {r["producto"]: r["precio"]
            for r in db.consultar(queries.PRECIOS_EN_FECHA, (estacion_id, fecha))}
    comps = []
    for r in db.consultar(queries.COMPETIDORES, (estacion_id,)):
        permitidos = queries.productos_que_compiten(r["compite_en"])
        comps.append({
            "id": r["id"], "km": r["distancia_km"], "en_radio": r["en_radio"],
            "precios": {q["producto"]: q["precio"]
                        for q in db.consultar(queries.PRECIOS_EN_FECHA, (r["id"], fecha))
                        if q["producto"] in permitidos}})

    def met(radio, prod):
        v = [c["precios"][prod] for c in comps if c["km"] <= radio and prod in c["precios"]]
        if not v:
            return None
        prom = sum(v) / len(v)
        return {"n": len(v), "prom": round(prom, 2),
                "min": round(min(v), 2), "max": round(max(v), 2),
                "dif": round(mios[prod] - prom, 2) if prod in mios else None,
                "pct": round((mios[prod] - prom) / prom * 100, 1) if prod in mios else None}

    # El tope del deslizador cuenta TODAS las relacionadas, directas y
    # vecinas, porque el mapa las pinta a las dos.
    vecinos = [{"km": r["distancia_km"]} for r in db.consultar(queries.VECINOS, (estacion_id,))]
    todas = comps + vecinos
    tope = round(max(c["km"] for c in todas) * 10 + 0.4999) / 10 if todas else 0
    return {"fecha": fecha, "mios": mios, "tope": tope,
            "n_total": len(comps),
            "n_vecinos": len(vecinos),
            "n_en_2km": sum(1 for c in comps if c["km"] <= 2.0),
            "fuera_radio": sum(1 for c in comps if not c["en_radio"]),
            "REGULAR_full": met(tope, "REGULAR"),
            "REGULAR_2km": met(2.0, "REGULAR")}


if __name__ == "__main__":
    # 1 = TREHER T (tres competidores, todos dentro del radio)
    # 9 = IXTAZACUALA (dos competidores FUERA del radio, agregados a mano)
    datos = {str(i): para(i) for i in (1, 9)}
    SALIDA.write_text(json.dumps(datos, indent=1, ensure_ascii=False), encoding="utf-8")
    print("escrito", SALIDA)
