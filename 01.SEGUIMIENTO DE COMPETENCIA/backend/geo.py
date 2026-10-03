"""Distancias geograficas.

SQLite no trae funciones espaciales: no hay ST_Distance ni indices
geograficos. Y relacion_estacion solo guarda los 96 pares que el operador
reviso, no todos contra todos. Asi que un radio variable en la interfaz
tiene que calcularse aqui.

Con 93 estaciones son 8,649 pares: una barbaridad de poco trabajo. No hace
falta indice espacial ni precalculo.

Se usa Haversine, que es la misma formula con la que se llenaron las
distancias que ya estan en la base. Es distancia en linea recta, NO
distancia de manejo: dos estaciones en cuerpos opuestos de autopista
pueden quedar a 150 m y no competir. Por eso el radio es filtro de
descubrimiento y nunca criterio: quien compite con quien lo decide
relacion_estacion.es_competencia, que confirmo el operador.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

RADIO_TIERRA_KM = 6371.0088     # radio medio, el mismo que uso la carga original


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    f1, f2 = radians(lat1), radians(lat2)
    df = f2 - f1
    dl = radians(lon2 - lon1)
    a = sin(df / 2) ** 2 + cos(f1) * cos(f2) * sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_KM * asin(sqrt(a))


def dentro_del_radio(origen: dict, candidatas, radio_km: float, incluir_origen=False):
    """Devuelve las candidatas dentro del radio, ordenadas por distancia.

    origen y cada candidata son dicts con id, latitud y longitud.
    """
    salida = []
    for c in candidatas:
        if not incluir_origen and c["id"] == origen["id"]:
            continue
        d = haversine_km(origen["latitud"], origen["longitud"], c["latitud"], c["longitud"])
        if d <= radio_km:
            item = dict(c)
            item["distancia_km"] = round(d, 3)
            salida.append(item)
    salida.sort(key=lambda x: x["distancia_km"])
    return salida
