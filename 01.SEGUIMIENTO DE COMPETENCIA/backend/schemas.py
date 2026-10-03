"""Formas de respuesta de la API.

Sirven para dos cosas: que /docs muestre de verdad que devuelve cada ruta,
y que un campo que desaparezca de la base reviente aqui y no en el mapa.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Precio(BaseModel):
    producto: str
    precio: float
    fecha: str = Field(description="Dia en que se publico ese precio")


class Estacion(BaseModel):
    id: int
    permiso: str
    nombre: str = Field(description="alias, o razon social cuando no hay alias")
    alias: Optional[str] = None
    razon_social: str
    marca: Optional[str] = None
    estado: Optional[str] = None
    municipio: Optional[str] = None
    domicilio: Optional[str] = None
    latitud: float
    longitud: float
    es_propia: int
    activa: int
    radio_km: Optional[float] = None
    publica_precio: int = Field(description="0 = no reporta a la CNE; se ubica pero sin precio")
    clase: str = Field(
        description="propia | directa | no_directa | sin_relacion. Sale de "
                    "relacion_estacion.es_competencia y decide el color del marcador. "
                    "Es GLOBAL: cinco estaciones son directa de una propia y no "
                    "directa de otra, asi que al seleccionar una estacion hay que "
                    "recalcular el color relativo a ella.")


class EstacionEnMapa(Estacion):
    precios: Dict[str, Precio] = Field(default_factory=dict,
                                       description="Ultimo precio conocido por producto")


class Competidor(BaseModel):
    id: int
    nombre: str
    permiso: str
    marca: Optional[str] = None
    municipio: Optional[str] = None
    estado: Optional[str] = None
    domicilio: Optional[str] = None
    latitud: float
    longitud: float
    es_propia: int
    distancia_km: float
    compite_en: Optional[str] = None
    mismo_sentido: Optional[int] = None
    en_radio: int
    motivo: Optional[str] = None
    precios: Dict[str, float] = Field(default_factory=dict,
                                      description="Precio en la fecha de referencia")


class Vecino(BaseModel):
    """Registrado en relacion_estacion pero con es_competencia = 0: el radio
    lo encontro y el operador determino que NO compite."""
    id: int
    nombre: str
    permiso: str
    marca: Optional[str] = None
    municipio: Optional[str] = None
    estado: Optional[str] = None
    domicilio: Optional[str] = None
    latitud: float
    longitud: float
    es_propia: int
    distancia_km: float
    en_radio: int
    mismo_sentido: Optional[int] = None
    motivo: Optional[str] = None
    precios: Dict[str, float] = Field(default_factory=dict)


class Evento(BaseModel):
    evento_id: int
    tipo: str
    titulo: str
    descripcion: Optional[str] = None
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    fecha_estimada: int
    fuente: Optional[str] = None
    rol: str
    efecto: Optional[str] = None


class EstacionDetalle(BaseModel):
    estacion: Estacion
    fecha_referencia: Optional[str] = Field(
        None, description="Ultimo dia con precio de esta estacion. NULL si nunca publico.")
    precios: Dict[str, float] = Field(default_factory=dict)
    competidores: List[Competidor] = Field(
        default_factory=list, description="es_competencia = 1. Los unicos que entran en las metricas.")
    vecinos: List[Vecino] = Field(
        default_factory=list, description="es_competencia = 0. Se muestran, pero NO se comparan.")
    eventos: List[Evento] = Field(default_factory=list)
    aviso: Optional[str] = None


class PuntoSerie(BaseModel):
    fecha: str
    precio: float


class Serie(BaseModel):
    estacion_id: int
    nombre: str
    producto: str
    desde: str
    hasta: str
    puntos: List[PuntoSerie]


class Catalogos(BaseModel):
    productos: List[str]
    marcas: List[dict]
    estados: List[str]
    municipios: List[dict]
    precios_desde: Optional[str] = None
    precios_hasta: Optional[str] = None
    dias_con_precio: int = 0
    total_estaciones: int = 0
    propias_activas: int = 0
    sin_precio: int = 0
