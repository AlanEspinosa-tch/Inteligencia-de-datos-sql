-- 2026-09-29_01_meta_actualizada.sql
--
-- Corrige cinco entradas de `meta` que quedaron desfasadas tras las cargas
-- del 2026-09-25. Tres eran residuo de `venta_mensual`, una tenia un conteo
-- equivocado y otra una fecha vieja.
--
-- Solo toca la tabla `meta`. No altera el esquema ni ningun dato de negocio.
-- Idempotente: se puede volver a ejecutar sin efecto.
--
-- Verificado antes de escribir:
--   venta_diaria      -> 13 estaciones, 2021-03-20 a 2026-09-24, 72,071 renglones
--   v_boleta_repetida -> 8 DUPLICADA_EXACTA, 8 CARGA_PARTIDA, 2 PRECIO_DISTINTO
--                        (18 boletas, coincide con el valor previo)
--   de las 8 DUPLICADA_EXACTA, 5 son del 2026-06-10

BEGIN;

-- 1. Decia "Solo TREHER T y TH tienen ventas cargadas". Son 13.
UPDATE meta SET valor =
'venta_diaria cubre las 13 estaciones propias: 12 activas mas TREHER LL, cerrada desde 2025-04-28. Del 2021-03-20 al 2026-09-24, 72,071 renglones, 2,015 fechas. Corregido el 2026-09-29: el valor anterior decia "solo TREHER T y TH" y era residuo de venta_mensual.'
WHERE clave = 'ventas_cobertura';

-- 2. Decia "MENSUALES por producto". Son diarias desde el 25-sep.
UPDATE meta SET valor =
'DIARIAS por producto y estacion, desde la carga del 2026-09-25. PK (estacion_id, fecha, producto), WITHOUT ROWID. Corregido el 2026-09-29: el valor anterior decia MENSUALES y describia a venta_mensual, que se elimino.'
WHERE clave = 'ventas_periodicidad';

-- 3. Describia precio_diario como tabla pendiente. Ya existe, y con otro nombre.
UPDATE meta SET valor =
'HECHO el 2026-09-25. No queda tabla pendiente. OJO CON EL NOMBRE: la tabla se llama precio_diario_CNE, no precio_diario, y lleva mayusculas, asi que SIEMPRE exige comillas dobles en SQL. PK (estacion_id, fecha, producto), WITHOUT ROWID, 59,938 renglones, 82 estaciones, 2026-01-01 a 2026-09-24. Corregido el 2026-09-29.'
WHERE clave = 'siguiente_tabla';

-- 4. Decia "Siete son DUPLICADA_EXACTA". Son ocho; verificadas una por una.
UPDATE meta SET valor =
'18 boletas tienen mas de una factura. Ver v_boleta_repetida. OCHO son DUPLICADA_EXACTA (misma estacion, producto, litros y precio con dos folios) y CINCO DE ESAS OCHO son del 2026-06-10: es un problema de captura de ese dia, no azar. La boleta 210206 tiene CUATRO facturas. Dos casos del 2026-09-21 (BOL 210476 AURORA y 210474 QL) son PRECIO_DISTINTO: misma boleta y litros facturados a 20.377129 y a 21.348613, casi un peso de diferencia. Ninguna se excluyo de la tabla. Corregido el 2026-09-29: el valor anterior decia siete.'
WHERE clave = 'boletas_repetidas';

-- 5. Fecha de armado inicial, sin actualizar tras las cargas del 25-sep.
UPDATE meta SET valor =
'2026-09-29. Fecha de la ultima modificacion de red.db. Antes decia 2026-09-24, que era la fecha de armado inicial: las cargas del 25-sep no actualizaron esta clave.'
WHERE clave = 'generado';

COMMIT;
