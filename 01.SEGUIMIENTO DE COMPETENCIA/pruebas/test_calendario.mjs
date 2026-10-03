/* Pruebas del calendario de la tabla comparativa.
 *
 * OPCIONAL: necesita Node y Playwright. Con el servidor levantado:
 *     node pruebas/test_calendario.mjs
 *
 * Incluye una de las cuatro fechas que le faltan al archivo de la CNE
 * (2026-05-03), para verificar que la aplicacion lo explique en vez de
 * mostrar una tabla vacia sin decir por que.
 */
import { chromium } from 'playwright';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000/';
let f = 0;
const ck = (n, ok, d='') => { console.log(`  [${ok?'OK  ':'FALLA'}] ${n}${d?'  -> '+d:''}`); if(!ok) f++; };
const b = await chromium.launch();
try {
  const pg = await b.newPage({ viewport: { width: 1600, height: 1000 } });
  const errs = []; pg.on('pageerror', e => errs.push(e.message));
  await pg.route('**tile.openstreetmap.org**', r => r.abort());
  await pg.goto(BASE, { waitUntil: 'domcontentloaded' });
  await pg.waitForSelector('table.comparativo');
  await pg.waitForFunction(() => document.getElementById('fecha').value !== '');
  await pg.waitForTimeout(600);

  console.log('\n1. El calendario');
  ck('arranca en el último día con precios',
     await pg.inputValue('#fecha') === '2026-09-24', await pg.inputValue('#fecha'));
  ck('no deja elegir antes del inicio de la serie',
     await pg.getAttribute('#fecha', 'min') === '2026-01-01', await pg.getAttribute('#fecha','min'));
  ck('ni después del último día',
     await pg.getAttribute('#fecha', 'max') === '2026-09-24');
  ck('el encabezado sigue con su fecha',
     (await pg.textContent('.fecha')).includes('24 de septiembre'),
     (await pg.textContent('.fecha')).trim());

  console.log('\n2. Un día cualquiera del pasado');
  await pg.selectOption('#periodo', '1');
  await pg.fill('#fecha', '2026-03-17'); await pg.dispatchEvent('#fecha', 'change');
  await pg.waitForTimeout(900);
  ck('el pie muestra esa fecha',
     (await pg.textContent('#piePeriodo')).includes('17 de marzo de 2026'),
     (await pg.textContent('#piePeriodo')).slice(0, 46));
  const p17 = await pg.textContent('table.comparativo tbody tr td.mio');
  ck('trae precios de ese día', p17.includes('$'), p17.trim());

  console.log('\n3. El promedio respeta la fecha elegida');
  await pg.selectOption('#periodo', '30'); await pg.waitForTimeout(900);
  ck('promedia los 30 días que terminan ahí',
     (await pg.textContent('#piePeriodo')).includes('al 17 de marzo de 2026') &&
     (await pg.textContent('#piePeriodo')).includes('16 de febrero'),
     (await pg.textContent('#piePeriodo')).slice(0, 62));

  console.log('\n4. Una de las cuatro fechas que le faltan al feed');
  await pg.selectOption('#periodo', '1');
  await pg.fill('#fecha', '2026-05-03'); await pg.dispatchEvent('#fecha', 'change');
  await pg.waitForTimeout(900);
  ck('lo dice en vez de mostrar una tabla vacía sin explicación',
     await pg.isVisible('#avisoFecha') &&
     (await pg.textContent('#avisoFecha')).includes('faltan cuatro fechas'),
     (await pg.textContent('#avisoFecha')).slice(0, 60));

  console.log('\n5. El botón Último');
  await pg.click('#hoy'); await pg.waitForTimeout(900);
  ck('regresa al 24 de septiembre', await pg.inputValue('#fecha') === '2026-09-24');
  ck('y el aviso se esconde', !(await pg.isVisible('#avisoFecha')));
  ck('la tabla vuelve a traer datos',
     (await pg.textContent('table.comparativo tbody tr td.mio')).includes('$'));

  console.log('\nerrores JS:', errs.length ? errs : 'ninguno');
  if (errs.length) f += errs.length;
  await pg.waitForTimeout(500);
} finally { await b.close(); }
console.log('\n' + '='.repeat(56));
console.log(f ? `FALLARON ${f}` : 'TODAS LAS PRUEBAS PASARON');
process.exit(f ? 1 : 0);
