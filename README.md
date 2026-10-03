# Sistema de Inteligencia Competitiva: Arquitectura de Datos Relacional

Migración integral de la información operativa y de competencia (12 estaciones activas propias y 80 del entorno) desde archivos Excel y CSV dispersos hacia una base de datos relacional formal en SQLite (`red.db`). Este repositorio documenta la estructura de datos que consolida la información y alimenta una aplicación web de monitoreo.

##  Objetivo del Proyecto
Crear una "Single Source of Truth" (Única Fuente de Verdad) robusta y auditable para analizar el entorno competitivo. El sistema cruza precios oficiales de la CNE, costos reales por factura de compra y ventas diarias del sistema interno, permitiendo evaluar el impacto real de la competencia en el volumen de ventas.

##  Arquitectura de Datos y SQL (Mi Trabajo Principal)
El núcleo de este proyecto, el modelado de datos y la lógica de negocio, fue diseñado y programado íntegramente por mí utilizando **SQL** para asegurar la integridad y confiabilidad de la información:
*   **Modelado Relacional:** Diseño de un esquema de 7 tablas transaccionales (`estacion`, `relacion_estacion`, `precio_diario_CNE`, `venta_diaria`, `factura_compra`, `evento`) que rechazan información basura mediante restricciones de integridad.
*   **Ingeniería de Vistas:** Creación de 8 vistas SQL (como `v_competencia` y `v_precio_zona`) para entregar métricas calculadas en tiempo real sin duplicar almacenamiento de datos.
*   **Validación Financiera Cruzada:** Implementación de consultas para cuadrar las compras de combustible contra las ventas del sistema (logrando cuadres con precisión del 1-2%) y detectar diferencias entre precios publicados y reales.
*   **Gestión de Concurrencia:** Resolución de problemas de arquitectura de archivos en entornos sincronizados en la nube (OneDrive), configurando el comportamiento transaccional (`journal_mode = delete`) para evitar bloqueos y corrupción de datos.

## Desarrollo de Interfaz y API (Apoyo de IA)
*Nota de transparencia: Toda la consolidación, limpieza, creación de consultas SQL, modelado y arquitectura de la base de datos fue desarrollada por mí. Para exponer estos datos de manera visual, utilicé la Inteligencia Artificial (Claude) como acelerador de desarrollo para generar la API y el frontend.*

*   **Base de Datos y Lógica (Humano):** SQLite, scripts SQL, DBeaver.
*   **Backend y API (Generado con IA):** Python, FastAPI.
*   **Frontend (Generado con IA):** HTML, interfaz web con mapas interactivos y tablas comparativas.

## 📊 Impacto de Negocio
Se eliminó por completo la dependencia de hojas de cálculo aisladas y propensas a errores. Ahora, la inteligencia competitiva está centralizada: es posible visualizar de manera inmediata si un competidor bajó su precio y medir el efecto exacto en nuestro volumen de ventas, con la certeza de que los datos base son 100% precisos.
