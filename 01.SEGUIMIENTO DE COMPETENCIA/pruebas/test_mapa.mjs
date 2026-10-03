/* Pruebas del mapa en un navegador real (etapas 5, 7 y 8).
 *
 * OPCIONAL: necesita Node y Playwright, que no hacen falta para usar la
 * aplicacion. Se corre asi, con el servidor ya levantado en el puerto 8000:
 *
 *     python -m pruebas.esperado        (calcula los valores desde SQL)
 *     npm i playwright && npx playwright install chromium
 *     node pruebas/test_mapa.mjs
 *
 * Contrasta lo que la interfaz MUESTRA contra lo que sale de consultar la
 * base por otro camino. Coincidir por casualidad seria muy raro.
 */
import { chromium } from 'playwright';
import { readFileSync } from 'fs';
const esp = JSON.parse(readFileSync(new URL('./esperado.json', import.meta.url), 'utf8'));
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000/';
let fallas = 0;
const check = (n, ok, det='') => { console.log(`  [${ok?'OK  ':'FALLA'}] ${n}${det?'  -> '+det:''}`); if(!ok) fallas++; };

const b = await chromium.launch();
try {
  const pg = await b.newPage({ viewport: { width: 1440, height: 980 } });
  const errores = [];
  pg.on('pageerror', e => errores.push('PAGEERROR: ' + e.message));
  await pg.route('**tile.openstreetmap.org**', r => r.abort());
  await pg.goto(BASE, { waitUntil: 'domcontentloaded' });
  await pg.waitForFunction(() => window.__app && Object.keys(window.__app.marcadores).length > 0);

  // ---------------- TREHER T (id 1)
  console.log('\n1. TREHER T — radio completo');
  await pg.evaluate(() => window.__app.seleccionar(1));
  await pg.waitForSelector('#radioRango');
  await pg.waitForTimeout(400);
  const e1 = esp['1'];
  check('el deslizador arranca en el tope del set',
        await pg.inputValue('#radioRango') === String(e1.tope), await pg.inputValue('#radioRango'));
  check('muestra los 3 confirmados',
        (await pg.textContent('#radioCuenta')).includes(`${e1.n_total} de ${e1.n_total}`),
        (await pg.textContent('#radioCuenta')).trim());
  const fila = async (p) => (await pg.textContent(`table.metricas tr:has(th:text-is("${p}"))`)).replace(/\s+/g,' ').trim();
  const r1 = await fila('REG');
  const m1 = e1.REGULAR_full;
  check('promedio de regular', r1.includes(`$${m1.prom.toFixed(2)}`), r1);
  check('mínimo de regular',   r1.includes(`$${m1.min.toFixed(2)}`), m1.min);
  check('máximo de regular',   r1.includes(`$${m1.max.toFixed(2)}`), m1.max);
  check('n=3',                 r1.includes('n=3'));
  check('diferencia absoluta', r1.includes(m1.dif.toFixed(2)), m1.dif);
  check('diferencia porcentual', r1.includes(m1.pct.toFixed(1)+'%'), m1.pct+'%');

  console.log('\n2. TREHER T — radio a 2.0 km');
  await pg.evaluate(() => window.__app.aplicarRadio(2.0));
  await pg.waitForTimeout(300);
  const e1b = e1.REGULAR_2km;
  check('ahora son 2 de 3',
        (await pg.textContent('#radioCuenta')).includes(`${e1.n_en_2km} de ${e1.n_total}`),
        (await pg.textContent('#radioCuenta')).trim());
  const r1b = await fila('REG');
  check('el promedio se recalculó', r1b.includes(`$${e1b.prom.toFixed(2)}`), r1b);
  check('n=2', r1b.includes('n=2'));
  check('la diferencia se recalculó', r1b.includes(e1b.dif.toFixed(2)), e1b.dif);
  check('la tabla ya solo lista 2',
        await pg.evaluate(() => document.querySelectorAll('#tablaComp tr').length - 1) === e1.n_en_2km);
  check('avisa que con pocos el promedio es débil',
        (await pg.textContent('#comparacion')).includes('no es una estadística'));

  // ---------------- IXTAZACUALA (id 9): dos competidores fuera del radio
  console.log('\n3. IXTAZACUALA — los que el operador agregó fuera del radio');
  await pg.evaluate(() => window.__app.seleccionar(9));
  await pg.waitForSelector('#radioRango');
  await pg.waitForTimeout(400);
  const e9 = esp['9'];
  check('el tope llega a 6.5 km, no al radio de 2',
        await pg.inputValue('#radioRango') === String(e9.tope), await pg.inputValue('#radioRango'));
  check('los 3 se muestran de entrada',
        (await pg.textContent('#radioCuenta')).includes('3 de 3'));
  check('marca los 2 que están fuera del radio',
        await pg.evaluate(() => document.querySelectorAll('#tablaComp .fuera').length) === e9.fuera_radio,
        e9.fuera_radio);
  check('la nota explica el radio de descubrimiento',
        (await pg.textContent('#panelContenido')).includes('radio de descubrimiento de esta estación es de 2'));
  const r9 = await fila('REG');
  check('promedio con n=2', r9.includes(`$${e9.REGULAR_full.prom.toFixed(2)}`) && r9.includes('n=2'), r9);
  check('IXTAZACUALA sale más cara (+)', r9.includes('+' + e9.REGULAR_full.dif.toFixed(2)), e9.REGULAR_full.dif);

  console.log('\n4. IXTAZACUALA — radio a 2.0 km: solo queda uno, y sin precio');
  await pg.evaluate(() => window.__app.aplicarRadio(2.0));
  await pg.waitForTimeout(300);
  check('1 de 3', (await pg.textContent('#radioCuenta')).includes('1 de 3'));
  check('dice que no hay comparación posible',
        (await pg.textContent('#comparacion')).includes('sin comparación posible'));
  check('y el único que queda es GPDC, sin precio',
        (await pg.textContent('#tablaComp')).includes('GPDC'));

  console.log('\n5. Radio en cero');
  await pg.evaluate(() => window.__app.aplicarRadio(0));
  await pg.waitForTimeout(250);
  check('0 de 3', (await pg.textContent('#radioCuenta')).includes('0 de 3'));
  check('lo dice sin romperse',
        (await pg.textContent('#comparacion')).includes('Ningún competidor confirmado dentro de este radio'));

  console.log('\nerrores de JS:', errores.length ? errores : 'ninguno');
  if (errores.length) fallas += errores.length;
} finally { await b.close(); }
console.log('\n' + '='.repeat(60));
console.log(fallas ? `FALLARON ${fallas}` : 'TODAS LAS PRUEBAS PASARON');
process.exit(fallas ? 1 : 0);
