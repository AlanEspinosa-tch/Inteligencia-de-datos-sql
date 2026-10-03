"""SQL centralizado.

Aqui vive todo el SQL de la aplicacion para que las trampas del esquema
esten en un solo lugar y no repartidas por las rutas.

DOS TRAMPAS QUE ESTE MODULO ENCAPSULA:

1. La tabla de precios de la CNE se llama "precio_diario_CNE", NO
   "precio_diario". Lleva mayusculas, asi que SIEMPRE necesita comillas
   dobles en SQL. Usa la constante T_PRECIO; no escribas el nombre a mano.

2. Los literales de producto son 'REGULAR', 'PREMIUM' y 'DIESEL', en
   mayusculas y DIESEL sin acento. Hay un CHECK en las tres tablas que lo
   obliga: cualquier otra grafia devuelve cero renglones en silencio.
"""
from __future__ import annotations

T_PRECIO = '"precio_diario_CNE"'

PRODUCTOS = ("REGULAR", "PREMIUM", "DIESEL")

# Que productos disputa realmente un par de competencia, segun `compite_en`.
# El criterio es del operador: el cliente de diesel no se desvia por unos
# centavos, asi que hay pares que solo compiten en gasolinas. La vista
# v_precio_zona ya lo respeta; esto es lo mismo para el codigo de la API.
PRODUCTOS_QUE_COMPITEN = {
    "AMBOS":     ("REGULAR", "PREMIUM", "DIESEL"),
    "GASOLINAS": ("REGULAR", "PREMIUM"),
    "DIESEL":    ("DIESEL",),
}


def productos_que_compiten(compite_en):
    return PRODUCTOS_QUE_COMPITEN.get(compite_en or "AMBOS", PRODUCTOS)


def normalizar_producto(valor: str) -> str:
    """Acepta lo que mande el frontend y devuelve el literal real.
    'diésel', 'Diesel', 'DIÉSEL' -> 'DIESEL'."""
    if valor is None:
        raise ValueError("producto vacio")
    limpio = (valor.strip().upper()
              .replace("É", "E").replace("Á", "A").replace("Í", "I")
              .replace("Ó", "O").replace("Ú", "U"))
    if limpio not in PRODUCTOS:
        raise ValueError("producto invalido: %r. Validos: %s" % (valor, ", ".join(PRODUCTOS)))
    return limpio


# "Mi red hoy" son 12 estaciones. Filtrar solo por es_propia devuelve 13
# e incluye TREHER LL, que esta cerrada desde abril de 2025.
FILTRO_RED_ACTIVA = "e.es_propia = 1 AND e.activa = 1"

# Todas las estaciones con lo que el mapa necesita para pintar un marcador.
# COALESCE porque 80 estaciones de competencia tienen alias en NULL.
#
# `clase` sale de relacion_estacion.es_competencia y decide el color:
#   propia      -> las 13 del grupo (azul), aunque alguna sea competencia de otra
#   directa     -> es_competencia = 1 frente a AL MENOS UNA propia (rojo)
#   no_directa  -> solo aparece con es_competencia = 0 (amarillo)
#   sin_relacion-> no esta en relacion_estacion (hoy: ninguna)
#
# OJO: esta clase es GLOBAL. Cinco estaciones son directa de una propia y no
# directa de otra (Zapata, Porcla, Servi Boulevard, El Encino y Combulub),
# asi que al seleccionar una estacion el color debe recalcularse RELATIVO a
# ella. Lo hace el frontend con lo que devuelve /api/estaciones/{id}.
ESTACIONES = """
SELECT  e.id,
        e.permiso,
        COALESCE(e.alias, e.razon_social) AS nombre,
        e.alias,
        e.razon_social,
        e.marca,
        e.estado,
        e.municipio,
        e.domicilio,
        e.latitud,
        e.longitud,
        e.es_propia,
        e.activa,
        e.radio_km,
        EXISTS (SELECT 1 FROM {T_PRECIO} p WHERE p.estacion_id = e.id) AS publica_precio,
        CASE
          WHEN e.es_propia = 1 THEN 'propia'
          WHEN EXISTS (SELECT 1 FROM relacion_estacion r
                       WHERE r.relacionada_id = e.id AND r.es_competencia = 1) THEN 'directa'
          WHEN EXISTS (SELECT 1 FROM relacion_estacion r
                       WHERE r.relacionada_id = e.id) THEN 'no_directa'
          ELSE 'sin_relacion'
        END AS clase
FROM    estacion e
ORDER BY e.es_propia DESC, nombre
""".replace("{T_PRECIO}", T_PRECIO)

# Ultimo precio conocido de cada estacion y producto. Es lo que va en el
# popup del mapa. Una estacion sin renglon simplemente no publico ese dia:
# no significa que este cerrada.
ULTIMO_PRECIO = """
SELECT  p.estacion_id,
        p.producto,
        p.precio,
        p.fecha
FROM    {T_PRECIO} p
JOIN   (SELECT estacion_id, producto, MAX(fecha) AS fecha
        FROM   {T_PRECIO}
        GROUP  BY estacion_id, producto) u
        ON u.estacion_id = p.estacion_id
       AND u.producto    = p.producto
       AND u.fecha       = p.fecha
""".replace("{T_PRECIO}", T_PRECIO)

# Serie historica para las graficas.
SERIE_PRECIO = """
SELECT  p.fecha, p.precio
FROM    {T_PRECIO} p
WHERE   p.estacion_id = ? AND p.producto = ?
  AND   p.fecha >= ?
ORDER   BY p.fecha
""".replace("{T_PRECIO}", T_PRECIO)

RANGO_FECHAS = """
SELECT  MIN(fecha) AS desde, MAX(fecha) AS hasta, COUNT(DISTINCT fecha) AS dias
FROM    {T_PRECIO}
""".replace("{T_PRECIO}", T_PRECIO)


# ---------------------------------------------------------------------------
# ETAPA 4 — consultas de datos
# ---------------------------------------------------------------------------

# La marca vacia viene en DOS formas: 7 estaciones con NULL y una con el
# texto literal "Sin Identificar". Se juntan en un solo cubo para que el
# catalogo y el filtro cuenten lo mismo. En la base siguen separadas: ver
# el pendiente 11 del CONTEXTO.
CATALOGO_MARCAS = """
SELECT  CASE
          WHEN marca IS NULL OR TRIM(marca) = ''      THEN 'Sin identificar'
          WHEN LOWER(TRIM(marca)) = 'sin identificar' THEN 'Sin identificar'
          ELSE TRIM(marca)
        END AS marca,
        COUNT(*) AS estaciones
FROM    estacion
GROUP   BY 1
ORDER   BY estaciones DESC, marca
"""

CATALOGO_UBICACION = """
SELECT  estado, municipio, COUNT(*) AS estaciones
FROM    estacion
GROUP   BY estado, municipio
ORDER   BY estado, municipio
"""

# Detalle de una estacion.
ESTACION_POR_ID = """
SELECT  e.id, e.permiso,
        COALESCE(e.alias, e.razon_social) AS nombre,
        e.alias, e.razon_social, e.razon_social_previa, e.marca,
        e.tipo_permiso, e.anio_permiso,
        e.estado, e.municipio, e.cve_geo, e.domicilio,
        e.latitud, e.longitud,
        e.terminal, e.km_terminal,
        e.es_propia, e.activa, e.radio_km
FROM    estacion e
WHERE   e.id = ?
"""

# Precios de una estacion en una fecha exacta.
PRECIOS_EN_FECHA = """
SELECT  producto, precio
FROM    {T_PRECIO}
WHERE   estacion_id = ? AND fecha = ?
""".replace("{T_PRECIO}", T_PRECIO)

# Ultimo dia en que una estacion publico algo.
ULTIMA_FECHA_ESTACION = """
SELECT  MAX(fecha) AS fecha FROM {T_PRECIO} WHERE estacion_id = ?
""".replace("{T_PRECIO}", T_PRECIO)

# Competidores CONFIRMADOS de una estacion. Dirigido: solo los pares que
# salen de esta estacion. Nunca simetrizar.
COMPETIDORES = """
SELECT  r.relacionada_id            AS id,
        COALESCE(c.alias, c.razon_social) AS nombre,
        c.permiso, c.marca, c.municipio, c.estado, c.domicilio,
        c.latitud, c.longitud, c.es_propia,
        r.distancia_km, r.compite_en, r.mismo_sentido, r.en_radio, r.motivo
FROM    relacion_estacion r
JOIN    estacion c ON c.id = r.relacionada_id
WHERE   r.estacion_id = ? AND r.es_competencia = 1
ORDER   BY r.distancia_km
"""

# Vecinos registrados que NO son competencia (es_competencia = 0). Estan en
# relacion_estacion porque el radio de descubrimiento los encontro, pero el
# operador determino que no compiten: cuerpo contrario de autopista, sin
# retorno a tiro, o demasiado lejos para el producto.
VECINOS = """
SELECT  r.relacionada_id            AS id,
        COALESCE(c.alias, c.razon_social) AS nombre,
        c.permiso, c.marca, c.municipio, c.estado, c.domicilio,
        c.latitud, c.longitud, c.es_propia,
        r.distancia_km, r.en_radio, r.mismo_sentido, r.motivo
FROM    relacion_estacion r
JOIN    estacion c ON c.id = r.relacionada_id
WHERE   r.estacion_id = ? AND r.es_competencia = 0
ORDER   BY r.distancia_km
"""

# Todas las estaciones con coordenadas, para el calculo de radio variable.
ESTACIONES_GEO = """
SELECT  e.id, COALESCE(e.alias, e.razon_social) AS nombre,
        e.marca, e.municipio, e.estado, e.latitud, e.longitud,
        e.es_propia, e.activa
FROM    estacion e
"""

# OJO: no usar v_evento para esto. Esa vista expone `alias`, que es NULL en
# las 80 estaciones de competencia, asi que un JOIN por alias las pierde.
# Aqui se va directo a las tablas y se liga por id.
EVENTOS_DE_ESTACION = """
SELECT  ev.id AS evento_id, ev.tipo, ev.titulo, ev.descripcion,
        ev.fecha_inicio, ev.fecha_fin, ev.fecha_estimada, ev.fuente,
        x.rol, x.efecto
FROM    evento_estacion x
JOIN    evento ev ON ev.id = x.evento_id
WHERE   x.estacion_id = ?
ORDER   BY ev.fecha_inicio DESC, ev.id
"""


# ---------------------------------------------------------------------------
# TABLA COMPARATIVA
# ---------------------------------------------------------------------------
#
# CONVENCION DE SIGNO, la misma en toda la aplicacion:
#
#     diferencial = mi precio  -  precio del competidor
#
# Positivo = estoy mas caro (rojo). Negativo = estoy mas barato (verde).
# El semaforo se prende a partir de 10 centavos, por instruccion del
# operador: por debajo de eso la diferencia no mueve al cliente.
#
# Su Excel usa el signo inverso (competidor - mio). Se eligio mantener una
# sola convencion en la aplicacion en vez de arrastrar las dos.

# Precio promedio por estacion y producto dentro de un rango de fechas.
# Con rango de un solo dia devuelve el precio de ese dia.
PRECIOS_PROMEDIO = """
SELECT  estacion_id, producto,
        AVG(precio) AS precio,
        COUNT(*)    AS dias
FROM    {T_PRECIO}
WHERE   fecha BETWEEN ? AND ?
GROUP   BY estacion_id, producto
""".replace("{T_PRECIO}", T_PRECIO)

# Diferencial promedio por par y producto.
#
# El JOIN por fecha es lo importante: promedia SOLO los dias en que las dos
# estaciones publicaron. Promediar cada una por su lado y restar despues
# compararia dias distintos, que es justo lo que no se debe hacer.
DIFERENCIAL_PROMEDIO = """
SELECT  r.estacion_id,
        r.relacionada_id,
        pp.producto,
        AVG(pp.precio - pc.precio) AS diferencial,
        COUNT(*)                   AS dias
FROM    relacion_estacion r
JOIN    {T_PRECIO} pp ON pp.estacion_id = r.estacion_id
                     AND pp.fecha BETWEEN ? AND ?
JOIN    {T_PRECIO} pc ON pc.estacion_id = r.relacionada_id
                     AND pc.fecha    = pp.fecha
                     AND pc.producto = pp.producto
GROUP   BY r.estacion_id, r.relacionada_id, pp.producto
""".replace("{T_PRECIO}", T_PRECIO)

# Todas las relaciones de las propias en operacion, directas y vecinas.
RELACIONES_DE_LA_RED = """
SELECT  r.estacion_id,
        COALESCE(b.alias, b.razon_social)  AS base,
        b.municipio                        AS base_municipio,
        r.relacionada_id                   AS id,
        COALESCE(c.alias, c.razon_social)  AS nombre,
        c.marca, c.municipio,
        r.distancia_km, r.es_competencia, r.compite_en, r.en_radio,
        c.es_propia
FROM    relacion_estacion r
JOIN    estacion b ON b.id = r.estacion_id
JOIN    estacion c ON c.id = r.relacionada_id
WHERE   b.es_propia = 1 AND b.activa = 1
ORDER   BY base, r.es_competencia DESC, r.distancia_km
"""
