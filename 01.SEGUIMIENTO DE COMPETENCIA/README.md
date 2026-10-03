# Monitoreo de precios y competencia — Grupo Treher

Aplicacion web interna sobre `red.db`. **La API nunca escribe en la base**:
abre todo en modo solo lectura y trabaja sobre una copia local.

Estado: **etapas 2 a 8 de 12** — conexion, API, mapa, radio variable y comparacion
de precios, probados (107 comprobaciones de Python mas 28 en navegador).

Se abre en `http://127.0.0.1:8000/`: las 93 estaciones sobre el mapa, y al
hacer clic en una propia se resaltan sus competidores confirmados.

## Arrancar

1. Instalar Python 3.9 o mas nuevo.
2. Doble clic en `run.bat`. La primera vez crea `.env` si falta y el entorno
   virtual en `%USERPROFILE%\.venvs\treher` — fuera de OneDrive a proposito,
   para no sincronizar miles de archivos de librerias.
3. Abre `http://127.0.0.1:8000/` para el mapa, o `/docs` para la API.

**No hay nada que configurar.** No hay usuario ni contrasena —SQLite es un
archivo— y la ruta a `red.db` tampoco hace falta: la aplicacion lo busca
junto a la carpeta `app`, que es donde siempre esta.

## Esta carpeta vive en SharePoint

Se sincroniza entre varias maquinas y cada quien la ve en una ruta distinta:

```
C:\Users\preci\...\Tesoreria y Finanzas Treher - ...\01.Diarios\01.Competencia
C:\Users\TREHER\...\Finanzas Treher - ...\01.Diarios\01.Competencia
```

Eso tiene dos consecuencias que el codigo ya contempla:

**`.env` tambien se sincroniza.** Si alguien escribe ahi una ruta absoluta,
le llega a los demas y no arrancan. Paso el 2026-09-29. Por eso `RED_DB_PATH`
va **vacio**, y si aun asi trae una ruta que no existe en esta maquina, la
aplicacion usa el `red.db` vecino y avisa en la consola en vez de morirse.

**`run.bat` no usa `--reload`.** Vigilaba esta misma carpeta, asi que cada
sincronizacion de SharePoint reiniciaba el servidor. Si cambias codigo, cierra
con Ctrl+C y vuelve a correrlo.

Lo que **no** se comparte, y esta bien asi: el entorno virtual
(`%USERPROFILE%\.venvs\treher`) y la copia de trabajo de la base
(`%LOCALAPPDATA%\treher-red`). Cada maquina tiene los suyos, asi que dos
personas pueden usar la aplicacion a la vez sin estorbarse.

## Rutas

**Datos**

| Ruta | Para que |
|---|---|
| `GET /api/catalogos` | Valores para poblar los filtros, mas conteos de control |
| `GET /api/estaciones` | Las 93, con filtros: `tipo`, `marca`, `estado`, `municipio`, `con_precio`, `activa`, `q` |
| `GET /api/mapa` | Lo mismo, con el ultimo precio de cada producto y su fecha. Es lo que consume el mapa |
| `GET /api/estaciones/{id}` | Detalle: precios, competidores confirmados con su precio de la MISMA fecha, y eventos |
| `GET /api/precios/serie` | Serie historica de una estacion y producto |
| `GET /api/comparativo` | La tabla completa de la red: cada propia con sus relacionadas, precios y diferencial. `dias=1` es el ultimo dia; mas de 1 promedia |

**Diagnostico**

| Ruta | Para que |
|---|---|
| `GET /health` | Vive, conecta, y que tan fresca esta la copia |
| `GET /api/db/info` | Censo del modelo: tablas, vistas y conteos |
| `POST /api/db/refresh` | Fuerza volver a copiar `red.db` tras una carga |

## Los tres colores del mapa

Salen de `relacion_estacion.es_competencia`, que es el criterio del operador,
no de la distancia:

| Marcador | Que es |
|---|---|
| Pin **azul con V** | Mis estaciones. Siempre azules, aunque una sea competencia de otra del grupo (Combulub y TH lo son) |
| Pin **rojo** | `es_competencia = 1`: competencia directa |
| Pin **amarillo** | `es_competencia = 0`: el radio la encontro, pero el operador determino que NO compite |
| Pin **hueco** | No publica precio del producto elegido |

Hoy: 13 mias, 26 directas, 54 vecinas. Las 80 competidoras estan en
`relacion_estacion`; ninguna se queda sin clasificar.

**El color no es absoluto.** Cinco estaciones son directa de una propia y no
directa de otra: Zapata, Porcla, Servi Boulevard, El Encino y Combulub. Sin
seleccion se usa la regla global (roja si es directa de AL MENOS UNA propia);
al seleccionar una estacion los colores se recalculan RELATIVOS a ella y lo
que no se relaciona con ella se apaga.

**Las vecinas amarillas se muestran pero NO entran en ninguna metrica.** Meter
en un "promedio de competencia" a quien el operador decidio que no compite
corrompe el numero. Se listan aparte, sin diferencial, con la distancia y el
motivo.

El selector de abajo a la izquierda cambia el producto de las etiquetas.
Debajo de zoom 11 las etiquetas se ocultan: 93 no caben en la vista general.

## La tabla comparativa

Debajo del mapa, con el formato del Excel del operador: agrupada por estacion,
orden **DIESEL / PREMIUM / REGULAR**, y semaforo en el diferencial.

**Un solo signo en toda la aplicacion:** `diferencial = mi precio - su precio`.
Positivo = estoy mas caro. El Excel del operador usa el signo inverso; se
eligio mantener una sola convencion aqui en vez de arrastrar las dos.

**El semaforo se prende a los 10 centavos**, por instruccion del operador:
verde si soy mas barato por 10 centavos o mas, rojo si soy mas caro por 10 o
mas, sin color por debajo de eso.

**El calendario elige la fecha FINAL del periodo.** Con "Ultimo dia" ves ese
dia exacto; con "Ultimos 30 dias" ves el promedio de los 30 que terminan ahi.
El boton "Ultimo" regresa al dia mas reciente con precios. Los limites del
calendario son el rango real de la base (2026-01-01 a 2026-09-24): no se puede
elegir un dia que no existe.

Si el dia elegido no tiene precios, la tabla lo dice. Al archivo de la CNE le
faltan cuatro fechas completas de 2026 — 3 y 23 de mayo, 4 de agosto y 3 de
septiembre — y es la captura, no las estaciones.

**Con promedio de varios dias hay un detalle que conviene saber.** Cada
diferencial se promedia SOLO sobre los dias en que las dos estaciones
publicaron; las columnas de precio, en cambio, promedian cada estacion por su
cuenta. Por eso un diferencial puede no cuadrar exactamente con la resta de las
dos columnas. El diferencial es el dato bueno, porque nunca mezcla fechas. Con
`dias=1` las dos cosas coinciden siempre.

## Criterios que la API respeta

- **`tipo=propia` devuelve 12**, no 13: excluye TREHER LL, que esta cerrada.
  Para verla: `?tipo=propia&activa=false`.
- **Las 11 estaciones que no publican precio si aparecen**, con
  `publica_precio = 0` y sin precios. Se ubican para tenerlas presentes.
- **Los pares de competencia son dirigidos** y se leen tal cual. QL no lista a
  Teoloyucan ni al reves, aunque esten a 150 m: son cuerpos opuestos de
  autopista.
- **La comparacion de precios siempre es dentro de la misma fecha.** Comparar
  el ultimo precio de dos estaciones que publicaron dias distintos no
  significa nada. Cuando no hay con que comparar, la respuesta trae `aviso`.
- **En el mapa, cada precio lleva su propia fecha**, porque no todas las
  estaciones publican el mismo dia.
- **El radio filtra DENTRO del set confirmado**, nunca sobre todas las
  estaciones. El radio es una lente, no el criterio: quien compite con quien
  lo decide `relacion_estacion.es_competencia`, que valido el operador. Por eso
  el deslizador arranca abarcando todo el set y no en el `radio_km` de la
  estacion: Ixtazacuala tiene dos competidores a 4.68 y 6.46 km con radio de
  2 km, y arrancar en 2 los esconderia de entrada. Salen marcados
  "fuera del radio".
- **Las metricas se calculan sobre lo que quede dentro del radio**, solo con
  los competidores que disputan ese producto y que publicaron precio ese dia.
  Siempre se muestra `n`, y con menos de tres se avisa que el promedio no es
  una estadistica.
- **`compite_en` manda sobre los datos.** Si un par compite solo en gasolinas,
  la API no devuelve el diesel del competidor aunque exista en la base:
  ofrecerlo invitaria justo a la comparacion que el operador declaro sin
  sentido. Es el criterio de `v_precio_zona`. En la interfaz, `n/c` es eso, y
  `—` es que no publico precio ese dia. No son lo mismo.

## Cargar ventas nuevas

```
python migraciones\cargar_ventas.py "ruta\al\archivo.xlsx"            simula
python migraciones\cargar_ventas.py "ruta\al\archivo.xlsx" --aplicar  escribe
```

**Por omision no escribe nada**: muestra cuantos renglones son nuevos, cuantos
cambiarian y cuales, y se detiene. Solo con `--aplicar` toca `red.db`, y
entonces hace el procedimiento completo — respaldo con fecha en
`migraciones\`, copia local, verificacion y sobrescritura.

Espera las columnas del Excel del operador, a lo ancho:

```
Estacion | Fecha | Diesel | Premium | Regular | $DIESEL | $PREMIUM | $REGULAR
```

Los encabezados se comparan sin acentos ni mayusculas, asi que da igual como
vengan escritos. La fecha acepta DD/MM/AAAA, AAAA-MM-DD y fechas de Excel.

**Es idempotente.** La llave es (estacion, fecha, producto): volver a correr el
mismo archivo no duplica nada, y uno con dias nuevos solo agrega esos. Se puede
pasar el archivo completo cada vez sin recortarlo.

Celda vacia, `0` y casi-cero (`1E-10`) significan "no se ofrecio el producto ese
dia" y se cargan como NULL, para que no sesguen los promedios.

Si aparece una estacion cuyo nombre no coincide con ningun alias, el script se
detiene y la nombra. Se resuelve agregando una linea a
`migraciones\alias_ventas.csv` — asi esta ATB para AILES TIERRA BLANCA.

Para leer `.xlsx` directo hace falta `pip install openpyxl`. Sin el, guarda la
hoja como CSV.

## Si un archivo "no se puede leer"

Esta carpeta usa Archivos a Petición de OneDrive: en una maquina que no los ha
abierto, los archivos existen pero son marcadores y Python falla con
`OSError: [Errno 22] Invalid argument`.

Se arregla abriendo la carpeta en el Explorador, o con clic derecho sobre
`01.Competencia` y "Mantener siempre en este dispositivo".

## Probar

```
python -m pruebas.test_conexion    # 33 comprobaciones de la capa de conexion
python -m pruebas.test_api         # 87 comprobaciones de las rutas de datos

# opcional, necesita Node y Playwright; con el servidor levantado:
python -m pruebas.esperado
node pruebas/test_mapa.mjs         # 28 comprobaciones del mapa
node pruebas/test_tabla.mjs        # 18 de la tabla y el layout
node pruebas/test_calendario.mjs   # 11 del calendario
```

Las del navegador contrastan lo que la interfaz MUESTRA contra metricas
calculadas desde SQL por otro camino. Las de conexion verifican que `red.db` no se modifica, que la escritura se
rechaza, que no quedan journals sueltos y que el calculo de distancias
coincide con el que ya esta guardado en la base. Las de la API van contra
cifras conocidas de `red.db`, no contra si mismas: si la base cambia, avisan.

## Por que hay una copia local

`red.db` vive en un mount de OneDrive. Leerla directo expone la API a que la
sincronizacion cambie el archivo a media consulta. El modulo `backend/db.py`
toma una instantanea con la API `backup` de SQLite y la deja en
`%LOCALAPPDATA%\treher-red`. Se refresca sola cuando cambian el tamano o la
fecha del original, asi que cargar datos nuevos no obliga a reiniciar.

## Dos trampas del esquema

Estan encapsuladas en `backend/queries.py`; no las repitas a mano.

1. La tabla de precios se llama **`precio_diario_CNE`**, no `precio_diario`, y
   lleva mayusculas: siempre necesita comillas dobles en SQL.
2. Los productos son **`REGULAR`, `PREMIUM`, `DIESEL`** — mayusculas y DIESEL
   sin acento. Un `CHECK` lo obliga; cualquier otra grafia devuelve cero
   renglones en silencio.

Y una del modelo: `es_propia = 1` devuelve **13** estaciones, no 12. TREHER LL
esta cerrada. La red que opera hoy es `es_propia = 1 AND activa = 1`.

## Estructura

```
app/
├── backend/
│   ├── config.py     lee .env, valida y falla temprano
│   ├── db.py         copia local, refresco y conexion de solo lectura
│   ├── geo.py        Haversine para el radio variable
│   ├── queries.py    todo el SQL, con las trampas encapsuladas
│   ├── schemas.py    formas de respuesta
│   ├── routes.py     rutas de datos
│   └── main.py       FastAPI + diagnostico
├── frontend/
│   ├── index.html
│   ├── css/app.css
│   ├── js/app.js     mapa, popups y ficha de competencia
│   └── vendor/       Leaflet, dentro del proyecto y no en un CDN
├── pruebas/
├── .env              NO se versiona
├── .env.example
├── requirements.txt
└── run.bat
```

## Siguientes etapas

5. Primer mapa con Leaflet.
6. Propias y competencia sobre el mapa.
7. Radio variable y distancias.
8. Comparacion de precios.
9. Historico y graficas.
10. Filtros.
