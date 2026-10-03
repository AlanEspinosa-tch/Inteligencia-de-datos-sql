/* Pruebas de la tabla comparativa y del layout (navegador real).
 *
 * OPCIONAL: necesita Node y Playwright, que NO hacen falta para usar la
 * aplicacion. Con el servidor levantado:
 *
 *     npm i playwright && npx playwright install chromium
 *     node pruebas/test_tabla.mjs
 *
 * Verifica el semaforo de 10 centavos celda por celda, que el signo del
 * diferencial cuadre con la resta de las columnas que la propia tabla
 * muestra, y que el encabezado pegajoso no tape la primera fila.
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
  await pg.waitForFunction(() => window.__app && Object.keys(window.__app.marcadores).length > 0);
  await pg.waitForTimeout(900);

  console.log('\n1. Estructura');
  ck('12 grupos, uno por propia activa',
     await pg.evaluate(() => document.querySelectorAll('td.base').length) === 12);
  ck('96 filas = los 96 pares de relacion_estacion',
     await pg.evaluate(() => document.querySelectorAll('table.comparativo tbody tr').length) === 96);
  ck('orden de columnas DIE · PRE · REG',
     (await pg.evaluate(() => [...document.querySelectorAll('thead tr:last-child th')].map(t=>t.textContent)))
       .join(',') === 'DIE,PRE,REG,DIE,PRE,REG,DIE,PRE,REG');
  ck('el mapa conserva altura util',
     await pg.evaluate(() => document.querySelector('.mapa-zona').getBoundingClientRect().height) >= 430,
     await pg.evaluate(() => Math.round(document.querySelector('.mapa-zona').getBoundingClientRect().height)) + 'px');
  ck('los 93 marcadores siguen ahi',
     await pg.evaluate(() => Object.keys(window.__app.marcadores).length) === 93);
  // Regresion: el encabezado pegajoso llego a taparle la primera fila.
  const solape = await pg.evaluate(() => {
    const th = document.querySelector('thead th');
    const f0 = document.querySelector('tbody tr');
    return Math.round(th.getBoundingClientRect().bottom - f0.getBoundingClientRect().top);
  });
  ck('el encabezado no tapa la primera fila', solape <= 0, solape + 'px de solape');
  ck('la primera fila es la directa mas cercana',
     (await pg.textContent('tbody tr .nom')).indexOf('SAN FRANCISCO') >= 0,
     await pg.textContent('tbody tr .nom'));

  console.log('\n2. El semáforo de 10 centavos');
  const sem = await pg.evaluate(() => {
    const mal = [];
    document.querySelectorAll('td.dif').forEach(td => {
      const t = td.textContent.trim();
      if (t === '—') return;
      const v = parseFloat(t);
      const verde = td.classList.contains('barato');
      const rojo  = td.classList.contains('caro');
      const ok = v <= -0.10 ? verde : (v >= 0.10 ? rojo : (!verde && !rojo));
      if (!ok) mal.push(t + ' verde=' + verde + ' rojo=' + rojo);
    });
    return { mal, total: document.querySelectorAll('td.dif').length };
  });
  ck('todas las celdas respetan el umbral', sem.mal.length === 0,
     sem.mal.length ? sem.mal.slice(0,5) : sem.total + ' celdas revisadas');
  ck('-0.10 exacto va en verde',
     await pg.evaluate(() => [...document.querySelectorAll('td.dif')]
       .some(td => td.textContent.trim() === '-0.10' && td.classList.contains('barato'))));
  ck('+0.10 exacto va en rojo',
     await pg.evaluate(() => [...document.querySelectorAll('td.dif')]
       .some(td => td.textContent.trim() === '+0.10' && td.classList.contains('caro'))));
  ck('-0.09 no se pinta',
     await pg.evaluate(() => [...document.querySelectorAll('td.dif')]
       .filter(td => Math.abs(parseFloat(td.textContent)) < 0.10 && td.textContent.trim() !== '—')
       .every(td => td.classList.contains('parejo'))));

  console.log('\n3. El signo coincide con la resta de las columnas (último día)');
  await pg.selectOption('#periodo', '1');
  await pg.waitForTimeout(900);
  const sign = await pg.evaluate(() => {
    const malas = [];
    document.querySelectorAll('table.comparativo tbody tr').forEach(tr => {
      const tds = [...tr.children];
      const base = tds.filter(t => t.classList.contains('mio'));
      if (!base.length) return;   // filas que heredan el rowspan
      const comp = tds.slice(-6);
      for (let i = 0; i < 3; i++) {
        const mio = parseFloat(base[i].textContent.replace('$',''));
        const suyo = parseFloat(comp[i].textContent.replace('$',''));
        const dif = parseFloat(comp[i+3].textContent);
        if (isNaN(mio) || isNaN(suyo) || isNaN(dif)) continue;
        if (Math.abs((mio - suyo) - dif) > 0.011) malas.push([mio, suyo, dif]);
      }
    });
    return malas;
  });
  ck('diferencial = mío − suyo en las filas verificables', sign.length === 0,
     sign.length ? sign.slice(0,3) : 'sin desviaciones');

  console.log('\n4. Periodo y filtro');
  ck('el pie dice que es un solo día',
     (await pg.textContent('#piePeriodo')).includes('Precios del'));
  await pg.selectOption('#periodo', '30'); await pg.waitForTimeout(900);
  ck('a 30 días dice promedio y advierte del desfase',
     (await pg.textContent('#piePeriodo')).includes('Promedio del') &&
     (await pg.textContent('#piePeriodo')).includes('no cuadrar exactamente'));
  await pg.check('#soloDirectas'); await pg.waitForTimeout(900);
  ck('solo directas deja 29 filas',
     await pg.evaluate(() => document.querySelectorAll('table.comparativo tbody tr').length) === 29,
     await pg.evaluate(() => document.querySelectorAll('table.comparativo tbody tr').length));
  ck('y ninguna vecina amarilla',
     await pg.evaluate(() => document.querySelectorAll('td.comp .tipo.nodirecta').length) === 0);
  await pg.uncheck('#soloDirectas'); await pg.waitForTimeout(800);

  console.log('\n5. Clic en la estación lleva al mapa');
  await pg.evaluate(() => document.querySelector('td.base').click());
  await pg.waitForSelector('#panel:not([hidden])', { timeout: 5000 });
  ck('abre la ficha en el mapa', true);
  console.log('\nerrores JS:', errs.length ? errs : 'ninguno');
  if (errs.length) f += errs.length;
  await pg.evaluate(() => window.scrollTo(0,0));
  await pg.waitForTimeout(400);
} finally { await b.close(); }
console.log('\n' + '='.repeat(56));
console.log(f ? `FALLARON ${f}` : 'TODAS LAS PRUEBAS PASARON');
process.exit(f ? 1 : 0);
