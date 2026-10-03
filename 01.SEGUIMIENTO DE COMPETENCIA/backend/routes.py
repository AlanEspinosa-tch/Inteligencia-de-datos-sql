"""Rutas de datos (etapa 4).

Criterios que estas rutas respetan y que conviene no perder de vista:

- "Mi red hoy" son 12 estaciones. TREHER LL cuenta como propia pero esta
  cerrada, asi que `tipo=propia` la excluye salvo que se pida `activa=false`.
- Una estacion que no publica precio SI aparece. Se ubica en el mapa con
  `publica_precio = 0` y sin precios. Son 11, dos de ellas competidores
  confirmados.
- Los pares de competencia son DIRIGIDOS: se leen tal como estan, nunca al
  reves. Que A compita con B no implica que B compita con A.
- `es_competencia` decide el color del marcador: 1 = competencia directa,
  0 = vecino registrado que NO compite. Los dos se muestran; solo los
  directos entran en las metricas de comparacion.
- La comparacion de precios se hace SIEMPRE dentro de la misma fecha. Comparar
  el ultimo precio de dos estaciones que publicaron dias distintos no
  significa nada.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from . import db, queries, schemas

router = APIRouter(prefix="/api", tags=["datos"])


# ---------------------------------------------------------------- catalogos

@router.get("/catalogos", response_model=schemas.Catalogos,
            summary="Valores para poblar los filtros")
def catalogos():
    marcas = db.consultar(queries.CATALOGO_MARCAS)
    ubic = db.consultar(queries.CATALOGO_UBICACION)
    rango = db.consultar(queries.RANGO_FECHAS)[0]
    tot = db.uno("SELECT COUNT(*) AS n FROM estacion")["n"]
    act = db.uno("SELECT COUNT(*) AS n FROM estacion WHERE es_propia = 1 AND activa = 1")["n"]
    sinp = db.uno('SELECT COUNT(*) AS n FROM estacion '
                  'WHERE id NOT IN (SELECT estacion_id FROM %s)' % queries.T_PRECIO)["n"]
    return {
        "productos": list(queries.PRODUCTOS),
        "marcas": marcas,
        "estados": sorted({u["estado"] for u in ubic if u["estado"]}),
        "municipios": ubic,
        "precios_desde": rango["desde"],
        "precios_hasta": rango["hasta"],
        "dias_con_precio": rango["dias"],
        "total_estaciones": tot,
        "propias_activas": act,
        "sin_precio": sinp,
    }


# --------------------------------------------------------------- estaciones

def _filtrar_estaciones(tipo, marca, estado, municipio, con_precio, activa, q):
    filas = db.consultar(queries.ESTACIONES)
    if tipo == "propia":
        filas = [f for f in filas if f["es_propia"] == 1]
    elif tipo == "competencia":
        filas = [f for f in filas if f["es_propia"] == 0]
    if activa is not None:
        filas = [f for f in filas if f["activa"] == (1 if activa else 0)]
    elif tipo == "propia":
        filas = [f for f in filas if f["activa"] == 1]   # la red que opera hoy
    if marca:
        m = marca.strip().lower()
        if m in ("sin identificar", "sin marca", "null"):
            filas = [f for f in filas if not f["marca"] or f["marca"].strip().lower() == "sin identificar"]
        else:
            filas = [f for f in filas if (f["marca"] or "").strip().lower() == m]
    if estado:
        filas = [f for f in filas if (f["estado"] or "").strip().lower() == estado.strip().lower()]
    if municipio:
        filas = [f for f in filas if (f["municipio"] or "").strip().lower() == municipio.strip().lower()]
    if con_precio is not None:
        filas = [f for f in filas if bool(f["publica_precio"]) is con_precio]
    if q:
        t = q.strip().lower()
        # Incluye razon_social: las propias se buscan por alias, pero alguien
        # puede escribir "Grupo Gasolinero TH" y espera encontrarla.
        filas = [f for f in filas
                 if t in (f["nombre"] or "").lower()
                 or t in (f["razon_social"] or "").lower()
                 or t in (f["permiso"] or "").lower()
                 or t in (f["domicilio"] or "").lower()]
    return filas


@router.get("/estaciones", response_model=list[schemas.Estacion],
            summary="Estaciones, con filtros")
def estaciones(
    tipo: str = Query("todas", pattern="^(todas|propia|competencia)$"),
    marca: Optional[str] = None,
    estado: Optional[str] = None,
    municipio: Optional[str] = None,
    con_precio: Optional[bool] = Query(None, description="true = solo las que reportan a la CNE"),
    activa: Optional[bool] = Query(None, description="Por omision, tipo=propia ya excluye las cerradas"),
    q: Optional[str] = Query(None, description="Busca en nombre, permiso y domicilio"),
):
    return _filtrar_estaciones(tipo, marca, estado, municipio, con_precio, activa, q)


@router.get("/mapa", response_model=list[schemas.EstacionEnMapa],
            summary="Todo lo que el mapa necesita en una sola llamada")
def mapa(
    tipo: str = Query("todas", pattern="^(todas|propia|competencia)$"),
    marca: Optional[str] = None,
    estado: Optional[str] = None,
    municipio: Optional[str] = None,
    con_precio: Optional[bool] = None,
    activa: Optional[bool] = None,
    q: Optional[str] = None,
):
    """Cada estacion con su ULTIMO precio conocido por producto, y la fecha
    de ese precio. La fecha viene por producto a proposito: no todas las
    estaciones publican el mismo dia, y fingir que si seria mentir."""
    filas = _filtrar_estaciones(tipo, marca, estado, municipio, con_precio, activa, q)
    ultimos = db.consultar(queries.ULTIMO_PRECIO)
    por_est: dict = {}
    for u in ultimos:
        por_est.setdefault(u["estacion_id"], {})[u["producto"]] = {
            "producto": u["producto"], "precio": u["precio"], "fecha": u["fecha"]}
    salida = []
    for f in filas:
        e = dict(f)
        e["precios"] = por_est.get(f["id"], {})
        salida.append(e)
    return salida


@router.get("/estaciones/{estacion_id}", response_model=schemas.EstacionDetalle,
            summary="Detalle: precios, competidores confirmados y eventos")
def estacion_detalle(estacion_id: int):
    est = db.uno(queries.ESTACION_POR_ID, (estacion_id,))
    if est is None:
        raise HTTPException(404, "No existe la estacion %d" % estacion_id)

    publica = db.uno('SELECT 1 AS x FROM %s WHERE estacion_id = ? LIMIT 1'
                     % queries.T_PRECIO, (estacion_id,))
    est["publica_precio"] = 1 if publica else 0
    est["nombre"] = est["alias"] or est["razon_social"]
    est["clase"] = "propia" if est["es_propia"] else (
        "directa" if db.uno("SELECT 1 AS x FROM relacion_estacion "
                            "WHERE relacionada_id = ? AND es_competencia = 1 LIMIT 1",
                            (estacion_id,))
        else ("no_directa" if db.uno("SELECT 1 AS x FROM relacion_estacion "
                                     "WHERE relacionada_id = ? LIMIT 1", (estacion_id,))
              else "sin_relacion"))

    fecha = db.uno(queries.ULTIMA_FECHA_ESTACION, (estacion_id,))["fecha"]
    precios = {}
    if fecha:
        precios = {r["producto"]: r["precio"]
                   for r in db.consultar(queries.PRECIOS_EN_FECHA, (estacion_id, fecha))}

    # Competidores confirmados, con su precio EN LA MISMA FECHA que la base.
    #
    # Y solo de los productos que ese par disputa de verdad: si `compite_en`
    # dice GASOLINAS, el diesel del competidor NO se devuelve aunque exista en
    # la base. Ofrecerlo invitaria justo a la comparacion que el operador
    # declaro sin sentido. Es el mismo criterio que aplica v_precio_zona.
    competidores = db.consultar(queries.COMPETIDORES, (estacion_id,))
    for c in competidores:
        if not fecha:
            c["precios"] = {}
            continue
        permitidos = queries.productos_que_compiten(c["compite_en"])
        c["precios"] = {f["producto"]: f["precio"]
                        for f in db.consultar(queries.PRECIOS_EN_FECHA, (c["id"], fecha))
                        if f["producto"] in permitidos}

    # Vecinos NO competidores. Se devuelven para poder pintarlos en amarillo
    # y explicar por que no cuentan, pero NUNCA entran en las metricas: meter
    # a alguien que el operador declaro que no compite en un "precio promedio
    # de competencia" corrompe el numero.
    vecinos = db.consultar(queries.VECINOS, (estacion_id,))
    for v in vecinos:
        v["precios"] = ({f["producto"]: f["precio"]
                         for f in db.consultar(queries.PRECIOS_EN_FECHA, (v["id"], fecha))}
                        if fecha else {})

    eventos = db.consultar(queries.EVENTOS_DE_ESTACION, (estacion_id,))

    aviso = None
    if not fecha:
        aviso = ("Esta estacion no publica precios ante la CNE. Se muestra su "
                 "ubicacion para tenerla presente, pero no hay con que compararla.")
    elif competidores and all(not c["precios"] for c in competidores):
        aviso = ("Ningun competidor confirmado publico precio el %s. "
                 "No se puede comparar en esa fecha." % fecha)

    return {"estacion": est, "fecha_referencia": fecha, "precios": precios,
            "competidores": competidores, "vecinos": vecinos,
            "eventos": eventos, "aviso": aviso}


# ------------------------------------------------------------------ precios

@router.get("/precios/serie", response_model=schemas.Serie,
            summary="Serie historica de una estacion y producto")
def serie(
    estacion_id: int,
    producto: str = Query(..., description="REGULAR, PREMIUM o DIESEL. Acepta 'diesel' y 'diésel'."),
    desde: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    hasta: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    dias: int = Query(30, ge=1, le=2000, description="Se usa solo si no se da 'desde'"),
):
    est = db.uno(queries.ESTACION_POR_ID, (estacion_id,))
    if est is None:
        raise HTTPException(404, "No existe la estacion %d" % estacion_id)
    try:
        prod = queries.normalizar_producto(producto)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    tope = db.consultar(queries.RANGO_FECHAS)[0]["hasta"]
    if not hasta:
        hasta = tope
    if not desde:
        desde = db.uno("SELECT date(?, ?) AS d", (hasta, "-%d day" % dias))["d"]

    puntos = db.consultar(
        'SELECT fecha, precio FROM %s WHERE estacion_id = ? AND producto = ? '
        'AND fecha >= ? AND fecha <= ? ORDER BY fecha' % queries.T_PRECIO,
        (estacion_id, prod, desde, hasta))
    return {"estacion_id": estacion_id,
            "nombre": est["alias"] or est["razon_social"],
            "producto": prod, "desde": desde, "hasta": hasta, "puntos": puntos}


# -------------------------------------------------------------- comparativo

@router.get("/comparativo", tags=["datos"],
            summary="Tabla comparativa de toda la red")
def comparativo(
    dias: int = Query(1, ge=1, le=365,
                      description="1 = solo el ultimo dia. Mas de 1 = promedio de esos dias."),
    hasta: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    solo_directas: bool = Query(False, description="true deja fuera a las vecinas que no compiten"),
):
    """Cada estacion propia en operacion con todas sus relacionadas.

    SIGNO: `diferencial = mi precio - precio del competidor`, igual que en
    la ficha del mapa. Positivo = estoy mas caro (rojo); negativo = estoy
    mas barato (verde). El semaforo se prende a partir de 10 centavos.

    El promedio de cada par usa SOLO los dias en que las dos estaciones
    publicaron. Promediar cada una por su lado y restar despues compararia
    dias distintos.
    """
    rango = db.consultar(queries.RANGO_FECHAS)[0]
    if not rango["hasta"]:
        raise HTTPException(503, "No hay precios cargados.")
    hasta = hasta or rango["hasta"]
    desde = hasta if dias == 1 else db.uno("SELECT date(?, ?) AS d",
                                           (hasta, "-%d day" % (dias - 1)))["d"]

    precios = {}
    for f in db.consultar(queries.PRECIOS_PROMEDIO, (desde, hasta)):
        precios.setdefault(f["estacion_id"], {})[f["producto"]] = round(f["precio"], 2)

    difs = {}
    for f in db.consultar(queries.DIFERENCIAL_PROMEDIO, (desde, hasta)):
        difs.setdefault((f["estacion_id"], f["relacionada_id"]), {})[f["producto"]] = {
            "valor": round(f["diferencial"], 2), "dias": f["dias"]}

    estaciones, indice = [], {}
    for r in db.consultar(queries.RELACIONES_DE_LA_RED):
        base_id = r["estacion_id"]
        if base_id not in indice:
            indice[base_id] = len(estaciones)
            estaciones.append({
                "id": base_id, "nombre": r["base"], "municipio": r["base_municipio"],
                "precios": precios.get(base_id, {}), "relacionadas": []})
        if solo_directas and not r["es_competencia"]:
            continue

        # compite_en manda: un par marcado GASOLINAS no compara diesel.
        permitidos = (queries.productos_que_compiten(r["compite_en"])
                      if r["es_competencia"] else queries.PRODUCTOS)
        d = difs.get((base_id, r["id"]), {})
        estaciones[indice[base_id]]["relacionadas"].append({
            "id": r["id"], "nombre": r["nombre"], "marca": r["marca"],
            "municipio": r["municipio"], "distancia_km": r["distancia_km"],
            "es_competencia": r["es_competencia"], "compite_en": r["compite_en"],
            "en_radio": r["en_radio"], "es_propia": r["es_propia"],
            "productos": list(permitidos),
            "precios": {k: v for k, v in precios.get(r["id"], {}).items() if k in permitidos},
            "diferencial": {k: v for k, v in d.items() if k in permitidos},
        })

    return {"desde": desde, "hasta": hasta, "dias_pedidos": dias,
            "signo": "diferencial = mio - competidor; positivo = estoy mas caro",
            "umbral": 0.10,
            "estaciones": estaciones}
