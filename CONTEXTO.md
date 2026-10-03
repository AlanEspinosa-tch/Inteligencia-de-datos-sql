# Contexto del proyecto — Red de estaciones Grupo Treher

Documento de traspaso. Pégalo al conocimiento del proyecto de Claude o ábrelo al inicio de una conversación nueva para retomar sin repetir nada.

**Última actualización:** 29 de septiembre de 2026 — se verificó el esquema real contra `red.db`, se corrigieron cinco entradas de `meta` y cinco marcas de la sección 6, y la aplicación web llegó a la etapa 8, con mapa, radio variable y tabla comparativa. El último cambio de datos sigue siendo el del 25 de septiembre.

---

## 1. Carpeta de trabajo

El archivo se llama **`red.db`** y vive en la carpeta `01.Competencia`. SQLite, se abre con DBeaver (driver SQLite, sin servidor).

**Dos máquinas, dos rutas.** Las dos están en uso y sincronizan la misma biblioteca, pero OneDrive le puso nombre distinto a la carpeta en cada una:

| Máquina | Ruta |
|---|---|
| `preci` | `C:\Users\preci\TRANSPORTES C MORALES C SA de CV\Tesorería y Finanzas Treher - Finanzas Grupo Treher\01.Diarios\01.Competencia` |
| `soporte` (usuario `TREHER`) | `C:\Users\TREHER\TRANSPORTES C MORALES C SA de CV\Finanzas Treher - Finanzas Grupo Treher\01.Diarios\01.Competencia` |

Nunca escribas la ruta a mano en el código. La aplicación la toma de `RED_DB_PATH` en su archivo `.env`, que es distinto en cada máquina.

**Regla que evita romper la conexión de DBeaver:** el archivo se llama siempre `red.db` y va siempre en esa carpeta. Cuando haya cambios, se sobrescribe; no se crean archivos con nombre nuevo. Los cambios se entregan como **scripts SQL de migración** sobre el `red.db` existente, no como base reconstruida.

**Cómo conectar la carpeta para que Claude la lea.** `device_request_folder_access` **falla con estas rutas**: el acento de "Tesorería" hace que el diálogo de aprobación remoto la rechace, y la carpeta padre tampoco se puede conceder. No insistir con variantes. Hay que conectarla a mano desde el botón **"+" → "Add folder"** de la app de escritorio, eligiendo `01.Competencia`. Queda montada en `$HOME/mnt/01.Competencia/`.

**Trampa de OneDrive, descubierta el 24-sep:** la carpeta es un mount de OneDrive y **SQLite no puede escribir en sitio sobre `red.db`**: falla con `disk I/O error` al crear el journal. El procedimiento que sí funciona:

1. Censar objetos y conteos antes de tocar nada.
2. Respaldar `red.db` con fecha, **dentro de `migraciones\`** para que sobreviva a la sesión.
3. Copiar `red.db` a disco local.
4. Aplicar la migración sobre la copia, nunca sobre el original.
5. Verificar: `integrity_check`, `foreign_key_check` y el censo contra el paso 1.
6. Borrar cualquier `red.db-journal` / `red.db-wal` suelto en la carpeta.
7. Sobrescribir `red.db` con la copia.
8. Reverificar sobre el archivo final.

El paso 6 no es opcional. Un journal huérfano dispara un rollback que **revierte la copia recién hecha y puede dejar el archivo corrupto**; pasó el 24-sep y se recuperó del respaldo.

**Y nunca activar `PRAGMA journal_mode=WAL`** mientras la base viva en OneDrive: WAL necesita un archivo `-shm` que el mount no soporta. La base se queda en `journal_mode = delete`, confirmado el 29-sep.

---

## 2. Qué es esto

Base de inteligencia competitiva para 12 estaciones de servicio propias en Hidalgo, Estado de México y Querétaro. Sirve para: saber quién compite realmente con cada estación, registrar los eventos que alteran la venta sin ser competencia, y medir efectos como la apertura de un entrante.

Desde el 29-sep tiene encima una **aplicación web** en construcción. Ver sección 13.

---

## 3. Modelo de datos

**Siete tablas más `meta`, ocho en total, y ocho vistas.** Verificado contra el archivo el 29-sep-2026. Se llegó aquí después de descartar un modelo de 12 tablas (sobrenormalizado para este volumen) y uno de una sola tabla con self-id (no representaba pares dirigidos).

El diseño original fueron cinco tablas más `meta`. Las cargas del 25-sep sumaron tres y quitaron `venta_mensual`. **Cualquier script que verifique "las 6 tablas" está desactualizado.** Inventario vigente:

| # | Tabla | Renglones |
|---|---|---|
| 1 | `estacion` | 93 |
| 2 | `relacion_estacion` | 96 |
| 3 | `precio_diario_CNE` | 59,938 |
| 4 | `venta_diaria` | 72,071 |
| 5 | `factura_compra` | 8,790 |
| 6 | `evento` | 10 |
| 7 | `evento_estacion` | 13 |
| 8 | `meta` | 42 |

Vistas (8): `v_zona`, `v_competencia`, `v_evento`, `v_precio`, `v_precio_zona`, `ventas`, `compras`, `v_boleta_repetida`. Índices: 9. Triggers: ninguno.

En vez de fijar el número en un script, comparar el censo antes y después de cada migración:

```sql
SELECT type, name FROM sqlite_master
WHERE  name NOT LIKE 'sqlite_%' ORDER BY type, name;
```

### Dos trampas de escritura de SQL

**1. La tabla de precios se llama `precio_diario_CNE`, no `precio_diario`.** Lleva mayúsculas, así que **siempre exige comillas dobles**:

```sql
SELECT * FROM "precio_diario_CNE" WHERE fecha = '2026-09-24';
```

Las vistas `v_precio` y `v_precio_zona` ya la referencian bien. Las consultas que la nombran directo tienen que entrecomillarla o fallan.

**2. Los literales de producto son `'REGULAR'`, `'PREMIUM'` y `'DIESEL'`** — mayúsculas, y DIESEL **sin acento**. Hay un `CHECK` en las tres tablas que lo obliga. Cualquier otra grafía devuelve cero renglones en silencio, que es la peor forma de fallar.

### `estacion`
`id`, `permiso` (UNIQUE, CRE `PL/...` o CNE `CNE/PL/...`), `alias`, `razon_social`, `razon_social_previa`, `marca`, `tipo_permiso` (ES/ESA), `anio_permiso`, `estado`, `municipio`, `cve_geo`, `domicilio`, `latitud`, `longitud`, `terminal`, `km_terminal`, `es_propia`, `radio_km`, `activa`.

**93 renglones**: 13 propias más 80 del entorno.

`latitud` y `longitud` son `NOT NULL` con `CHECK` de rango. **Las 93 tienen coordenadas válidas**, verificado el 29-sep: ninguna nula ni en cero. El mapa puede pintarlas todas.

**`activa`**: 1 = en operación, 0 = cerrada. Solo TREHER LL está en 0.

- **"Mi red hoy"** es `es_propia = 1 AND activa = 1` → **12** estaciones.
- **"Mi red histórica"** es `es_propia = 1` → **13**.

**Cuidado:** las consultas que solo filtran `es_propia = 1` devuelven 13 e incluyen una estación cerrada.

**Dos huecos que afectan a cualquier interfaz** (hallazgo del 29-sep):

- **80 estaciones tienen `alias` en NULL** — todas las de competencia. Las vistas hacen `COALESCE(alias, razon_social)`, así que degradan a la razón social: los popups dirán `GPDC ESTACIONES DE SERVICIO SA DE CV` en mayúsculas. Poblar `alias` es cosmético pero mejora mucho la lectura del mapa. Ver pendiente 10.
- **Marca vacía en 8 estaciones, de dos formas distintas**: 7 en `NULL` y 1 con el texto literal `"Sin Identificar"`. Un filtro de marca que no trate los dos casos pierde registros.

### `relacion_estacion`
Pares **dirigidos**. 96 renglones, 29 marcados como competencia.

`estacion_id`, `relacionada_id`, `distancia_km`, `en_radio`, `es_competencia`, `compite_en` (AMBOS / GASOLINAS / DIESEL), `mismo_sentido` (1/0/NULL), `motivo`.

Es dirigida porque que A compita con B no implica lo inverso: en autopista con cuerpos opuestos, el flujo solo va en un sentido. **Nunca simetrizar esta tabla** en una consulta ni en el código.

### `venta_diaria`  *(25-sep-2026; reemplazó a `venta_mensual`)*
`estacion_id`, `fecha`, `producto`, `litros`, `precio_venta`. PK `(estacion_id, fecha, producto)`, `WITHOUT ROWID`, índice por `(fecha, producto)`.

**72,071 renglones, del 2021-03-20 al 2026-09-24**, 2,015 fechas, 13 estaciones. Origen: archivo de ventas del operador, formato ancho con litros y precio por producto; la fecha venía como serial de Excel (época 1899-12-30).

`litros` y `precio_venta` **son NULLABLE a propósito.** El origen usaba tres formas de decir "no se ofreció el producto ese día": celda vacía, `0` y casi-cero (`1E-10`). Las tres se cargaron como NULL por instrucción del operador, para que no sesguen promedios — `AVG` y `SUM` ignoran NULL solos. 766 renglones se omitieron porque litros y precio quedaban ambos nulos; 40 quedaron con litros NULL y precio real, que son días de paro con precio publicado.

Los precios se redondearon a 2 decimales. De 87 valores con más de dos decimales, **77 eran marcadores casi-cero** y solo 10 eran precios reales, probablemente promedios de días con cambio de precio a media jornada.

**`precio_venta` no es lo mismo que `precio_diario_CNE.precio`.** Uno es el precio del sistema de ventas y existe solo para las propias, 2021–2026; el otro es lo publicado ante la CNE y existe para las 82, solo 2026. Compararlos es el punto.

**El importe no se guarda.** En el origen era exactamente `litros × precio`: verificado en 72,156 comparaciones, cero desviaciones mayores a un centavo. Por lo tanto **no es dinero de caja sino una multiplicación de hoja de cálculo, y no permite detectar descuentos.** La vista `ventas` lo deriva como `importe_calculado`.

### `venta_mensual` — ELIMINADA el 25-sep-2026
Sus cifras eran de **un mes específico por año**, no promedios, y solo cubrían TREHER T y TH. `venta_diaria` la reemplaza con cinco años y medio de las 13 estaciones. Con ella se fueron las vistas `v_venta` y `v_evolucion`.

### `evento` y `evento_estacion`
Lo que mueve la venta sin ser competencia. `tipo` (OPERATIVO_FEDERAL, DESABASTO_COMPETENCIA, ENTRANTE, CLAUSURA, OBRA_VIAL, OTRO), `titulo`, `descripcion`, `fecha_inicio`, `fecha_fin`, `fecha_estimada`, `fuente`. La liga lleva `rol` (CAUSANTE / AFECTADA / BENEFICIADA) y `efecto`.

### `precio_diario_CNE`  *(25-sep-2026)*
`estacion_id`, `fecha`, `producto`, `precio`. PK `(estacion_id, fecha, producto)`, `WITHOUT ROWID`, índice por `(fecha, producto)`.

**59,938 renglones, del 2026-01-01 al 2026-09-24**, 263 fechas, 82 estaciones. Origen: `PRECIOS COMPETENCIA 2026.csv`, aportado por el operador. Venía en formato ancho (una columna por producto) y se cargó en largo.

Reglas de limpieza aplicadas, todas verificadas contra el archivo:

- **El cero significa "sin dato", no un precio.** El CSV no usa celdas vacías. Se omitieron 3,928 ceros: 957 en regular, 297 en premium, 2,674 en diésel. No hubo ningún otro valor fuera del rango 10–45.
- **163 pares (permiso, fecha) duplicados**, en 28/03 y 24/05. Se comprobó uno por uno: los 163 con precios idénticos, cero conflictos. La PK los colapsa.
- **Faltan 4 fechas completas**: 3 y 23 de mayo, 4 de agosto, 3 de septiembre. Nadie reportó esos días; es la captura, no las estaciones.
- Atlanta (PL/11248), Galigas (PL/11271) y Tepogas (PL/18961) **nunca reportan regular** pero sí premium y diésel los 263 días. Coincide con el feed público de la CNE.

Que falte un renglón significa que no se publicó precio ese día, **no** que la estación estuviera cerrada.

**No hay hora, solo fecha.** Ninguna tabla guarda hora de actualización. Decisión del operador el 29-sep: la interfaz omite la hora en vez de inventarla.

**La tabla se sigue poblando.** El archivo llega al 24-sep-2026 y se recarga periódicamente; el cargador es idempotente. Cualquier consumidor tiene que tolerar que la última fecha se mueva.

### `factura_compra`  *(25-sep-2026)*
`num_factura` (PK), `estacion_id`, `fecha_bol`, `producto`, `litros`, `precio`, `bol`.

**8,790 facturas, del 2024-01-02 al 2026-09-23**, 899 fechas, 13 estaciones, **256,361,925 litros**. Origen: `Facturas.csv` del operador.

`num_factura` es único en los 8,790 renglones, así que sirve de llave primaria natural. Va como TEXT por si el folio gana un prefijo. `fecha_bol` se llama así a propósito: es la fecha de la **boleta**, no la de facturación — el origen no trae esa última.

El producto venía por código (1=diésel, 2=premium, 3=regular) y también por texto; concuerdan en el 100% de los renglones, pero el texto traía mayúsculas inconsistentes, así que se derivó del código.

**El precio NO se redondeó.** Trae de 3 a 8 decimales y esa precisión es real. Es lo contrario de `venta_diaria.precio_venta`, que sí se redondeó a 2.

**Lo que este archivo NO trae:** proveedor, IVA, IEPS ni el total facturado. Es el detalle de compra de combustible, **no cuentas por pagar**. Para conciliar contra contabilidad hace falta el importe con impuestos. El importe se deriva como `litros × precio`.

**Costeo PEPS.** El operador costea con capas estilo PEPS por estación. El orden determinista de entrada es `(fecha_bol, num_factura)`: el folio es secuencial en todo el archivo y desempata dos pipas del mismo día. El índice `ix_factura_peps` está hecho para eso. Falta definir una **capa inicial**: las compras arrancan el 2024-01-02 y lo que había en los tanques el 1 de enero tiene costo desconocido.

### `meta`
42 claves con la documentación que vive dentro de la base. **Corregida el 29-sep** (migración `2026-09-29_01`): cinco entradas habían quedado desfasadas tras las cargas del 25-sep. Ver sección 12.

### Vistas
- **`v_precio`** — plana: fecha, producto, estación, marca, municipio, estado, es_propia, precio. 59,938 renglones.
- **`v_precio_zona`** — cada propia contra cada competidor confirmado, mismo día y producto, con `diferencial = precio_base − precio_competidor`. Positivo significa que la propia está **más cara**. Respeta `compite_en`: el par TREHER–Zapata, marcado GASOLINAS, no aparece en diésel. 18,934 renglones.
- **`v_zona`** — los 96 pares con los datos de la estación relacionada. `v_competencia` es `v_zona` filtrada a `es_competencia = 1`: 29 renglones.
- **`v_evento`** — 13 renglones, evento cruzado con estación.
- **`ventas`** — sobre `venta_diaria`: agrega `anio`, `mes`, `mes_letra`, `dia_semana`, el alias de la estación, su bandera `activa` e `importe_calculado`. 72,071 renglones. **No lleva prefijo `v_`** por decisión del operador, así que en DBeaver parece tabla hasta que se ve en qué carpeta está. Lo mismo con `compras`.
- **`compras`** — sobre `factura_compra`, con `anio`, `mes`, alias, `activa` e `importe_calculado`. 8,790 renglones.
- **`v_boleta_repetida`** — las boletas facturadas más de una vez, clasificadas en `DUPLICADA_EXACTA`, `PRECIO_DISTINTO` y `CARGA_PARTIDA`. 38 renglones sobre 18 boletas.

**`v_venta` y `v_evolucion` ya no existen**: se fueron con `venta_mensual`. Si hace falta evolución año contra año, se arma sobre `ventas` (ver sección 12).

---

## 4. Criterios acordados

Estas son decisiones del operador, no supuestos. Respetarlas.

**Una estación cuenta como competencia solo si tiene sentido vial.** El radio es filtro de descubrimiento, nunca criterio. Un vecino a 500 m en cuerpo contrario de autopista no compite; uno a 190 m cruzando carretera con cruce sí.

**El cliente de diésel tampoco se desvía por unos centavos.** No se usa radio ampliado para diésel. Esto sacó a Arsona (PL/24156) y Combulub del set de TREHER, donde solo entraban por diésel a 3.0 y 3.5 km.

**Nadie recorre 12 km por 20 centavos de regular.** Por eso Archundia está en la base pero fuera del set competitivo de Toremex: aparece solo como causante de un evento.

**Radio por estación, no uniforme:** 4 km para TREHER T, TH, las dos AILES, AVE FENIX y AURORA; 3 km para QL y TEOLOYUCAN; 2 km para COMBULUB, HUEHUETOCA, IXTAZACUALA y TOREMEX.

**Estaciones del grupo sí compiten entre sí.** COMBULUB y TH están a 1.75 km y quedan registradas como competencia mutua.

**Los 29 pares de competencia los confirmó el operador**, que conoce las doce plazas. No hay pendientes de validación.

**Una estación que no publica precio se muestra igual en el mapa** (decisión del 29-sep), marcada como "sin precio publicado". Se ubica para tener presente que existe, aunque no haya con qué compararla.

---

## 5. Las propias (12 en operación, 13 históricas)

| id | Alias | Permiso | Razón social | Plaza | Radio |
|---|---|---|---|---|---|
| 1 | TREHER T | PL/2027/EXP/ES/2015 | Grupo Treher | Tizayuca, Hgo. | 4 km |
| 2 | TH | PL/1731/EXP/ES/2015 | Grupo Gasolinero TH | Tizayuca, Hgo. | 4 km |
| 3 | AILES TIERRA BLANCA | PL/12856/EXP/ES/2015 | Super Servicio Ailes | Cuautitlán, Méx. | 4 km |
| 4 | AILES TEPOJACO | PL/19215/EXP/ES/2016 | Super Servicio Ailes | Cuautitlán Izcalli, Méx. | 4 km |
| 5 | AVE FENIX | PL/9330/EXP/ES/2015 | Abastecedora Ave Fénix | Querétaro, Qro. | 4 km |
| 6 | AURORA | PL/3086/EXP/ES/2015 | Super Servicio Aurora | Cuautitlán Izcalli, Méx. | 4 km |
| 7 | COMBULUB | PL/1767/EXP/ES/2015 | Combulub El Pilar | Tizayuca, Hgo. | 2 km |
| 8 | HUEHUETOCA | PL/2966/EXP/ES/2015 | Servicio Huehuetoca | Huehuetoca, Méx. | 2 km |
| 9 | IXTAZACUALA | PL/1900/EXP/ES/2015 | Servicio Ixtazacuala | Atitalaquia, Hgo. | 2 km |
| 10 | QL | PL/2209/EXP/ES/2015 | Grupo Q L | Tepotzotlán, Méx. | 3 km |
| 11 | TEOLOYUCAN | PL/2616/EXP/ES/2015 | Gasolinera Teoloyucan | Tepotzotlán, Méx. | 3 km |
| 12 | TOREMEX | PL/5210/EXP/ES/2015 | Grupo Toremex | Jilotepec, Méx. | 2 km |
| 93 | **TREHER LL** *(cerrada)* | PL/19259/EXP/ES/2016 | Grupo Treher | Nextlalpan, Méx. | — |

Las doce activas publican precio los 263 días de 2026, con 789 renglones cada una (263 × 3 productos). **TREHER LL no tiene ningún precio de la CNE.**

**TREHER LL está cerrada** (`activa = 0`). Operó del **2025-01-01 al 2025-04-28**, 117 días, 351 renglones de venta, unos 491,000 litros. Se conserva para no perder esos datos: sin la estación, la llave foránea no admitiría sus ventas, y los totales de red de 2025 quedarían cortos sin explicación. No tiene relaciones de competencia.

El padrón la ubica en **Nextlalpan** (`cve_geo` 15059) por localidad INEGI más cercana, pero su domicilio dice **Zumpango**. Se cargó Nextlalpan para que municipio y clave no queden en contradicción. "LL" parece venir de San Pedro la Laguna, su domicilio.

Cuidado: **AILES TEPOJACO está en Cuautitlán Izcalli** (Av. San Pedro Tepojaco), no en el Tepojaco de Tizayuca donde está TH. Son lugares distintos.

---

## 6. Set competitivo confirmado

| Propia | Competidor | Permiso | Marca | km | Producto |
|---|---|---|---|---|---|
| TREHER T | Operadora ACE Hidrocarburos | CNE/PL/386/EXP/ES/2025 | Pemex | 0.19 | ambos |
| TREHER T | Estación El Cid | PL/1689/EXP/ES/2015 | Total | 0.84 | ambos |
| TREHER T | Energéticos Zapata | PL/24614/EXP/ES/2022 | Pemex | 2.57 | solo gasolinas |
| TH | Felipe Simón Olvera Castelán | PL/24553/EXP/ES/2022 | — | 1.17 | ambos |
| TH | Servicio Cúpula | PL/6187/EXP/ES/2015 | Servifácil | 1.43 | ambos |
| TH | Combulub (propia) | PL/1767/EXP/ES/2015 | Valero | 1.75 | ambos |
| AILES TIERRA BLANCA | Servicio Moderno Ferman | PL/26174/EXP/ES/2025 | Sin Identificar | 0.88 | ambos |
| AILES TIERRA BLANCA | Operadora Intergasolineras | PL/10078/EXP/ES/2015 | Pemex | 1.78 | ambos |
| AILES TEPOJACO | Servicio San Francisco Tepojaco | PL/1417/EXP/ES/2015 | G500 | 0.50 | ambos |
| AVE FENIX | Servicio Sujuxi | PL/20289/EXP/ES/2017 | Pemex | 0.30 | ambos |
| AVE FENIX | Servicio Petro Junípero | PL/22827/EXP/ES/2019 | Petro Figues | 0.97 | ambos |
| AVE FENIX | Oleum | PL/25437/EXP/ES/2023 | G500 | 1.31 | ambos |
| AURORA | Operadora de Miniestaciones Combuserv | PL/11327/EXP/ES/2015 | Pemex | 0.86 | ambos |
| AURORA | Hidrosina Plus | PL/8519/EXP/ES/2015 | Hidrosina | 1.90 | ambos |
| AURORA | Autoservicio Galigas | PL/11271/EXP/ES/2015 | Pemex | 2.06 | ambos |
| AURORA | Servicio El Molino | PL/6939/EXP/ES/2015 | G500 | 2.34 | ambos |
| COMBULUB | Servicio Cúpula | PL/6187/EXP/ES/2015 | Servifácil | 1.39 | ambos |
| COMBULUB | TH (propia) | PL/1731/EXP/ES/2015 | Valero | 1.75 | ambos |
| HUEHUETOCA | NR Combustibles | PL/2712/EXP/ES/2015 | Pemex | 0.40 | ambos |
| HUEHUETOCA | Estación de Servicio Jorobas | PL/6407/EXP/ES/2015 | Valero | 0.78 | ambos |
| HUEHUETOCA | Super Servicios San Juan | PL/4631/EXP/ES/2015 | Pemex | 1.02 | ambos |
| IXTAZACUALA | GPDC Estaciones de Servicio | PL/7069/EXP/ES/2015 | — | 1.45 | ambos |
| IXTAZACUALA | Servicio Fácil del Sureste | PL/1446/EXP/ES/2015 | Servifácil | 4.68 * | ambos |
| IXTAZACUALA | Parán Megaservicios | PL/9370/EXP/ES/2015 | Chevron | 6.46 * | ambos |
| QL | Servicio El Encino | PL/4840/EXP/ES/2015 | Pemex | 1.32 | ambos |
| QL | Porcla | PL/4394/EXP/ES/2015 | Pemex | 2.23 | ambos |
| TEOLOYUCAN | Servi Boulevard | PL/4401/EXP/ES/2015 | Pemex | 2.24 | ambos |
| TOREMEX | Petro 107 | PL/6909/EXP/ES/2015 | Pemex | 0.58 | ambos |
| TOREMEX | Juan Carmona Reyes | PL/11278/EXP/ES/2015 | Exxon Mobil | 1.58 | ambos |

**Marcas corregidas el 29-sep.** Cinco de esta tabla traían todavía el valor viejo de Profeco, anterior a la corrección del 25-sep: El Cid (decía Valero, es **Total**), Combuserv (decía Hidrosina, es **Pemex**), Galigas (decía sin marca, es **Pemex**), Parán (decía Pemex, es **Chevron**) y Ferman (decía sin marca, es **Sin Identificar**, que es justo lo que ya decía la sección 10). Ahora las 28 coinciden con `red.db`, verificado una por una. **Ante una diferencia, manda la base**: la marca se confirmó al 100% contra el CSV del operador.

`*` fuera del radio, agregadas por conocimiento del operador. Las dos están sobre Carretera Tula–Jorobas, que parece ser el eje real de esa plaza; el radio de 2 km para Ixtazacuala probablemente se queda corto.

**Las 96 distancias guardadas son Haversine y están bien.** Verificado el 29-sep recalculándolas desde las coordenadas: la desviación máxima en los 96 pares es de **50 centímetros**. Cualquier cálculo de radio variable que use Haversine va a reproducir este mismo set.

### Casos especiales de sentido vial

**QL y TEOLOYUCAN no compiten entre sí** pese a estar a 150 m: cuerpos opuestos de la autopista México–Querétaro Km 45.8, sin retorno a tiro. Los 150 m son ancho de vía. Por eso cada una tiene su directa distinta: Porcla para QL, Servi Boulevard para Teoloyucan.

**Arsona (PL/24156) vs Combulub, a 510 m:** el domicilio de Arsona dice "Km 53+640 Sentido 2". Si es cuerpo opuesto no compiten. Quedó en `es_competencia = 0` con `mismo_sentido` NULL. **Pendiente de confirmar.**

### Dos competidores confirmados sin precio

**Felipe Simón Olvera Castelán** (`id 50`, `PL/24553`, compite con TH) y **GPDC** (`id 82`, `PL/7069`, compite con IXTAZACUALA) no publican ante la CNE y no están en el set de 82. `v_precio_zona` nunca los va a mostrar. En el mapa aparecen ubicados pero sin precio. Ver pendiente 5-bis.

---

## 7. Ventas cargadas

**5 años y medio de ventas diarias**, del 2021-03-20 al 2026-09-24, para las 13 propias. 72,071 renglones.

| Año | Millones de litros | Estaciones |
|---|---|---|
| 2021 *(desde 20-mar)* | 52.41 | 12 |
| 2022 | 75.33 | 12 |
| 2023 | 83.73 | 12 |
| 2024 | 94.58 | 12 |
| 2025 | 92.17 | 13 |
| 2026 *(al 24-sep)* | 67.78 | 12 |

Cobertura por estación: entre 5,399 y 6,045 renglones cada una, salvo TREHER LL con 351. Las que tienen menos son las que sufrieron paros — COMBULUB (5,399), TOREMEX (5,955) e IXTAZACUALA (6,006). Ver sección 8.

La última fecha varía por estación: AILES TIERRA BLANCA, AVE FENIX y TEOLOYUCAN llegan al 24-sep; TREHER T y HUEHUETOCA solo al 20-sep. Los últimos días del archivo no están completos para todas.

**Advertencia sobre las cifras que traía el documento antes.** Las tablas de 2024, 2025 y 2026 de TREHER T y TH que había aquí venían de `venta_mensual` y eran **un mes específico por año**, no promedios ni años completos. Ya no están. Los hallazgos de la sección 9 se construyeron sobre esas cifras y **deben recalcularse** con la serie diaria.

## 8. Eventos registrados

| # | Tipo | Fechas | Participantes |
|---|---|---|---|
| 1 | Operativo federal, corredor Jilotepec–San Juan del Río | 14 sep 2026 → en curso (estimada) | TOREMEX beneficiada: regular se duplicó |
| 2 | Desabasto de Servicio Archundia (Canalejas) | 14 sep → 28 sep 2026 (estimada) | Archundia causante; TOREMEX beneficiada: regular se triplicó algunos días |
| 3 | Apertura de ACE frente a TREHER T | sin fecha | ACE causante; TREHER afectada |
| 4 | Apertura de Ferman cerca de AILES TIERRA BLANCA | sin fecha | Hipótesis sin confirmar |
| 5 | **Cierre de COMBULUB** | 28 mar → 2 oct 2025 (**189 días**) | Confirmado por el operador |
| 6 | **Cierre de IXTAZACUALA** | 28 mar → 8 abr 2025 (12 días) | Confirmado por el operador |
| 7 | **Cierre definitivo de TREHER LL** | 28 abr 2025 → sigue cerrada | Confirmado por el operador |
| 8 | Toremex sin diésel | 21 may → 10 ago 2021 (82 días) | Detectado en datos, **sin confirmar** |
| 9 | Combulub sin premium | 8 oct → 18 dic 2023 (72 días) | Detectado en datos, **sin confirmar** |
| 10 | Ave Fénix sin venta | 13 → 24 nov 2021 (12 días) | Detectado en datos, **sin confirmar** |

### Los paros que `venta_diaria` destapó

Ninguno de los seis estaba registrado. Salieron de agrupar en rachas consecutivas los días sin venta.

**COMBULUB estuvo 189 días sin vender un litro de ningún producto.** Seis meses. Cualquier comparación de Combulub 2025 contra otro año no tiene sentido hasta excluir ese periodo.

**COMBULUB e IXTAZACUALA paran el mismo día, el 2025-03-28.** Dos plazas distintas —Tizayuca y Atitalaquia— deteniéndose la misma fecha. El operador confirmó que ambos fueron cierres.

**Consecuencia que hay que medir:** Combulub compite con TH a 1.75 km. Si estuvo cerrada de marzo a octubre de 2025, **parte del volumen de TH en 2025 es volumen prestado.** Es medible con la serie diaria y es la primera cosa que conviene revisar.

Cuando TOREMEX perdió el diésel 82 días en 2021 siguió vendiendo gasolinas, así que eso fue falta de producto, no cierre.

Los días de cierre **no generan renglón** en `venta_diaria`: se ven como ausencia, y el evento es lo que los explica.

Los eventos 1 y 2 arrancaron casi a la par, así que **sus efectos sobre Toremex están superpuestos y no son separables** con datos mensuales. El duplicado viene del operativo; el triplicado es el desabasto encima.

Contexto de fondo del evento 1: presencia militar ligada a la obra del Tren México–Querétaro que cortó el abasto informal en la zona. Es **demanda prestada, no ganada**: cuando el operativo se retire, buena parte de ese cliente regresa al informal. El evento 2 termina cuando Canalejas se reabastezca.

---

## 8-bis. Lo que destaparon las facturas de compra

### Las compras cuadran con las ventas

Validación cruzada de dos fuentes independientes —el sistema de ventas y las facturas de compra— para 2024–2026. **Las doce estaciones activas cuadran dentro del 1–2%**, que es lo que se espera por inventario en piso y merma. Eso valida las dos fuentes a la vez.

**La excepción es TREHER LL.** Compró 1,007,000 litros en 2024 con **cero ventas registradas**, y 560,000 en 2025 contra 491,000 vendidos. Sus facturas arrancan el **2024-08-12**, cinco meses antes de la primera venta del archivo. Un millón de litros no caben en los tanques de una estación, así que lo más probable es que **falten las ventas de agosto a diciembre de 2024** y que LL haya abierto a mediados de 2024, no en enero de 2025. **Pendiente de verificar.**

### Ocho boletas facturadas dos veces

De 8,770 boletas, 18 tienen más de una factura. La vista `v_boleta_repetida` las clasifica en 8 `DUPLICADA_EXACTA`, 8 `CARGA_PARTIDA` y 2 `PRECIO_DISTINTO`. Las ocho de duplicado exacto — misma estación, producto, litros y precio, con dos folios distintos:

| Boleta | Fecha | Estación | Producto | Litros | Folios |
|---|---|---|---|---|---|
| 199993 | 2026-06-04 | IXTAZACUALA | REGULAR | 29,884 | 72273 / 72318 |
| 200590 | 2026-06-09 | TREHER T | DIESEL | 29,982 | 72534 / 72535 |
| 200654 | **2026-06-10** | AURORA | REGULAR | 36,247 | 72592 / 72651 |
| 200665 | **2026-06-10** | COMBULUB | REGULAR | 10,142 | 72601 / 72602 |
| 200666 | **2026-06-10** | COMBULUB | REGULAR | 19,958 | 72603 / 72604 |
| 200704 | **2026-06-10** | TEOLOYUCAN | DIESEL | 19,882 | 72610 / 72611 |
| 200705 | **2026-06-10** | AURORA | REGULAR | 35,942 | 72652 / 72708 |
| 209972 | 2026-09-14 | HUEHUETOCA | DIESEL | 29,881 | 77872 / 78145 |

**Cinco de las ocho son del mismo día, el 10 de junio de 2026.** Eso es un problema de captura de esa jornada, no azar. La boleta 210206 del 17 de septiembre llega a **cuatro** facturas.

**La copia de esas ocho suma $4,264,536 en importe calculado.**

*(Nota del 29-sep: `meta.boletas_repetidas` decía "siete". Se verificaron una por una contra `v_boleta_repetida` y son ocho; la clave quedó corregida.)*

### Dos boletas facturadas a dos precios

El 21 de septiembre de 2026, con casi un peso de diferencia por litro:

| Boleta | Estación | Litros | Folio | Precio |
|---|---|---|---|---|
| 210474 | QL | 33,380 | 78221 / 78288 | $20.377129 / $21.348613 |
| 210476 | AURORA | 35,788 | 78220 / 78287 | $20.377129 / $21.348613 |

Una de cada par está mal. Son unos $34,700 de diferencia solo en la de Aurora.

**Ninguna se excluyó de la tabla**: cada una tiene folio propio y decidir cuál es válida es contabilidad del operador. Pero con PEPS **cada factura crea una capa de inventario**, así que una boleta facturada dos veces mete existencia fantasma al costeo y lo arrastra hacia adelante hasta consumirse. **Resolverlas antes de correr capas de costo.**

---

## 9. Hallazgos de análisis

> **LEER ANTES DE USAR ESTA SECCIÓN.** Todo lo que sigue se calculó sobre `venta_mensual`, que guardaba **un mes específico por año** de solo TREHER T y TH. Con `venta_diaria` —cinco años y medio de las 13 estaciones— estas conclusiones **se pueden y se deben recalcular**. Hasta entonces, tratarlas como hipótesis, no como hechos.

**TREHER T y TH tienen perfiles de regular distintos pese a estar a 5 km.** Volumen parecido (314 mil contra 359 mil litros) pero peso muy distinto dentro de la estación: regular es 37.8% de TH y 53% de TREHER.

TREHER está en el Crucero del Carmen, nodo saturado, demanda residencial y de paso hacia Pachuca. Su regular cayó 15% en 2026 y 17% contra 2024: caída sostenida dos años. Vende regular más barato que TH ($23.83 contra $23.99) y aun así pierde volumen, lo que apunta a acceso, visibilidad o servicio más que a precio. La caída de premium (-21%) indica fuga del automovilista particular, no contracción de mercado.

TH está sobre el corredor industrial de Tepojaco, 57% diésel, demanda de flota y trabajadores de turno. Tuvo bache en 2025 y rebote en 2026.

Sumadas, las dos perdieron 90,782 litros de regular contra 2024 (-11.9%), y TREHER aporta el 81% de esa pérdida.

La caída de premium en ambas es efecto de mercado, no de plaza. La divergencia en regular sí es local.

**Advertencia metodológica registrada:** el -15% de TREHER no sirve como coeficiente para predecir qué pasará en otra plaza. Está contaminado por varios factores, diluido por meses de exposición parcial y sin grupo de control.

---

## 10. Fuentes y sus defectos

**Padrón de estaciones:** catálogo de la CNE (ex-CRE), feed de publicación de precios. Réplica en GitHub: `gasmonsoftaxel/Precios-Cre`.

**Ese repo no sirve como histórico.** Verificado el 24-sep-2026: su carpeta `historico/` arranca el **2026-08-29**, 26 archivos. No hay años previos ahí. El histórico de precios lo aportó el operador.

**`marca` ya no viene de Profeco.** Se corrigió el 25-sep-2026 con la lista del operador, confirmada al 100% contra la columna `Marca` de `PRECIOS COMPETENCIA 2026.csv` (82 permisos, cero diferencias). Fueron **19 cambios**. Donde la lista no traía marca se conservó el valor previo, por instrucción del operador: son 5 casos, todos competidores confirmados — ACE (Pemex), Carmona (Exxon Mobil), Zapata (Pemex), Oleum (G500) y Ferman (Sin Identificar). Las 10 estaciones fuera del set de 82 no se tocaron y siguen con el valor viejo de Profeco.

Dos de los 19 fueron solo grafía: `Wascom Blue` → `Wasconblue` y `Petro Figue S` → `Petro Figues`.

Reparto vigente: Pemex 33, Valero 14, G500 14, Shell 5, Servifacil 5, Total 2, Mobil 2, Hidrosina 2, Exxon Mobil 2, y una cada uno de Wasconblue, Red Energy, Petro Figues, Flash, Chevron, Bp y "Sin Identificar". Siete en NULL.

**`terminal` y `km_terminal`** son la TAR **más cercana calculada geográficamente**, no la terminal de suministro real. Ixtazacuala aparece con Pachuca a 52.6 km estando pegada a la refinería de Tula, y Toremex con Azcapotzalco a 81.8 km.

**`razon_social`** es la vigente del padrón CNE; `razon_social_previa` es la anterior. Cambia por cesión de derechos. Validar titular vigente ante la CNE antes de usarla en trámites.

**Las distancias son Haversine en línea recta**, no distancia de manejo. Y `relacion_estacion` guarda **solo 96 pares**, no todos contra todos: un radio variable tiene que calcular Haversine al vuelo sobre las 93 estaciones. **SQLite no trae funciones espaciales** — ni `ST_Distance` ni índices geográficos —, así que ese cálculo va en la capa de aplicación. Con 93 estaciones son 8,649 pares: trabajo despreciable, no hace falta precálculo.

**El feed de precios no detecta cierres ni desabasto en la zona de Toremex.** Verificado: entre el 29 de agosto y el 23 de septiembre de 2026, Toremex, Petro 107, Carmona y Archundia reportaron precio los 26 días sin cambiar un centavo. Archundia siguió reportando durante su propio desabasto. El método de detectar huecos en el feed solo sirve donde las estaciones mueven precio a diario.

---

## 10-bis. Lo que dicen los 9 meses de precios

**El precio no es una variable táctica en estas plazas.** En 263 días, las doce propias cambiaron el precio de regular entre **2 y 8 veces**. Huehuetoca fue la más activa con 8 movimientos; Combulub la más quieta con 2. El promedio es cinco cambios en nueve meses, o sea uno cada mes y medio.

Esto confirma con 263 días lo que se había visto con 26, y cierra la duda de si era un artefacto de la ventana corta: **no lo era.** Consecuencia práctica: no tiene sentido buscar reacciones de precio día por día, ni construir alertas sobre cambios diarios. El movimiento relevante es de nivel, y ocurre en escala de semanas. **Cualquier tablero que prometa "monitoreo diario" va a mostrar el mismo número semanas enteras.**

### Posición de precio, regular, promedio de los 263 días

Diferencial contra los competidores confirmados. Positivo = la propia está **más cara**.

| Propia | Competidores | Diferencial | Rango observado |
|---|---|---|---|
| IXTAZACUALA | 2 | **+0.185** | −0.50 a +0.60 |
| AILES TIERRA BLANCA | 2 | +0.166 | −0.40 a +0.50 |
| TEOLOYUCAN | 1 | +0.139 | +0.04 a +0.24 |
| TH | 2 | +0.068 | −0.28 a +0.50 |
| AVE FENIX | 3 | +0.065 | −0.70 a +0.80 |
| AILES TEPOJACO | 1 | −0.004 | −0.20 a +0.10 |
| AURORA | 3 | −0.015 | −0.30 a +0.30 |
| TOREMEX | 2 | −0.026 | −0.25 a +0.09 |
| QL | 2 | −0.029 | −0.40 a +0.24 |
| TREHER T | 3 | −0.043 | −0.31 a +0.29 |
| HUEHUETOCA | 3 | −0.162 | −0.66 a +0.40 |
| COMBULUB | 2 | **−0.264** | −0.50 a 0.00 |

**IXTAZACUALA y TEOLOYUCAN nunca están por debajo de nadie de forma sostenida** y son las dos más caras de la red frente a su competencia. Ixtazacuala además tiene el rango más amplio hacia arriba.

**COMBULUB es la más barata de la red**, y su rango nunca llega a cero por arriba: en los 263 días **jamás estuvo más cara** que Cúpula ni que TH. Es una estación que sistemáticamente se pone por debajo, incluso de su propia hermana del grupo.

### Esto sostiene el hallazgo de la sección 9

Ahí se concluyó que TREHER T pierde regular **pese a vender más barato** que TH, y que por eso la causa es acceso, visibilidad o servicio, no precio. Con nueve meses: TREHER promedia **−0.043 contra sus tres competidores** y **23.764 contra 23.855 de TH**. Está por debajo del mercado y por debajo de su hermana, sostenidamente, durante nueve meses. **En el periodo observado TREHER no pierde por caro.**

Un mes de datos no prueba dos años de caída, pero la hipótesis de precio queda descartada para 2026.

---

## 11. Pendientes

1. ~~**Cargar `precio_diario_CNE`.**~~ **HECHO 25-sep.** Queda como **pendiente recurrente**: recargar con el CSV actualizado; el cargador es idempotente. Y falta decidir si se consiguen **años anteriores a 2026**: hoy no hay con qué comparar contra 2024 ni 2025.
2. ~~**Cargar ventas diarias.**~~ **HECHO 25-sep.** Recurrente igual.
2-bis. **Recalcular la sección 9 con la serie diaria.** El pendiente de análisis más valioso. Empezar por: ¿cuánto del volumen de TH en 2025 es volumen prestado del cierre de COMBULUB?
2-ter. **Confirmar los tres paros sin confirmar** (eventos 8, 9 y 10).
2-quater. **Comparar `precio_venta` contra `precio_diario_CNE.precio`** en 2026, donde las dos series coexisten para las propias. Si un día el sistema dice un precio y la CNE otro, eso es un hallazgo.
3. **Marcar septiembre 2026 de Toremex como periodo anómalo** para que no contamine la base de comparación del año entrante.
4. **Fecha de apertura de ACE.** Buscar la resolución del permiso CNE/PL/386/EXP/ES/2025 y su primer reporte de precios. Sin esa fecha no se puede separar su efecto del resto de la caída de regular de TREHER.
5. **Confirmar Arsona vs Combulub**: ¿cuerpo opuesto o no? Arsona (`PL/24156`) quedó fuera del set de 82 y no viene en el CSV, aunque sí publica a la CNE.
5-bis. **Dos competidores confirmados sin precio**: Felipe Simón Olvera Castelán (`PL/24553`) y GPDC (`PL/7069`). Si su precio importa, hay que levantarlo en campo.
5-ter. **Diez estaciones fuera del set.** `red.db` tiene 93 y el operador vigila 82. Siete de las diez no publican precio. Tres sí publican y quedaron fuera: `PL/24156` (Arsona), `PL/2397` y `PL/3389`. Decidir si entran.
6. ~~**Terminal real de suministro.**~~ **Ya no bloquea nada**: con `factura_compra` el precio de compra real está por estación y factura. Sigue siendo útil para logística.
6-bis. **Verificar el municipio de TREHER LL**: el padrón dice Nextlalpan, su domicilio dice Zumpango.
6-ter. **Resolver las boletas repetidas** (`v_boleta_repetida`). Requisito antes de costear con capas.
6-quater. **Definir la capa inicial de inventario** al 2024-01-01 para poder correr PEPS.
6-quinquies. **Verificar las ventas de TREHER LL de agosto a diciembre de 2024**, que faltan según sus compras.
7. **Revisar si hubo caída en AILES TIERRA BLANCA** que corresponda a la apertura de Ferman (evento 4, hipótesis).
8. **Visor HTML**: había un `visor.html` con sql.js. **Superado** por la aplicación de la sección 13; se conserva la nota por si tiene algo aprovechable.
9. ~~**Confirmar los literales de `producto`.**~~ **RESUELTO 29-sep**: son `'REGULAR'`, `'PREMIUM'`, `'DIESEL'`, en mayúsculas y DIESEL sin acento, forzados por `CHECK`.
10. **Poblar `alias` de la competencia.** 80 estaciones lo tienen en NULL, así que el mapa muestra la razón social completa en mayúsculas. Es cosmético pero mejora mucho la lectura. Requiere que el operador dicte los nombres cortos.
11. **Normalizar la marca vacía.** 7 estaciones en `NULL` y 1 con `"Sin Identificar"`. Decidir cuál es la forma canónica.

---

## 12. Cómo trabajar de aquí en adelante

Entregar **scripts SQL de migración** sobre el `red.db` existente, no bases reconstruidas. Mantener nombre y ruta para no romper la conexión de DBeaver.

**Cerrar la conexión de DBeaver antes de cualquier escritura y refrescarla después.** Un DBeaver abierto puede bloquear la sobrescritura en Windows o seguir mostrando datos en caché. Si aparece "database is locked", cerrar DBeaver — **nunca activar WAL para resolverlo**.

Respaldar antes de cada carga, **dentro de `migraciones\`**: un respaldo en disco temporal se pierde al terminar la sesión y no le sirve al operador.

Migraciones aplicadas, en `migraciones\`:

- `2026-09-25_01_marcas_y_precio_diario.sql` — las 19 marcas, el DDL de la tabla de precios, `v_precio` y `v_precio_zona`.
- `2026-09-25_02_carga_precios_cne.py`
- `2026-09-25_03_ventas_diarias.sql` — columna `activa`, alta de TREHER LL, `venta_diaria`, vista `ventas`, baja de `venta_mensual` y sus dos vistas, y los seis eventos.
- `2026-09-25_03_venta_diaria.csv` — insumo limpio, 72,071 renglones.
- `2026-09-25_04_carga_ventas.py`
- `2026-09-25_05_factura_compra.sql` — `factura_compra`, `compras` y `v_boleta_repetida`.
- `2026-09-25_05_factura_compra.csv` — insumo limpio, 8,790 facturas.
- `2026-09-25_06_carga_facturas.py`
- **`2026-09-29_01_meta_actualizada.sql`** — corrige cinco claves de `meta` que quedaron desfasadas tras las cargas del 25-sep: `ventas_cobertura` (decía "solo TREHER T y TH"), `ventas_periodicidad` (decía MENSUALES), `siguiente_tabla` (describía la tabla de precios como pendiente), `boletas_repetidas` (decía siete duplicados exactos, son ocho) y `generado`. Solo toca `meta`; idempotente.

Respaldos: `red_respaldo_previo_2026-09-25.db`, `..._2026-09-25_ventas.db`, `..._2026-09-25_facturas.db` y **`red_respaldo_previo_2026-09-29_meta.db`**.

### Consultas de arranque

Verificadas contra el archivo el 29-sep-2026.

```sql
SELECT * FROM v_competencia ORDER BY base, distancia_km;
SELECT * FROM v_zona WHERE base = 'AURORA';
SELECT * FROM v_evento ORDER BY evento_id;
SELECT clave, valor FROM meta ORDER BY clave;

-- censo: confirma que el modelo es el que dice la seccion 3
SELECT type, name FROM sqlite_master
WHERE  name NOT LIKE 'sqlite_%' ORDER BY type DESC, name;

-- evolucion anio contra anio. Sustituye a v_evolucion, que ya no existe.
SELECT estacion, anio, ROUND(SUM(litros)/1e6, 3) AS millones_lts
FROM   ventas
WHERE  producto = 'REGULAR' AND activa = 1
GROUP  BY estacion, anio
ORDER  BY estacion, anio;

-- precios: posicion contra la competencia, ultimo dia disponible
-- OJO: precio_diario_CNE va SIEMPRE entre comillas dobles.
SELECT base, competidor, precio_base, precio_competidor, diferencial
FROM   v_precio_zona
WHERE  producto = 'REGULAR'
  AND  fecha = (SELECT MAX(fecha) FROM "precio_diario_CNE")
ORDER  BY base, diferencial DESC;

-- diferencial promedio de todo el periodo
SELECT base, COUNT(*) AS obs, ROUND(AVG(diferencial), 3) AS dif
FROM   v_precio_zona WHERE producto = 'REGULAR'
GROUP  BY base ORDER BY dif DESC;

-- cuantas veces movio el precio cada propia
WITH s AS (
  SELECT estacion, fecha, precio,
         LAG(precio) OVER (PARTITION BY estacion ORDER BY fecha) AS ant
  FROM   v_precio WHERE es_propia = 1 AND producto = 'REGULAR')
SELECT estacion,
       SUM(CASE WHEN ant IS NOT NULL AND precio <> ant THEN 1 ELSE 0 END) AS cambios,
       MIN(precio) AS minimo, MAX(precio) AS maximo
FROM   s GROUP BY estacion ORDER BY cambios DESC;

-- cobertura: quien publica poco
SELECT estacion, producto, COUNT(*) AS dias
FROM   v_precio GROUP BY estacion, producto ORDER BY dias, estacion;

-- estaciones que no publican precio (se ubican, pero sin comparacion)
SELECT id, permiso, COALESCE(alias, razon_social) AS nombre, es_propia
FROM   estacion
WHERE  id NOT IN (SELECT estacion_id FROM "precio_diario_CNE")
ORDER  BY es_propia DESC, nombre;

-- ventas: litros por año y estación (red que opera hoy)
SELECT anio, estacion, ROUND(SUM(litros)/1e6, 2) AS millones_lts
FROM   ventas WHERE activa = 1
GROUP  BY anio, estacion ORDER BY anio, millones_lts DESC;

-- ventas: mezcla de producto por estación, últimos 90 días
SELECT estacion, producto, ROUND(SUM(litros), 0) AS litros,
       ROUND(100.0 * SUM(litros) / SUM(SUM(litros)) OVER (PARTITION BY estacion), 1) AS mix_pct
FROM   ventas
WHERE  fecha >= date((SELECT MAX(fecha) FROM venta_diaria), '-90 day')
GROUP  BY estacion, producto ORDER BY estacion, producto;

-- compras: boletas facturadas mas de una vez
SELECT * FROM v_boleta_repetida ORDER BY clase, fecha_bol, bol, num_factura;

-- compras: precio promedio ponderado de compra por mes y producto
SELECT anio, mes, producto,
       ROUND(SUM(litros * precio) / SUM(litros), 4) AS precio_ponderado,
       ROUND(SUM(litros), 0) AS litros
FROM   compras GROUP BY anio, mes, producto ORDER BY anio, mes, producto;

-- compras contra ventas por anio y estacion (validacion cruzada)
SELECT c.anio, c.estacion,
       ROUND(c.lts/1000.0, 0) AS compra_miles,
       ROUND(v.lts/1000.0, 0) AS venta_miles,
       ROUND(100.0*(c.lts - v.lts)/v.lts, 1) AS dif_pct
FROM  (SELECT anio, estacion, SUM(litros) lts FROM compras GROUP BY 1,2) c
JOIN  (SELECT anio, estacion, SUM(litros) lts FROM ventas  GROUP BY 1,2) v
      ON v.anio = c.anio AND v.estacion = c.estacion
ORDER BY c.anio, c.estacion;

-- lo publicado ante la CNE contra lo que traia el sistema de ventas
SELECT v.fecha, v.estacion, v.producto, v.precio_venta, p.precio AS precio_cne,
       ROUND(v.precio_venta - p.precio, 2) AS brecha
FROM   ventas v
JOIN   "precio_diario_CNE" p ON p.estacion_id = v.estacion_id
                            AND p.fecha = v.fecha AND p.producto = v.producto
WHERE  ROUND(v.precio_venta - p.precio, 2) <> 0
ORDER  BY ABS(v.precio_venta - p.precio) DESC LIMIT 50;
```

---

## 13. La aplicación web

Vive en **`01.Competencia\app\`**, junto a la base. Arranca con doble clic en `run.bat`.

Sirve para ver sobre un mapa las estaciones propias y su competencia, con precios, distancias e histórico. Arquitectura elegida el 29-sep, después de comparar tres opciones:

```
red.db  →  copia local  →  FastAPI (solo lectura)  →  HTML/JS + Leaflet
```

Se descartó un visor sin servidor con sql.js —los 9.5 MB se descargarían completos en cada apertura y la base va a crecer— y se descartó migrar a PostgreSQL con PostGIS, que hoy es sobre-ingeniería para 93 estaciones. Tampoco se usa SQLAlchemy: con ocho tablas y solo lectura, el módulo `sqlite3` basta y evita una capa que no aporta.

**Tres garantías que el código cumple y las pruebas verifican:**

1. **La API nunca escribe en `red.db`.** Abre con `mode=ro` y `PRAGMA query_only`. Un intento de escritura es rechazado.
2. **Trabaja sobre una copia local, fuera de OneDrive**, en `%LOCALAPPDATA%\treher-red`. La instantánea se toma con la API `backup` de SQLite, que da una copia consistente aunque alguien esté escribiendo; copiar bytes queda solo como plan B. Tarda 169 ms.
3. **La copia se refresca sola** cuando cambian tamaño o fecha del original, así que recargar datos no obliga a reiniciar. `POST /api/db/refresh` lo fuerza.

**No hay credenciales ni nada que configurar.** SQLite es un archivo: no hay host, puerto, usuario ni contraseña. Y la ruta a `red.db` tampoco hace falta.

**La carpeta vive en SharePoint y se sincroniza entre varias máquinas**, cada una con su propia ruta (ver sección 1). Eso rompió el arranque el 29-sep: `.env` está dentro de la carpeta sincronizada, así que la ruta absoluta escrita en la máquina `soporte` le llegó a `preci`, donde esa carpeta no existe.

La solución no fue poner la ruta correcta sino **quitar la ruta**: `red.db` se busca por **posición relativa**, siempre junto a la carpeta `app`. Y si `RED_DB_PATH` trae una ruta que no existe en esa máquina, la aplicación usa el vecino y avisa en la consola en lugar de morirse. Ese es el comportamiento correcto para un proyecto compartido: **ninguna ruta absoluta debe quedar dentro de la carpeta sincronizada**.

Por lo mismo `run.bat` **ya no usa `--reload`**: vigilaba esa misma carpeta y cada sincronización de SharePoint reiniciaba el servidor.

Lo que no se comparte, y está bien así: el entorno virtual (`%USERPROFILE%\.venvs\treher`) y la copia de trabajo de la base (`%LOCALAPPDATA%\treher-red`). Son por máquina, así que dos personas pueden usar la aplicación a la vez sin estorbarse.

Estado al 29-sep: **etapas 2 a 8 de 12** terminadas y probadas — **120 comprobaciones de Python más 44 en un navegador real**. Se abre en `http://127.0.0.1:8000/` y muestra las 93 estaciones sobre el mapa; al hacer clic en una propia se resaltan sus competidores confirmados y se abre una ficha con el radio ajustable y la comparación de precios.

La vista imita la de una app de precios: pin con etiqueta de precio encima, y un selector de producto abajo a la izquierda que repinta las etiquetas. Debajo de zoom 11 las etiquetas se ocultan — 93 no caben en la vista general.

**Leaflet vive dentro del proyecto** (`frontend/vendor/`), no en un CDN: la aplicación abre aunque la máquina no tenga internet. Los mosaicos del mapa sí necesitan red; sin ella los marcadores se pintan igual sobre fondo vacío.

**Debajo del mapa va la tabla comparativa**, con el formato del Excel del operador: agrupada por estación, orden **DIÉSEL / PREMIUM / REGULAR**, selector de periodo y semáforo en el diferencial. El mapa pasó a altura fija (62vh, mínimo 430 px) y la página hace scroll.

**Un solo signo en toda la aplicación:** `diferencial = mi precio − su precio`. Positivo = estoy más caro. El Excel del operador usa el signo inverso; se eligió mantener una sola convención aquí en vez de arrastrar las dos. **El semáforo se prende a los 10 centavos**, por instrucción del operador.

**Detalle de los promedios.** Cada diferencial se promedia solo sobre los días en que las dos estaciones publicaron; las columnas de precio promedian cada estación por su cuenta. Por eso un diferencial puede no cuadrar con la resta de las dos columnas — el diferencial es el dato bueno, porque nunca mezcla fechas. Con un solo día coinciden siempre. Ojo también con el conteo: una ventana de 30 días naturales da **29 días comparados**, porque al feed le faltan 4 fechas completas de 2026 (ver sección 3).

Rutas: `/api/catalogos`, `/api/estaciones`, `/api/mapa`, `/api/estaciones/{id}`, `/api/precios/serie`, `/api/comparativo`, más `/health`, `/api/db/info` y `POST /api/db/refresh`. Siguen: gráficas de histórico, filtros, optimización y alertas.

**Los tres colores del mapa salen de `relacion_estacion.es_competencia`**, no de la distancia. Decisión del operador el 29-sep:

| Marcador | Qué es | Cuántas |
|---|---|---|
| Pin **azul con V** | Mis estaciones | 13 |
| Pin **rojo** | `es_competencia = 1`, competencia directa | 26 |
| Pin **amarillo** | `es_competencia = 0`, vecina registrada que **no** compite | 54 |
| Pin **hueco** | No publica precio del producto elegido | — |

Las 80 competidoras están en `relacion_estacion`; ninguna se queda sin clasificar.

**El color no puede ser absoluto.** Cinco estaciones son directa de una propia y no directa de otra: **Zapata, Porcla, Servi Boulevard, El Encino y Combulub**. Sin selección se usa la regla global —roja si es directa de al menos una propia—, y al seleccionar una estación los colores se recalculan **relativos a ella**. Las propias se quedan azules siempre, aunque una sea competencia de otra del grupo.

**Las vecinas amarillas se muestran pero NO entran en ninguna métrica.** Meter en un "promedio de competencia" a quien el operador decidió que no compite corrompe el número. Se listan aparte, sin diferencial, con su distancia y el motivo.

**El radio filtra sobre las estaciones relacionadas con la seleccionada**, directas y vecinas. El radio es una lente, no el criterio. Por eso el deslizador **arranca abarcando todas y no en el `radio_km` de la estación**: Ixtazacuala tiene dos competidores a 4.68 y 6.46 km con radio de 2 km, y arrancar en 2 los escondería de entrada. Salen marcados "fuera del radio".

**Las métricas de comparación se recalculan con el radio**, y solo cuentan a los competidores que disputan ese producto y que publicaron precio ese día. Siempre se muestra `n`: con uno o dos competidores el promedio no es una estadística, y la interfaz lo dice en vez de disimularlo.

**La interfaz distingue dos huecos que parecen el mismo.** Una celda con `—` es que la estación no publicó precio ese día. Una con `n/c` es que ese par no compite en ese producto, por criterio del operador: `compite_en` manda sobre los datos, así que el diésel de Zapata existe en la base pero la API no lo ofrece frente a TREHER, igual que hace `v_precio_zona`.

Las pruebas corren con `python -m pruebas.test_conexion` y `python -m pruebas.test_api` desde `app\`. Comprueban, entre otras cosas, que `red.db` no cambia de tamaño ni de fecha, que no quedan journals sueltos, que el censo del modelo coincide con la sección 3, que el Haversine de la aplicación reproduce las 96 distancias guardadas con menos de 50 cm de desviación, y que los pares dirigidos no se simetrizan: QL no lista a Teoloyucan ni al revés. Las del navegador (`pruebas/test_mapa.mjs`, opcionales: necesitan Node y Playwright) contrastan lo que la interfaz **muestra** contra métricas calculadas desde SQL por otro camino.
