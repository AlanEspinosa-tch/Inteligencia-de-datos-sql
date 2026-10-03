-- =====================================================================
-- Migracion 2026-09-25_01
--   a) Corrige la columna marca de estacion segun la lista del operador
--   b) Crea precio_diario + indice + dos vistas
-- Base: red.db  (01.Diarios\01.Competencia\red.db)
-- Idempotente. No reconstruye nada. No toca ninguna otra columna.
--
-- COMO APLICARLA: OneDrive no deja a SQLite escribir en sitio sobre
-- red.db. Copiar a disco local, aplicar ahi, borrar cualquier
-- red.db-journal suelto, y sobrescribir. NUNCA activar journal_mode=WAL:
-- el mount no soporta el archivo -shm.
--
-- La CARGA de precios la hace 2026-09-25_02_carga_precios_cne.py desde
-- "PRECIOS COMPETENCIA 2026.csv", que vive en la carpeta padre.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- a) MARCA
-- Fuente: lista del operador, confirmada al 100% contra la columna Marca
-- de "PRECIOS COMPETENCIA 2026.csv" (82 permisos, cero diferencias).
-- Donde la lista viene vacia o dice "Sin Marca" se CONSERVA lo que ya
-- tiene red.db: son 5 casos, anotados al final de este bloque.
-- ---------------------------------------------------------------------
UPDATE estacion SET marca = 'Pemex'        WHERE permiso = 'PL/1051/EXP/ES/2015';   -- Corpogas        -> Pemex
UPDATE estacion SET marca = 'Pemex'        WHERE permiso = 'PL/11248/EXP/ES/2015';  -- NULL            -> Pemex
UPDATE estacion SET marca = 'Pemex'        WHERE permiso = 'PL/11271/EXP/ES/2015';  -- NULL            -> Pemex
UPDATE estacion SET marca = 'Pemex'        WHERE permiso = 'PL/11327/EXP/ES/2015';  -- Hidrosina       -> Pemex
UPDATE estacion SET marca = 'Wasconblue'   WHERE permiso = 'PL/12677/EXP/ES/2015';  -- Wascom Blue     -> Wasconblue
UPDATE estacion SET marca = 'Mobil'        WHERE permiso = 'PL/1278/EXP/ES/2015';   -- Petro 7         -> Mobil
UPDATE estacion SET marca = 'Total'        WHERE permiso = 'PL/1689/EXP/ES/2015';   -- Valero          -> Total
UPDATE estacion SET marca = 'G500'         WHERE permiso = 'PL/18961/EXP/ES/2016';  -- NULL            -> G500
UPDATE estacion SET marca = 'Shell'        WHERE permiso = 'PL/1965/EXP/ES/2015';   -- One             -> Shell
UPDATE estacion SET marca = 'Flash'        WHERE permiso = 'PL/20445/EXP/ES/2017';  -- Bp              -> Flash
UPDATE estacion SET marca = 'Petro Figues' WHERE permiso = 'PL/22827/EXP/ES/2019';  -- Petro Figue S   -> Petro Figues
UPDATE estacion SET marca = 'Pemex'        WHERE permiso = 'PL/22900/EXP/ES/2019';  -- Corpogas        -> Pemex
UPDATE estacion SET marca = 'Pemex'        WHERE permiso = 'PL/3301/EXP/ES/2015';   -- Exxon Mobil     -> Pemex
UPDATE estacion SET marca = 'Total'        WHERE permiso = 'PL/5746/EXP/ES/2015';   -- Valero          -> Total
UPDATE estacion SET marca = 'Mobil'        WHERE permiso = 'PL/5992/EXP/ES/2015';   -- Total           -> Mobil
UPDATE estacion SET marca = 'Pemex'        WHERE permiso = 'PL/7414/EXP/ES/2015';   -- Sin Identificar -> Pemex
UPDATE estacion SET marca = 'Pemex'        WHERE permiso = 'PL/8214/EXP/ES/2015';   -- G500            -> Pemex
UPDATE estacion SET marca = 'Chevron'      WHERE permiso = 'PL/9370/EXP/ES/2015';   -- Pemex           -> Chevron
UPDATE estacion SET marca = 'Shell'        WHERE permiso = 'PL/9977/EXP/ES/2015';   -- Orsan           -> Shell

-- Conservadas a peticion del operador (la lista no traia marca):
--   CNE/PL/386/EXP/ES/2025  -> Pemex            (ACE, competidor de TREHER T)
--   PL/11278/EXP/ES/2015    -> Exxon Mobil      (Carmona, competidor de TOREMEX)
--   PL/24614/EXP/ES/2022    -> Pemex            (Zapata, competidor de TREHER T)
--   PL/25437/EXP/ES/2023    -> G500             (Oleum, competidor de AVE FENIX)
--   PL/26174/EXP/ES/2025    -> Sin Identificar  (Ferman, competidor de AILES TIERRA BLANCA)
-- Las 10 estaciones que no aparecen en la lista no se tocaron.

-- ---------------------------------------------------------------------
-- b) precio_diario
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS precio_diario (
    estacion_id INTEGER NOT NULL REFERENCES estacion(id) ON DELETE CASCADE,
    fecha       TEXT    NOT NULL CHECK (fecha LIKE '____-__-__'),
    producto    TEXT    NOT NULL CHECK (producto IN ('REGULAR','PREMIUM','DIESEL')),
    precio      REAL    NOT NULL CHECK (precio BETWEEN 10 AND 45),
    PRIMARY KEY (estacion_id, fecha, producto)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS ix_precio_fecha ON precio_diario (fecha, producto);

-- Vista plana
DROP VIEW IF EXISTS v_precio;
CREATE VIEW v_precio AS
SELECT  p.fecha, p.producto,
        e.id AS estacion_id,
        COALESCE(e.alias, e.razon_social) AS estacion,
        e.marca, e.municipio, e.estado, e.es_propia,
        p.precio
FROM    precio_diario p
JOIN    estacion e ON e.id = p.estacion_id;

-- Propia contra cada competidor confirmado, mismo dia y producto.
-- diferencial > 0 = la propia esta MAS CARA. Respeta compite_en.
DROP VIEW IF EXISTS v_precio_zona;
CREATE VIEW v_precio_zona AS
SELECT  pp.fecha, pp.producto,
        COALESCE(b.alias, b.razon_social) AS base,
        COALESCE(c.alias, c.razon_social) AS competidor,
        c.marca AS marca_competidor,
        r.distancia_km,
        pp.precio AS precio_base,
        pc.precio AS precio_competidor,
        ROUND(pp.precio - pc.precio, 2) AS diferencial
FROM    relacion_estacion r
JOIN    estacion b       ON b.id = r.estacion_id
JOIN    estacion c       ON c.id = r.relacionada_id
JOIN    precio_diario pp ON pp.estacion_id = r.estacion_id
JOIN    precio_diario pc ON pc.estacion_id = r.relacionada_id
                        AND pc.fecha = pp.fecha AND pc.producto = pp.producto
WHERE   r.es_competencia = 1
  AND ( r.compite_en = 'AMBOS'
     OR (r.compite_en = 'GASOLINAS' AND pp.producto IN ('REGULAR','PREMIUM'))
     OR (r.compite_en = 'DIESEL'    AND pp.producto =  'DIESEL') );

-- ---------------------------------------------------------------------
-- c) meta
-- ---------------------------------------------------------------------
INSERT INTO meta (clave, valor) VALUES
 ('precio_diario_fuente',
  'PRECIOS COMPETENCIA 2026.csv, aportado por el operador. 82 estaciones, 2026-01-01 a 2026-09-24. Formato original ANCHO (una columna por producto); se cargo en LARGO para empatar con venta_mensual. Permiso CRE = estacion.permiso, resuelve directo.'),
 ('precio_diario_ceros',
  'El CSV original NO usa celdas vacias: cuando no hay dato pone 0. Eran 957 en regular, 297 en premium y 2674 en diesel, todos exactamente cero. NO se cargaron. Que falte un renglon significa que no se publico precio ese dia, no que la estacion estuviera cerrada.'),
 ('precio_diario_duplicados',
  'El CSV traia 163 pares (permiso,fecha) duplicados, en 28/03/2026 y 24/05/2026. Se verificaron uno por uno: los 163 con precios IDENTICOS, cero conflictos. Se colapsaron por la PK.'),
 ('precio_diario_dias_faltantes',
  'Faltan 4 fechas completas en el origen: 2026-05-03, 2026-05-23, 2026-08-04 y 2026-09-03. Nadie reporto esos dias, es la captura y no las estaciones. 263 fechas con dato de 267 del rango.'),
 ('precio_diario_sin_regular',
  'Autoservicio Atlanta (PL/11248), Galigas (PL/11271) y Tepogas (PL/18961) nunca reportan REGULAR pero si premium y diesel los 263 dias. Coincide con el feed publico de la CNE, no es defecto del archivo.'),
 ('estaciones_fuera_del_set',
  '10 estaciones de red.db no estan en el set de 82 que vigila el operador ni en el CSV de precios. Siete no publican precio a la CNE. Tres si publican y quedaron fuera: PL/24156 (Arsona), PL/2397 y PL/3389. OJO: PL/24553 (Felipe Simon Olvera) y PL/7069 (GPDC) son COMPETENCIA CONFIRMADA de TH y de IXTAZACUALA y se quedan sin precio.'),
 ('fuente_marca',
  'Corregida el 2026-09-25 con la lista del operador, confirmada contra la columna Marca de PRECIOS COMPETENCIA 2026.csv (82 permisos, cero diferencias). 19 cambios. Donde la lista no traia marca se conservo el valor previo (5 casos). Ya NO viene del archivo estatico de Profeco.'),
 ('no_usar_wal',
  'NUNCA activar PRAGMA journal_mode=WAL: la carpeta es un mount FUSE de OneDrive y SQLite no puede crear ahi el archivo -shm. Falla con disk I/O error y un journal huerfano puede corromper la base. Se queda en journal_mode = delete.')
ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;

UPDATE meta SET valor = 'Cuenta como competencia solo si tiene sentido vial. Lo confirmo el operador, que conoce las doce plazas.'
 WHERE clave = 'es_competencia';

UPDATE meta SET valor = 'Radio de descubrimiento por estacion propia, no criterio de competencia: TREHER T, TH, AILES TIERRA BLANCA, AILES TEPOJACO, AVE FENIX y AURORA 4 km; QL y TEOLOYUCAN 3 km; COMBULUB, HUEHUETOCA, IXTAZACUALA y TOREMEX 2 km.'
 WHERE clave = 'radio_km';
