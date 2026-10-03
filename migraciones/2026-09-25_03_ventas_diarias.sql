-- =====================================================================
-- Migracion 2026-09-25_03
--   a) estacion: columna activa + alta de TREHER LL (cerrada)
--   b) venta_diaria + vista ventas
--   c) baja de venta_mensual, v_venta y v_evolucion
--   d) eventos de cierre
-- Base: red.db.  Idempotente donde se puede.
--
-- NO activar journal_mode=WAL (OneDrive no soporta el -shm). Aplicar sobre
-- copia local, borrar red.db-journal suelto, y sobrescribir.
--
-- Los datos de venta_diaria los carga 2026-09-25_04_carga_ventas.py desde
-- 2026-09-25_03_venta_diaria.csv, que esta en esta misma carpeta.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- a) estacion: bandera de operacion
--    "mi red hoy"       = es_propia = 1 AND activa = 1   (12 estaciones)
--    "mi red historica" = es_propia = 1                  (13 estaciones)
-- ---------------------------------------------------------------------
ALTER TABLE estacion ADD COLUMN activa INTEGER NOT NULL DEFAULT 1;

-- TREHER LL: operó del 2025-01-01 al 2025-04-28 y sigue cerrada.
-- Se da de alta para no perder 117 dias de venta real de 2025; sin la
-- estacion la llave foranea no admitiria esos renglones.
-- Municipio: el padron la pone en Nextlalpan por localidad INEGI mas
-- cercana; su domicilio dice Zumpango. Se usa Nextlalpan para que
-- municipio y cve_geo no queden en contradiccion. Ver meta.
INSERT INTO estacion
  (id, permiso, alias, razon_social, marca, tipo_permiso, anio_permiso,
   estado, municipio, cve_geo, domicilio, latitud, longitud,
   terminal, km_terminal, es_propia, radio_km, activa)
VALUES
  (93, 'PL/19259/EXP/ES/2016', 'TREHER LL', 'GRUPO TREHER SA DE CV', 'Valero',
   'ES', 2016, 'México', 'Nextlalpan', '15059',
   'Carretera Zumpango-Cuautitlán 1200, San Pedro la Laguna, C.p. 55609, Zumpango, México',
   19.76736, -99.12288, 'San Juan Ixhuatepec', 26.6, 1, NULL, 0)
ON CONFLICT(permiso) DO NOTHING;

-- ---------------------------------------------------------------------
-- b) venta_diaria
--    litros y precio_venta son NULLABLE a proposito: el origen usa vacio,
--    0 y casi-cero (1E-10) para "no se ofrecio el producto ese dia".
--    Los tres se cargan como NULL, asi AVG y SUM los ignoran solos.
--    precio_venta es el precio del sistema de ventas, NO es lo mismo que
--    precio_diario.precio, que es lo publicado ante la CNE.
--    El importe NO se guarda: en el origen era exactamente litros*precio
--    (verificado en 72,156 comparaciones, cero desviaciones), asi que se
--    deriva en la vista y no puede quedar en contradiccion.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS venta_diaria (
    estacion_id  INTEGER NOT NULL REFERENCES estacion(id) ON DELETE CASCADE,
    fecha        TEXT    NOT NULL CHECK (fecha LIKE '____-__-__'),
    producto     TEXT    NOT NULL CHECK (producto IN ('REGULAR','PREMIUM','DIESEL')),
    litros       REAL             CHECK (litros >= 0),
    precio_venta REAL             CHECK (precio_venta BETWEEN 10 AND 45),
    PRIMARY KEY (estacion_id, fecha, producto)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS ix_venta_fecha ON venta_diaria (fecha, producto);

-- ---------------------------------------------------------------------
-- c) fuera lo mensual: era un mes por anio y ya no hace falta
-- ---------------------------------------------------------------------
DROP VIEW  IF EXISTS v_venta;
DROP VIEW  IF EXISTS v_evolucion;
DROP TABLE IF EXISTS venta_mensual;

-- ---------------------------------------------------------------------
-- d) la vista de ventas
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS ventas;
CREATE VIEW ventas AS
SELECT  v.fecha,
        CAST(strftime('%Y', v.fecha) AS INTEGER) AS anio,
        CAST(strftime('%m', v.fecha) AS INTEGER) AS mes,
        CASE strftime('%m', v.fecha)
             WHEN '01' THEN 'ENERO'   WHEN '02' THEN 'FEBRERO'  WHEN '03' THEN 'MARZO'
             WHEN '04' THEN 'ABRIL'   WHEN '05' THEN 'MAYO'     WHEN '06' THEN 'JUNIO'
             WHEN '07' THEN 'JULIO'   WHEN '08' THEN 'AGOSTO'   WHEN '09' THEN 'SEPTIEMBRE'
             WHEN '10' THEN 'OCTUBRE' WHEN '11' THEN 'NOVIEMBRE' ELSE 'DICIEMBRE' END AS mes_letra,
        CASE strftime('%w', v.fecha)
             WHEN '0' THEN 'DOMINGO' WHEN '1' THEN 'LUNES'   WHEN '2' THEN 'MARTES'
             WHEN '3' THEN 'MIÉRCOLES' WHEN '4' THEN 'JUEVES' WHEN '5' THEN 'VIERNES'
             ELSE 'SÁBADO' END                   AS dia_semana,
        e.id                                     AS estacion_id,
        COALESCE(e.alias, e.razon_social)        AS estacion,
        e.activa,
        v.producto,
        v.litros,
        v.precio_venta,
        ROUND(v.litros * v.precio_venta, 4)      AS importe_calculado
FROM    venta_diaria v
JOIN    estacion e ON e.id = v.estacion_id;

-- ---------------------------------------------------------------------
-- e) eventos: cierres y faltantes de producto detectados en las ventas
-- ---------------------------------------------------------------------
INSERT INTO evento (tipo, titulo, descripcion, fecha_inicio, fecha_fin, fecha_estimada, fuente)
SELECT * FROM (
  SELECT 'CLAUSURA' AS tipo, 'Cierre de COMBULUB, marzo a octubre 2025' AS titulo,
         'COMBULUB no vendio un solo litro de ningun producto durante 189 dias consecutivos. Detectado en venta_diaria y CONFIRMADO por el operador como cierre. Cualquier comparacion anual de COMBULUB 2025 debe excluir este periodo.' AS descripcion,
         '2025-03-28' AS fecha_inicio, '2025-10-02' AS fecha_fin, 0 AS fecha_estimada,
         'venta_diaria + confirmacion del operador' AS fuente
  UNION ALL SELECT 'CLAUSURA', 'Cierre de IXTAZACUALA, 12 dias de 2025',
         'IXTAZACUALA no vendio ningun producto durante 12 dias. Arranca el MISMO dia que el cierre de COMBULUB (2025-03-28). Detectado en venta_diaria y CONFIRMADO por el operador como cierre.',
         '2025-03-28', '2025-04-08', 0, 'venta_diaria + confirmacion del operador'
  UNION ALL SELECT 'CLAUSURA', 'Cierre definitivo de TREHER LL',
         'TREHER LL (PL/19259/EXP/ES/2016) opero del 2025-01-01 al 2025-04-28 y sigue cerrada. Se conserva en estacion con activa=0 para no perder sus 117 dias de venta. No tiene relaciones de competencia ni precios de la CNE.',
         '2025-04-28', NULL, 0, 'confirmacion del operador'
  UNION ALL SELECT 'OTRO', 'TOREMEX sin diesel, 82 dias de 2021',
         'TOREMEX no vendio diesel del 2021-05-21 al 2021-08-10 mientras siguio vendiendo gasolinas: apunta a falta de producto, no a cierre. DETECTADO EN LOS DATOS, SIN CONFIRMAR por el operador.',
         '2021-05-21', '2021-08-10', 0, 'venta_diaria (sin confirmar)'
  UNION ALL SELECT 'OTRO', 'COMBULUB sin premium, 72 dias de 2023',
         'COMBULUB no vendio premium del 2023-10-08 al 2023-12-18 mientras siguio vendiendo regular y diesel. DETECTADO EN LOS DATOS, SIN CONFIRMAR por el operador.',
         '2023-10-08', '2023-12-18', 0, 'venta_diaria (sin confirmar)'
  UNION ALL SELECT 'OTRO', 'AVE FENIX sin venta, 12 dias de noviembre 2021',
         'AVE FENIX no vendio ningun producto del 2021-11-13 al 2021-11-24, con precio publicado. DETECTADO EN LOS DATOS, SIN CONFIRMAR por el operador.',
         '2021-11-13', '2021-11-24', 0, 'venta_diaria (sin confirmar)'
) AS nuevos
WHERE NOT EXISTS (SELECT 1 FROM evento e WHERE e.titulo = nuevos.titulo);

-- ligar cada evento a su estacion
INSERT INTO evento_estacion (evento_id, estacion_id, rol, efecto)
SELECT ev.id, es.id, 'AFECTADA', ef.efecto FROM (
  SELECT 'Cierre de COMBULUB, marzo a octubre 2025' AS t, 'COMBULUB' AS al, 'Venta en cero los 189 dias.' AS efecto
  UNION ALL SELECT 'Cierre de IXTAZACUALA, 12 dias de 2025', 'IXTAZACUALA', 'Venta en cero los 12 dias.'
  UNION ALL SELECT 'Cierre definitivo de TREHER LL', 'TREHER LL', 'Cierre definitivo; 117 dias operados en 2025.'
  UNION ALL SELECT 'TOREMEX sin diesel, 82 dias de 2021', 'TOREMEX', 'Diesel en cero 82 dias; gasolinas sin interrupcion.'
  UNION ALL SELECT 'COMBULUB sin premium, 72 dias de 2023', 'COMBULUB', 'Premium en cero 72 dias; regular y diesel sin interrupcion.'
  UNION ALL SELECT 'AVE FENIX sin venta, 12 dias de noviembre 2021', 'AVE FENIX', 'Venta en cero los 12 dias, con precio publicado.'
) AS ef
JOIN evento   ev ON ev.titulo = ef.t
JOIN estacion es ON es.alias  = ef.al
WHERE NOT EXISTS (SELECT 1 FROM evento_estacion x WHERE x.evento_id = ev.id AND x.estacion_id = es.id);

-- ---------------------------------------------------------------------
-- f) meta
-- ---------------------------------------------------------------------
INSERT INTO meta (clave, valor) VALUES
 ('venta_diaria_fuente',
  'Archivo de ventas del operador (Libro1.csv), formato ANCHO con litros y precio por producto en columnas. Convertido a LARGO. 72,071 renglones, 2021-03-20 a 2026-09-24, 13 estaciones. La fecha venia como serial de Excel (epoca 1899-12-30).'),
 ('venta_diaria_nulos',
  'El origen usaba tres formas de decir "no se ofrecio el producto ese dia": celda vacia, 0 y casi-cero (1E-10 / 0.000000001). Las tres se cargaron como NULL por instruccion del operador, para que no sesguen promedios. 766 renglones se omitieron porque litros y precio quedaban ambos nulos; 40 quedaron con litros NULL y precio real (dias de paro con precio publicado).'),
 ('venta_diaria_precios',
  'Los precios se redondearon a 2 decimales. De 87 valores con mas de 2 decimales, 77 eran marcadores casi-cero y solo 10 eran precios reales (probables promedios de dias con cambio de precio a media jornada). precio_venta es el precio del sistema de ventas, NO es precio_diario.precio, que es lo publicado ante la CNE.'),
 ('venta_diaria_sin_importe',
  'El importe NO se guarda. En el origen era exactamente litros*precio: verificado en 72,156 comparaciones con cero desviaciones mayores a un centavo. Por lo tanto NO es dinero de caja sino una multiplicacion de hoja de calculo, y NO permite detectar descuentos. La vista ventas lo deriva como importe_calculado.'),
 ('venta_mensual_eliminada',
  'venta_mensual se borro el 2026-09-25. Sus cifras eran de UN MES ESPECIFICO por anio, no promedios, y solo cubrian TREHER T y TH. venta_diaria la reemplaza con 5 anios y medio de las 13 estaciones. OJO: los hallazgos de la seccion 9 del CONTEXTO se construyeron sobre esas cifras de un mes por anio y deben recalcularse con la serie diaria.'),
 ('estacion_activa',
  'Columna activa: 1 = en operacion, 0 = cerrada. Solo TREHER LL (id 93) esta en 0. "Mi red hoy" es es_propia=1 AND activa=1 (12 estaciones); "mi red historica" es es_propia=1 (13). Las consultas viejas que solo usan es_propia=1 ahora devuelven 13.'),
 ('treher_ll_municipio',
  'TREHER LL: el padron geo la ubica en Nextlalpan (cve_geo 15059) por localidad INEGI mas cercana, pero su domicilio dice Zumpango. Se cargo Nextlalpan para que municipio y cve_geo no queden en contradiccion. Verificar en campo si importa.'),
 ('paros_detectados',
  'venta_diaria revelo paros que no estaban registrados: COMBULUB 189 dias (2025-03-28 a 2025-10-02) e IXTAZACUALA 12 dias (mismo dia de arranque), ambos confirmados como cierres por el operador; y tres interrupciones de producto sin confirmar (TOREMEX diesel 82 dias 2021, COMBULUB premium 72 dias 2023, AVE FENIX 12 dias nov-2021). Estan en evento. El cierre de COMBULUB coincide con el corredor de competencia de TH a 1.75 km: parte del volumen de TH en 2025 puede ser volumen prestado.')
ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
