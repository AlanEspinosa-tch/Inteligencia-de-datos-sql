-- =====================================================================
-- Migracion 2026-09-25_05  ·  factura_compra
-- Facturas de compra de combustible. 8,790 facturas, 2024-01-02 a
-- 2026-09-23, 13 estaciones.
--
-- NO activar journal_mode=WAL (OneDrive no soporta el -shm). Aplicar sobre
-- copia local, borrar red.db-journal suelto, y sobrescribir.
-- Los datos los carga 2026-09-25_06_carga_facturas.py desde
-- 2026-09-25_05_factura_compra.csv, en esta misma carpeta.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- Tabla. El grano es la FACTURA: una estacion, un producto, una fecha.
-- num_factura es UNICO en los 8,790 renglones del origen, asi que sirve
-- de llave primaria natural. Va como TEXT por si algun dia el folio gana
-- un prefijo o un cero a la izquierda.
--
-- fecha_bol se llama asi a proposito: es la fecha de la BOLETA, que no
-- necesariamente es la de facturacion. El origen no trae fecha de factura.
--
-- El importe NO se guarda: se deriva como litros * precio. Y OJO, el
-- origen NO trae el total facturado, ni IVA, ni IEPS, ni proveedor. Esto
-- es el detalle de compra de combustible, NO cuentas por pagar.
--
-- precio NO se redondea: trae de 3 a 8 decimales y esa precision es real.
-- Distinto de venta_diaria.precio_venta, que si se redondeo a 2.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS factura_compra (
    num_factura TEXT    PRIMARY KEY,
    estacion_id INTEGER NOT NULL REFERENCES estacion(id) ON DELETE CASCADE,
    fecha_bol   TEXT    NOT NULL CHECK (fecha_bol LIKE '____-__-__'),
    producto    TEXT    NOT NULL CHECK (producto IN ('REGULAR','PREMIUM','DIESEL')),
    litros      REAL    NOT NULL CHECK (litros > 0),
    precio      REAL    NOT NULL CHECK (precio BETWEEN 5 AND 45),
    bol         TEXT
);

-- Orden determinista para capas de costo PEPS por estacion:
-- (fecha_bol, num_factura). Si llegan dos pipas el mismo dia, el folio
-- desempata porque es secuencial en todo el archivo.
CREATE INDEX IF NOT EXISTS ix_factura_peps
    ON factura_compra (estacion_id, producto, fecha_bol, num_factura);

CREATE INDEX IF NOT EXISTS ix_factura_bol ON factura_compra (bol);

-- ---------------------------------------------------------------------
-- Vista plana
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS compras;
CREATE VIEW compras AS
SELECT  f.fecha_bol,
        CAST(strftime('%Y', f.fecha_bol) AS INTEGER) AS anio,
        CAST(strftime('%m', f.fecha_bol) AS INTEGER) AS mes,
        f.num_factura,
        f.bol,
        e.id                              AS estacion_id,
        COALESCE(e.alias, e.razon_social) AS estacion,
        e.activa,
        f.producto,
        f.litros,
        f.precio,
        ROUND(f.litros * f.precio, 4)     AS importe_calculado
FROM    factura_compra f
JOIN    estacion e ON e.id = f.estacion_id;

-- ---------------------------------------------------------------------
-- Boletas con mas de una factura. NO se excluyo ninguna de la tabla:
-- cada una tiene folio propio y decidir cual es valida es contabilidad
-- del operador. Esta vista las senala para que las revise.
--
-- IMPORTANTE para PEPS: cada factura crea una capa de inventario, asi
-- que una boleta facturada dos veces mete existencia fantasma al costeo.
-- Resolverlas ANTES de correr capas de costo.
--
-- clase:
--   DUPLICADA_EXACTA  misma estacion, producto, litros y precio -> muy
--                     probablemente doble facturacion
--   PRECIO_DISTINTO   misma estacion y litros, precio distinto -> refactura
--                     o correccion; una de las dos esta mal
--   CARGA_PARTIDA     estaciones distintas -> probablemente una pipa que
--                     surtio a dos estaciones; normal
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_boleta_repetida;
CREATE VIEW v_boleta_repetida AS
WITH d AS (
    SELECT bol FROM factura_compra
    WHERE bol IS NOT NULL GROUP BY bol HAVING COUNT(*) > 1
),
m AS (
    SELECT f.bol,
           COUNT(DISTINCT f.estacion_id) AS n_estaciones,
           COUNT(DISTINCT f.precio)      AS n_precios,
           COUNT(*)                      AS n_facturas
    FROM factura_compra f JOIN d ON d.bol = f.bol
    GROUP BY f.bol
)
SELECT  f.bol,
        m.n_facturas,
        CASE WHEN m.n_estaciones > 1      THEN 'CARGA_PARTIDA'
             WHEN m.n_precios    > 1      THEN 'PRECIO_DISTINTO'
             ELSE 'DUPLICADA_EXACTA' END  AS clase,
        f.fecha_bol,
        COALESCE(e.alias, e.razon_social) AS estacion,
        f.num_factura,
        f.producto,
        f.litros,
        f.precio,
        ROUND(f.litros * f.precio, 2)     AS importe_calculado
FROM    factura_compra f
JOIN    m        ON m.bol = f.bol
JOIN    estacion e ON e.id = f.estacion_id
ORDER BY f.fecha_bol, f.bol, f.num_factura;

-- ---------------------------------------------------------------------
-- meta
-- ---------------------------------------------------------------------
INSERT INTO meta (clave, valor) VALUES
 ('factura_compra_fuente',
  'Facturas.csv del operador. 8,790 facturas, 2024-01-02 a 2026-09-23, 13 estaciones, 256,361,925 litros. El origen traia el producto por codigo (1=DIESEL, 2=PREMIUM, 3=REGULAR) y tambien por texto; los dos concuerdan en el 100% de los renglones, pero el texto venia con mayusculas inconsistentes, asi que se derivo del codigo.'),
 ('factura_compra_alcance',
  'OJO: el origen NO trae proveedor, ni IVA, ni IEPS, ni el total facturado. Es el detalle de compra de combustible, NO cuentas por pagar. Para conciliar contra contabilidad hace falta el importe con impuestos.'),
 ('factura_compra_precio',
  'precio trae de 3 a 8 decimales y NO se redondeo: la precision es real y el importe depende de ella. Es distinto de venta_diaria.precio_venta, que si se redondeo a 2 decimales.'),
 ('factura_compra_peps',
  'El operador costea con capas estilo PEPS por estacion. El orden determinista de entrada es (fecha_bol, num_factura): num_factura es secuencial en todo el archivo y desempata dos pipas del mismo dia. El indice ix_factura_peps esta hecho para eso. Falta una capa inicial: las compras arrancan el 2024-01-02 y lo que habia en los tanques el 1 de enero tiene costo desconocido.'),
 ('boletas_repetidas',
  '18 boletas tienen mas de una factura. Ver v_boleta_repetida. Siete son DUPLICADA_EXACTA (misma estacion, producto, litros y precio con dos folios) y CINCO DE ESAS SIETE son del 2026-06-10: es un problema de captura de ese dia, no azar. La boleta 210206 tiene CUATRO facturas. Dos casos del 2026-09-21 (BOL 210476 AURORA y 210474 QL) son PRECIO_DISTINTO: misma boleta y litros facturados a 20.377129 y a 21.348613, casi un peso de diferencia. Ninguna se excluyo de la tabla.'),
 ('compras_vs_ventas',
  'Validacion cruzada 2024-2026: los litros comprados y vendidos cuadran dentro del 1-2% en las doce estaciones activas, lo que valida las dos fuentes de forma independiente. La excepcion es TREHER LL: compro 1,007,000 litros en 2024 con CERO ventas registradas, y sus facturas arrancan el 2024-08-12, cinco meses antes de su primera venta. Lo mas probable es que FALTEN las ventas de TREHER LL de agosto a diciembre de 2024 y que la estacion haya abierto a mediados de 2024, no en enero de 2025. PENDIENTE de verificar con el operador.')
ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
