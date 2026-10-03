# Red de estaciones Grupo Treher — base de datos y aplicación

**Carpeta:** `01.Diarios\01.Competencia`
**Base:** `red.db` (SQLite, 9.9 MB)
**Última actualización de este README:** 3 de octubre de 2026

---

## De qué va el proyecto

La idea central no es "una base de estaciones". Es **migrar la información de la operación a bases de datos formales con SQL**, y manejarla, consultarla y tratarla con SQL en lugar de con hojas de cálculo — para que después se pueda conectar con aplicaciones, APIs y cualquier otra cosa que necesite leer esos datos de forma confiable.

Esta carpeta es **el primer caso completo de esa práctica**, de principio a fin:

```
Excel y CSV dispersos
   →  limpieza y validación documentada
   →  esquema relacional con reglas que rechazan basura
   →  red.db
   →  API de solo lectura (FastAPI)
   →  aplicación web con mapa y tablas
```

Sirve de referencia para los siguientes dominios que se migren. Lo que se aprendió aquí —cómo se decide un esquema, cómo se documenta una decisión, cómo se entrega una migración, qué trampas tiene trabajar sobre OneDrive— aplica igual a lo que venga.

El dominio concreto de esta carpeta es **inteligencia competitiva y operación de las estaciones**: quién compite realmente con cada una, a qué precio vende cada quién, cuánto se vendió, cuánto se compró, y qué eventos alteraron la venta sin ser competencia.

---

## Qué hay cargado hoy

| Tabla | Renglones | Cobertura |
|---|---|---|
| `estacion` | **93** | 13 propias (12 en operación) + 80 del entorno |
| `relacion_estacion` | **96** pares dirigidos | 29 confirmados como competencia |
| `precio_diario_CNE` | **61,103** | 2026-01-01 a 2026-09-29, 268 fechas, 82 estaciones |
| `venta_diaria` | **72,251** | 2021-03-20 a 2026-09-28, 2,019 fechas, 13 estaciones |
| `factura_compra` | **8,790** facturas | 2024-01-02 a 2026-09-23, 256,361,925 litros |
| `evento` + `evento_estacion` | **10** + **13** | cierres, desabastos, operativos, aperturas |
| `meta` | **42** claves | las decisiones y defectos de cada fuente, dentro de la base |

Más **8 vistas** y **9 índices**.

### Las tres series de datos y para qué sirve cada una

- **`precio_diario_CNE`** — lo que cada estación **publica ante la CNE**. Es la única fuente que existe para los competidores. Cubre solo 2026.
- **`venta_diaria`** — litros y precio del **sistema de ventas propio**. Cinco años y medio, pero solo de las propias.
- **`factura_compra`** — el **precio de compra real** por factura. Con esto el margen se calcula directo, sin estimar.

Cruzarlas es el punto. Compra contra venta valida las dos fuentes de forma independiente: **cuadran dentro del 1–2% en las doce estaciones activas**. Y el precio publicado contra el del sistema de ventas coincide en **9,288 de 9,417 días comparables**; los 129 que difieren son los que vale revisar.

### Las vistas

| Vista | Qué entrega |
|---|---|
| `v_zona` | todo el entorno de cada propia, compita o no |
| `v_competencia` | solo los 29 pares confirmados |
| `v_precio` | precios de la CNE en plano, con nombres y marca |
| `v_precio_zona` | cada propia contra su competencia, con el diferencial ya calculado |
| `ventas` | ventas con año, mes, día de la semana e importe derivado |
| `compras` | facturas con año, mes e importe derivado |
| `v_boleta_repetida` | boletas facturadas más de una vez, clasificadas |
| `v_evento` | eventos con sus estaciones y el rol de cada una |

Las vistas no guardan datos: son consultas con nombre que leen las tablas en vivo. Ocupan cero bytes.

---

## Qué hay en la carpeta

```
01.Competencia\
├── README.md                    este archivo
├── CONTEXTO.md                  el documento de traspaso, a detalle
├── red.db                       la base
├── PRECIOS COMPETENCIA 2026.csv insumo de precios de la CNE
├── migraciones\                 todo cambio aplicado, con sus respaldos
├── APP\                         la aplicación web (tiene su propio README)
└── Consultas pre realizadas\    (vacía por ahora)
```

**`CONTEXTO.md` es la fuente de verdad del detalle.** Trae el modelo de datos tabla por tabla, los criterios que el operador fijó y que no se deben reinterpretar, los hallazgos de análisis, los defectos conocidos de cada fuente y los pendientes. Este README solo orienta; para trabajar, leer ese.

**`migraciones\`** guarda cada cambio como `AAAA-MM-DD_NN_descripcion`, con el `.sql`, el cargador `.py` cuando aplica, el CSV ya limpio que se usó de insumo, y el respaldo de la base previo a cada carga. Nada se aplica sin dejar rastro reproducible.

---

## Cómo se trabaja con esto

### Consultar
Con **DBeaver**, driver SQLite, sin servidor. El archivo siempre se llama `red.db` y siempre vive en esta ruta: así no se rompe la conexión guardada.

### La aplicación
Doble clic en `APP\run.bat`. Abre en `http://127.0.0.1:8000/` y muestra las 93 estaciones sobre un mapa, con precios, distancias, comparativo y radio ajustable. Lee la base en **solo lectura** y trabaja sobre una copia local fuera de OneDrive, así que no puede dañarla. El detalle está en `APP\README.md` y en la sección 13 del CONTEXTO.

### Cambiar datos
Se entrega siempre como **script SQL de migración** sobre la base existente, nunca como base reconstruida. El procedimiento que funciona en esta carpeta:

```
1. RESPALDO      red.db → copia con fecha, fuera de OneDrive
2. COPIA LOCAL   red.db → work.db
3. MIGRACIÓN     aplicar sobre la copia, nunca sobre el original
4. VERIFICAR     integrity_check + foreign_key_check + conteos
5. LIMPIAR       borrar red.db-journal / -wal sueltos
6. SOBRESCRIBIR  work.db → red.db
7. REVERIFICAR   sobre el archivo final
```

---

## Tres reglas que no se rompen

**No activar `PRAGMA journal_mode=WAL`.** La carpeta es un mount de OneDrive y SQLite no puede crear ahí el archivo `-shm`. Falla con `disk I/O error`, y un journal huérfano puede dejar la base corrupta. Ya pasó una vez. La base se queda en `journal_mode = delete`.

**No escribir en sitio.** SQLite tampoco puede escribir directo sobre `red.db` en esta carpeta. De ahí el procedimiento de copia local de arriba. Si DBeaver da "database is locked", cerrar la conexión en DBeaver — nunca activar WAL para resolverlo.

**Ninguna ruta absoluta dentro de la carpeta sincronizada.** La carpeta vive en SharePoint y se sincroniza entre varias máquinas, cada una con su propia ruta. Una ruta absoluta escrita en una máquina rompe el arranque en la otra. Ya pasó con el `.env` de la aplicación: se resolvió buscando `red.db` por posición relativa, no por ruta.

---

## Criterios del operador

Estas son decisiones de quien conoce las plazas, no supuestos. **No se reinterpretan sin consultarlo.**

- **Una estación cuenta como competencia solo si tiene sentido vial.** El radio es filtro de descubrimiento, nunca criterio. Un vecino a 500 m en cuerpo contrario de autopista no compite; uno a 190 m cruzando carretera sí.
- **El cliente de diésel tampoco se desvía por centavos.** No se usa radio ampliado para diésel.
- **Nadie recorre 12 km por 20 centavos de regular.**
- **Las estaciones del grupo sí compiten entre sí** cuando toca: Combulub y TH están a 1.75 km y están registradas como competencia mutua.
- **Los 29 pares los confirmó el operador** uno por uno. No hay pendientes de validación ahí.
- **Las vecinas que no compiten se muestran pero no entran en ninguna métrica.** Meterlas en un promedio de competencia corrompe el número.

---

## Lo que falta

Lo urgente, en orden:

1. **Resolver las boletas facturadas dos veces.** Ocho duplicados exactos, cinco de ellos del 2026-06-10, más dos boletas del 2026-09-21 facturadas a dos precios distintos. Es requisito antes de costear con capas PEPS: cada factura crea una capa, así que un duplicado mete inventario fantasma.
2. **Definir la capa inicial de inventario** al 2024-01-01, para poder correr PEPS por estación.
3. **Verificar las ventas de TREHER LL de agosto a diciembre de 2024**, que faltan: compró un millón de litros sin ventas registradas.
4. **Recalcular los hallazgos de la sección 9 del CONTEXTO.** Salieron de una tabla mensual que guardaba un mes por año de dos estaciones; con la serie diaria se pueden hacer de verdad.
5. **Terminar la aplicación**: van las etapas 2 a 8 de 12. Siguen gráficas de histórico, filtros, optimización y alertas.
6. **Confirmar Arsona contra Combulub** (¿cuerpo opuesto?), y los tres paros de producto detectados en los datos pero sin confirmar.

La lista completa está en la sección 11 del CONTEXTO.
