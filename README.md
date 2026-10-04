# Inteligencia competitiva con SQL

Proyecto de modelado relacional y análisis de información de precios, ventas y competencia.

## Objetivo

Diseñar una estructura de datos que permita integrar diferentes fuentes y realizar consultas analíticas de forma consistente.

El proyecto utiliza:

- SQLite;
- SQL;
- consultas con CTEs y funciones de ventana;
- vistas para encapsular métricas;
- Python para procesos auxiliares;
- una interfaz web para consultar los resultados.

## Mi contribución

El núcleo del proyecto fue el diseño del modelo de datos y la lógica analítica:

- definición de entidades y relaciones;
- diseño de tablas y restricciones;
- creación de vistas SQL;
- consultas para comparar precios y volumen;
- reglas para determinar comparabilidad entre estaciones;
- validaciones cruzadas entre diferentes fuentes.

La interfaz web y parte del código de API se desarrollaron con apoyo de Inteligencia Artificial. La selección de la arquitectura, las reglas de negocio y la validación de los resultados fueron parte del trabajo analítico.

## Arquitectura

```
Fuentes de datos
      ↓
Limpieza y transformación
      ↓
Base de datos relacional SQLite
      ↓
Vistas y consultas SQL
      ↓
API / interfaz de consulta
```

## Datos

Por motivos de confidencialidad, los archivos de bases de datos, respaldos y datos operativos originales no forman parte de la versión pública del proyecto.

El repositorio conserva la documentación y los componentes técnicos que permiten entender el diseño.

## Tecnologías

SQL · SQLite · Python · FastAPI · HTML/CSS/JavaScript · Leaflet

## Nota

El objetivo de este repositorio es mostrar la metodología de modelado y análisis, no publicar información comercial de la empresa.
