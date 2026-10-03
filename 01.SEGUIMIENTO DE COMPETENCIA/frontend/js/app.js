/* Red Treher — mapa de estaciones y competencia.
 *
 * Vanilla JS a proposito: una sola pantalla, sin build, sin dependencias
 * que mantener. Leaflet va dentro del proyecto (vendor/), no desde un CDN,
 * para que la aplicacion abra aunque la maquina no tenga internet. Los
 * mosaicos del mapa si necesitan red; si no hay, los marcadores se pintan
 * igual sobre un fondo vacio.
 *
 * Criterios que este archivo respeta:
 *
 *  - Una estacion que no publica precio SE MUESTRA. Marcador hueco y
 *    punteado, con su nota. Existe aunque no haya con que compararla.
 *  - Los pares de competencia son DIRIGIDOS y vienen resueltos del backend.
 *    Aqui no se infiere ninguno ni se dibuja al reves.
 *  - Los precios que se comparan son SIEMPRE de la misma fecha; la
 *    devuelve el backend como fecha_referencia. Nunca se mezclan dias.
 *  - No se inventa hora: la base solo guarda fecha.
 */

'use strict';

var PRODUCTOS = ['REGULAR', 'PREMIUM', 'DIESEL'];

/* Que productos disputa un par, segun compite_en. Hay pares que solo compiten
 * en gasolinas porque el cliente de diesel no se desvia por unos centavos.
 * El backend ya no manda esos precios; aqui se usa para explicar el hueco. */
var COMPITEN = {
  AMBOS: ['REGULAR', 'PREMIUM', 'DIESEL'],
  GASOLINAS: ['REGULAR', 'PREMIUM'],
  DIESEL: ['DIESEL']
};

var mapa, capaEstaciones, capaEnlaces, capaResaltado, capaRadio;
var marcadores = {};        // id -> CircleMarker
var estaciones = [];
var seleccionada = null;
var productoActivo = 'REGULAR';
var clasesRelativas = null;   // id -> clase, cuando hay una estacion seleccionada
var ZOOM_ETIQUETAS = 11;      // debajo de esto, solo el pin: 93 etiquetas no caben

/* Orden de la tabla comparativa, tomado del Excel del operador. NO es el
 * mismo que el de la ficha del mapa. */
var ORDEN_TABLA = ['DIESEL', 'PREMIUM', 'REGULAR'];
var rangoPrecios = null;      // limites del calendario, salen de /api/catalogos

/* Semaforo de la tabla: el operador lo prende a partir de 10 centavos.
 * Por debajo de eso la diferencia no mueve al cliente. */
var UMBRAL = 0.10;
var detalle = null;        // ultimo /api/estaciones/{id} recibido
var radioActual = 0;

/* Clases de marcador. El color sale de relacion_estacion.es_competencia:
 *   propia      -> pin azul con una V, las del grupo
 *   directa     -> rojo, es_competencia = 1
 *   no_directa  -> amarillo, es_competencia = 0: el radio la encontro pero el
 *                  operador determino que no compite
 *
 * Cinco estaciones son directa de una propia y no directa de otra, asi que
 * el color GLOBAL (el de /api/mapa) es "directa de al menos una". Al
 * seleccionar una estacion los colores se recalculan relativos a ella.
 */

// ---------------------------------------------------------------- utilidades

function pesos(v) {
  if (v === null || v === undefined) return null;
  return '$' + v.toFixed(2);
}

function fechaLarga(iso) {
  if (!iso) return '';
  var meses = ['enero','febrero','marzo','abril','mayo','junio','julio',
               'agosto','septiembre','octubre','noviembre','diciembre'];
  var p = iso.split('-');
  return parseInt(p[2], 10) + ' de ' + meses[parseInt(p[1], 10) - 1] + ' de ' + p[0];
}

function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}

function pedir(url) {
  return fetch(url).then(function (r) {
    if (!r.ok) throw new Error('HTTP ' + r.status + ' en ' + url);
    return r.json();
  });
}

function avisar(texto) {
  var el = document.getElementById('aviso');
  el.textContent = texto;
  el.hidden = false;
}

// -------------------------------------------------------------------- arranque

function iniciar() {
  // SVG y no canvas: con 93 marcadores el rendimiento es identico, y asi
  // cada punto es un elemento del DOM que se puede inspeccionar y probar.
  // zoomSnap en 0.25: por omision Leaflet redondea el zoom a enteros y el
  // encuadre inicial queda con mucho aire, porque la red se estira de
  // Queretaro a Hidalgo. Con pasos de cuarto ajusta de verdad.
  mapa = L.map('mapa', { zoomControl: true, zoomSnap: 0.25 });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; colaboradores de <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(mapa);

  capaRadio = L.layerGroup().addTo(mapa);
  capaEnlaces = L.layerGroup().addTo(mapa);
  capaResaltado = L.layerGroup().addTo(mapa);
  capaEstaciones = L.layerGroup().addTo(mapa);

  mapa.on('click', function (e) {
    if (!e.originalEvent.target.closest('.leaflet-marker-icon')) limpiarSeleccion();
  });
  mapa.on('zoomend', ajustarEtiquetas);
  document.getElementById('productos').addEventListener('change', function (ev) {
    if (ev.target.name === 'producto') cambiarProducto(ev.target.value);
  });
  document.getElementById('cerrarPanel').addEventListener('click', cerrarPanel);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { cerrarPanel(); limpiarSeleccion(); }
  });

  // Enganche para las pruebas automatizadas. No lo usa la interfaz: permite
  // abrir un popup o seleccionar una estacion sin depender de donde cayo el
  // pixel del marcador en pantalla.
  window.__app = { mapa: mapa, marcadores: marcadores, seleccionar: seleccionar,
                   estaciones: function () { return estaciones; },
                   aplicarRadio: function (r) { aplicarRadio(r); },
                   metricas: metricas,
                   detalle: function () { return detalle; } };

  document.getElementById('periodo').addEventListener('change', cargarComparativo);
  document.getElementById('soloDirectas').addEventListener('change', cargarComparativo);
  document.getElementById('fecha').addEventListener('change', cargarComparativo);
  document.getElementById('hoy').addEventListener('click', function () {
    if (!rangoPrecios) return;
    document.getElementById('fecha').value = rangoPrecios.hasta;
    cargarComparativo();
  });

  Promise.all([pedir('api/catalogos'), pedir('api/mapa')])
    .then(function (res) { resumen(res[0]); pintar(res[1]); mapa.invalidateSize(); })
    .catch(function (err) {
      avisar('No se pudo leer la API: ' + err.message +
             '. Revisa que el servidor siga corriendo y que RED_DB_PATH apunte a red.db.');
    });
}

function resumen(cat) {
  document.querySelector('.fecha').textContent =
    'Precios al ' + fechaLarga(cat.precios_hasta) + ' · ' + cat.dias_con_precio + ' días de historia';

  // El calendario de la tabla se limita al rango que existe en la base:
  // no tiene caso poder elegir un dia sin datos posibles.
  rangoPrecios = { desde: cat.precios_desde, hasta: cat.precios_hasta };
  var f = document.getElementById('fecha');
  f.min = cat.precios_desde;
  f.max = cat.precios_hasta;
  if (!f.value) f.value = cat.precios_hasta;
}

/* Los chips se arman desde las clases reales del mapa, no desde un conteo
 * aparte: asi no pueden contradecir lo que se ve pintado. */
function chips() {
  var n = { propia: 0, directa: 0, no_directa: 0, sin_relacion: 0 };
  var sinPrecio = 0;
  estaciones.forEach(function (e) {
    n[e.clase] = (n[e.clase] || 0) + 1;
    if (!e.publica_precio) sinPrecio++;
  });
  var h = '<span class="chip propias"><b>' + n.propia + '</b> mías</span>' +
          '<span class="chip directa"><b>' + n.directa + '</b> competencia directa</span>' +
          '<span class="chip nodirecta"><b>' + n.no_directa + '</b> vecinas</span>' +
          '<span class="chip"><b>' + sinPrecio + '</b> sin precio</span>';
  document.getElementById('chips').innerHTML = h;
}

// ------------------------------------------------------------------ marcadores

function claseDe(e) {
  if (clasesRelativas && clasesRelativas[e.id]) return clasesRelativas[e.id];
  if (clasesRelativas) return 'apagada';      // hay seleccion y esta no participa
  return e.clase || 'no_directa';
}

function precioDe(e) {
  var p = e.precios && e.precios[productoActivo];
  return p ? p.precio : null;
}

function crearIcono(e) {
  var clase = claseDe(e);
  var precio = precioDe(e);
  var propia = clase === 'propia';
  var sinPrecio = precio === null;

  var h = '';
  if (!sinPrecio) {
    h += '<div class="pill">$' + precio.toFixed(2) + '</div>';
  }
  h += '<div class="pin">' + (propia ? '<span>V</span>' : '') + '</div>';

  return L.divIcon({
    className: 'mk mk-' + clase + (sinPrecio ? ' mk-sin' : ''),
    html: h,
    iconSize: [88, propia ? 56 : 50],
    iconAnchor: [44, propia ? 56 : 50],
    popupAnchor: [0, propia ? -52 : -46]
  });
}

function refrescarIconos() {
  estaciones.forEach(function (e) {
    var m = marcadores[e.id];
    if (m) m.setIcon(crearIcono(e));
  });
  ordenarPorClase();
}

/* Las propias arriba de todo, luego las directas. Con divIcon el orden lo
 * da el zIndexOffset, no el orden de insercion. */
function ordenarPorClase() {
  var peso = { propia: 3000, directa: 2000, no_directa: 1000, sin_relacion: 500, apagada: 0 };
  estaciones.forEach(function (e) {
    var m = marcadores[e.id];
    if (m) m.setZIndexOffset(peso[claseDe(e)] || 0);
  });
}

function pintar(lista) {
  estaciones = lista;
  var puntos = [];

  lista.forEach(function (e) {
    var m = L.marker([e.latitud, e.longitud], {
      icon: crearIcono(e),
      title: e.nombre,
      riseOnHover: true
    });
    m.bindPopup(function () { return popup(e); }, { maxWidth: 300, autoPanPadding: [40, 40] });
    m.on('popupopen', function () {
      var b = document.querySelector('.pop-boton[data-id="' + e.id + '"]');
      if (b) b.addEventListener('click', function () { seleccionar(e.id); });
    });
    m.addTo(capaEstaciones);
    marcadores[e.id] = m;
    puntos.push([e.latitud, e.longitud]);
  });

  ordenarPorClase();
  chips();
  if (puntos.length) mapa.fitBounds(puntos, { padding: [60, 60] });
  else avisar('La API no devolvió ninguna estación.');
  ajustarEtiquetas();
}

function ajustarEtiquetas() {
  document.body.classList.toggle('sin-etiquetas', mapa.getZoom() < ZOOM_ETIQUETAS);
}

function cambiarProducto(prod) {
  productoActivo = prod;
  refrescarIconos();
  if (detalle) aplicarRadio(radioActual);
}

function popup(e) {
  var h = '<div class="pop-nombre">' + esc(e.nombre) + '</div>';

  var meta = [];
  if (e.marca) meta.push(esc(e.marca));
  if (e.municipio) meta.push(esc(e.municipio) + (e.estado ? ', ' + esc(e.estado) : ''));
  if (meta.length) h += '<div class="pop-meta">' + meta.join(' · ') + '</div>';
  if (e.domicilio) h += '<div class="pop-meta">' + esc(e.domicilio) + '</div>';

  var clase = claseDe(e);
  var etiqueta = {
    propia: ['propia', e.activa === 1 ? 'Estación propia' : 'Propia · cerrada'],
    directa: ['directa', 'Competencia directa'],
    no_directa: ['nodirecta', 'Vecina · no compite'],
    sin_relacion: ['nodirecta', 'Sin relación registrada'],
    apagada: ['nodirecta', 'Sin relación con la seleccionada']
  }[clase] || ['nodirecta', ''];
  if (clase === 'propia' && e.activa !== 1) etiqueta = ['cerrada', 'Propia · cerrada'];
  h += '<span class="pop-etiqueta ' + etiqueta[0] + '">' + etiqueta[1] + '</span>';

  var claves = Object.keys(e.precios);
  if (claves.length) {
    h += '<table class="precios">';
    PRODUCTOS.forEach(function (p) {
      if (!e.precios[p]) return;
      h += '<tr class="' + (p === productoActivo ? 'activo' : '') + '">' +
           '<th>' + p.charAt(0) + p.slice(1).toLowerCase() + '</th>' +
           '<td>' + pesos(e.precios[p].precio) + '</td></tr>';
    });
    h += '</table>';
    if (claves.length < 3) {
      var faltan = PRODUCTOS.filter(function (p) { return !e.precios[p]; });
      h += '<div class="pop-sin">No reporta ' + faltan.join(' ni ').toLowerCase() + '.</div>';
    }
    h += '<div class="pop-fecha">Precio del ' + fechaLarga(e.precios[claves[0]].fecha) + '</div>';
  } else {
    h += '<div class="pop-sin">No publica precios ante la CNE. Se ubica para tenerla ' +
         'presente, pero no hay con qué compararla.</div>';
  }

  if (e.es_propia === 1) {
    h += '<button class="pop-boton" data-id="' + e.id + '">Ver competencia</button>';
  }
  return h;
}

// ------------------------------------------------------------------ seleccion

function limpiarSeleccion() {
  capaEnlaces.clearLayers();
  capaResaltado.clearLayers();
  capaRadio.clearLayers();
  seleccionada = null;
  detalle = null;
  if (clasesRelativas) { clasesRelativas = null; refrescarIconos(); }
}

function cerrarPanel() {
  document.getElementById('panel').hidden = true;
}

function seleccionar(id) {
  limpiarSeleccion();
  seleccionada = id;
  pedir('api/estaciones/' + id)
    .then(function (d) {
      detalle = d;
      // El deslizador arranca abarcando TODO el set confirmado, no el
      // radio_km de la estacion. Hay pares que el operador agrego por
      // conocimiento local estando fuera del radio (Ixtazacuala tiene dos
      // a 4.68 y 6.46 km con radio de 2). Arrancar en radio_km los
      // escondería de entrada, que es justo lo contrario de lo que
      // queremos: el set es el criterio, el radio solo una lente.
      radioActual = topeRadio(d);
      llenarPanel(d);
      aplicarRadio(radioActual);
    })
    .catch(function (err) { avisar('No se pudo leer el detalle: ' + err.message); });
}

function relacionadas(d) {
  return d.competidores.concat(d.vecinos || []);
}

function topeRadio(d) {
  var todas = relacionadas(d);
  if (!todas.length) return 0;
  var max = Math.max.apply(null, todas.map(function (c) { return c.distancia_km; }));
  return Math.ceil(max * 10) / 10;
}

function dentroDelRadio(d, radio) {
  return d.competidores.filter(function (c) { return c.distancia_km <= radio + 1e-9; });
}

function vecinosDentro(d, radio) {
  return (d.vecinos || []).filter(function (c) { return c.distancia_km <= radio + 1e-9; });
}

/* Recolorea el mapa RELATIVO a la estacion seleccionada.
 *
 * Las propias se quedan azules siempre: son mis estaciones, aunque alguna sea
 * competencia de otra del grupo (Combulub y TH lo son). El resto toma el
 * color que le corresponde FRENTE A ESTA estacion, que no siempre es el
 * global: Zapata, Porcla, Servi Boulevard y El Encino son directa de una
 * propia y no directa de otra. */
function recolorearRelativo(d, dentro, vecinos) {
  var mapaClases = {};
  estaciones.forEach(function (e) {
    if (e.es_propia === 1) mapaClases[e.id] = 'propia';
  });
  dentro.forEach(function (c) { if (!mapaClases[c.id]) mapaClases[c.id] = 'directa'; });
  vecinos.forEach(function (c) { if (!mapaClases[c.id]) mapaClases[c.id] = 'no_directa'; });
  clasesRelativas = mapaClases;
  refrescarIconos();
}

/* Redibuja lo que depende del radio: mapa, metricas y tabla. */
function aplicarRadio(radio) {
  radioActual = radio;
  if (!detalle) return;
  var d = detalle;
  var dentro = dentroDelRadio(d, radio);
  var vecinos = vecinosDentro(d, radio);
  recolorearRelativo(d, dentro, vecinos);

  capaEnlaces.clearLayers();
  capaResaltado.clearLayers();
  capaRadio.clearLayers();

  var base = [d.estacion.latitud, d.estacion.longitud];
  if (radio > 0) {
    L.circle(base, {
      radius: radio * 1000, color: '#0f766e', weight: 1.5,
      opacity: .6, dashArray: '5 5', fillColor: '#0f766e', fillOpacity: .05
    }).addTo(capaRadio);
  }
  dentro.forEach(function (c) {
    L.polyline([base, [c.latitud, c.longitud]], {
      color: '#7c3aed', weight: 1.5, opacity: .55, dashArray: '4 4'
    }).addTo(capaEnlaces);
    L.circleMarker([c.latitud, c.longitud], {
      radius: 11, weight: 2.5, color: '#7c3aed', opacity: .85, fill: false
    }).addTo(capaResaltado);
  });

  var caja = document.getElementById('radioValor');
  if (caja) caja.textContent = radio.toFixed(1) + ' km';
  var cuenta = document.getElementById('radioCuenta');
  if (cuenta) {
    cuenta.innerHTML =
      '<b>' + dentro.length + '</b> de ' + d.competidores.length + ' directas' +
      ' · <b>' + vecinos.length + '</b> de ' + (d.vecinos || []).length + ' vecinas';
  }
  var tv = document.getElementById('tablaVecinos');
  if (tv) tv.innerHTML = htmlVecinos(vecinos);
  var comp = document.getElementById('comparacion');
  if (comp) comp.innerHTML = htmlComparacion(d, dentro);
  var tab = document.getElementById('tablaComp');
  if (tab) tab.innerHTML = htmlTabla(d, dentro);
}

function encuadrarSeleccion() {
  if (!detalle) return;
  var d = detalle;
  var dentro = dentroDelRadio(d, radioActual).concat(vecinosDentro(d, radioActual));
  var puntos = [[d.estacion.latitud, d.estacion.longitud]].concat(
    dentro.map(function (c) { return [c.latitud, c.longitud]; }));
  mapa.fitBounds(puntos, { padding: [90, 90], maxZoom: 14 });
}

/* ------------------------------------------------------- metricas (etapa 8)
 *
 * Se calculan sobre los competidores DENTRO del radio, y solo con los que
 * (a) disputan ese producto segun compite_en y (b) publicaron precio ese dia.
 * Con uno o dos competidores el "promedio" no es una estadistica: por eso
 * siempre se muestra n, sin disfrazarlo.
 */
function metricas(mio, competidores, producto) {
  var v = [];
  competidores.forEach(function (c) {
    var x = c.precios[producto];
    if (x !== undefined && x !== null) v.push(x);
  });
  if (!v.length) return null;
  var suma = v.reduce(function (a, b) { return a + b; }, 0);
  var prom = suma / v.length;
  var m = {
    n: v.length,
    promedio: prom,
    minimo: Math.min.apply(null, v),
    maximo: Math.max.apply(null, v),
    masBaratos: v.filter(function (x) { return x < mio; }).length,
    masCaros: v.filter(function (x) { return x > mio; }).length
  };
  if (mio !== undefined && mio !== null) {
    m.dif = mio - prom;
    m.difPct = prom !== 0 ? (mio - prom) / prom * 100 : null;
  }
  return m;
}

function claseDif(v) { return v > 0.004 ? 'caro' : (v < -0.004 ? 'barato' : 'igual'); }

/* Con signo, pero sin "-0.00": una diferencia que redondea a cero es cero,
 * y el menos delante sugiere una ventaja que no existe. */
function conSigno(v, dec) {
  var r = Number(v.toFixed(dec));
  if (r === 0) return (0).toFixed(dec);
  return (r > 0 ? '+' : '') + r.toFixed(dec);
}

function htmlComparacion(d, dentro) {
  if (!dentro.length) {
    return '<div class="nota">Ningún competidor confirmado dentro de este radio.</div>';
  }
  var filas = '', hubo = false;
  PRODUCTOS.forEach(function (prod) {
    var mio = d.precios[prod];
    var m = metricas(mio, dentro, prod);
    if (!m) {
      filas += '<tr><th>' + prod.slice(0, 3) + '</th>' +
               '<td colspan="5" class="nd">sin comparación posible</td></tr>';
      return;
    }
    hubo = true;
    var difTxt = '<span class="nd">—</span>';
    if (m.dif !== undefined) {
      var cl = claseDif(m.dif);
      difTxt = '<span class="dif ' + cl + '">' + conSigno(m.dif, 2) +
               '<br><small>' + conSigno(m.difPct, 1) + '%</small></span>';
    }
    filas += '<tr><th>' + prod.slice(0, 3) + '</th>' +
             '<td>' + (mio === undefined ? '<span class="nd">—</span>' : pesos(mio)) + '</td>' +
             '<td>' + pesos(m.promedio) + '<br><small class="nd">n=' + m.n + '</small></td>' +
             '<td>' + pesos(m.minimo) + '</td>' +
             '<td>' + pesos(m.maximo) + '</td>' +
             '<td>' + difTxt + '</td></tr>';
  });

  var h = '<table class="metricas">' +
          '<tr><th></th><th>Mío</th><th>Prom.</th><th>Mín.</th><th>Máx.</th><th>Dif.</th></tr>' +
          filas + '</table>';

  if (hubo) {
    // Posicion, solo de regular: es el producto de mayor rotacion y el que
    // el operador usa para leer la plaza.
    var mr = metricas(d.precios.REGULAR, dentro, 'REGULAR');
    if (mr && d.precios.REGULAR !== undefined) {
      var frase;
      if (mr.masCaros === mr.n) frase = 'En regular soy el más barato de este radio.';
      else if (mr.masBaratos === mr.n) frase = 'En regular soy el más caro de este radio.';
      else frase = 'En regular hay ' + mr.masBaratos + ' más barato' +
                   (mr.masBaratos === 1 ? '' : 's') + ' y ' + mr.masCaros + ' más caro' +
                   (mr.masCaros === 1 ? '' : 's') + ' que yo.';
      h += '<div class="nota">' + frase +
           ' <b>Dif.</b> es mi precio menos el promedio de la competencia.' +
           (mr.n < 3 ? ' Ojo: con ' + mr.n + ' competidor' + (mr.n === 1 ? '' : 'es') +
                       ' el promedio no es una estadística, es casi el dato suelto.' : '') +
           '</div>';
    }
  }
  return h;
}

/* Los vecinos NO entran en las metricas. Se listan aparte, sin diferencial,
 * porque poner un "+0.12" al lado invitaria justo a la comparacion que el
 * operador descarto. Lo que si se muestra es POR QUE no compite. */
function htmlVecinos(vecinos) {
  if (!vecinos.length) {
    return '<div class="nota">Ninguna vecina registrada dentro de este radio.</div>';
  }
  var h = '<table class="comp vecinos"><tr><th>Estación</th><th>' +
          productoActivo.slice(0, 3) + '</th></tr>';
  vecinos.forEach(function (c) {
    var etiquetas = [c.distancia_km.toFixed(2) + ' km'];
    if (c.marca) etiquetas.push(esc(c.marca));
    if (c.es_propia) etiquetas.push('del grupo');
    if (c.mismo_sentido === 0) etiquetas.push('cuerpo contrario');
    var precio = c.precios[productoActivo];
    h += '<tr><td><div class="nom">' + esc(c.nombre) + '</div>' +
         '<div class="km">' + etiquetas.join(' · ') + '</div></td>' +
         '<td>' + (precio === undefined ? '<span class="nd">—</span>' : pesos(precio)) +
         '</td></tr>';
  });
  return h + '</table>';
}

function htmlTabla(d, dentro) {
  if (!dentro.length) return '';
  var h = '<table class="comp"><tr><th>Estación</th>';
  PRODUCTOS.forEach(function (p) { h += '<th>' + p.slice(0, 3) + '</th>'; });
  h += '</tr>';

  dentro.forEach(function (c) {
    var etiquetas = [c.distancia_km.toFixed(2) + ' km'];
    if (c.marca) etiquetas.push(esc(c.marca));
    if (c.compite_en && c.compite_en !== 'AMBOS') etiquetas.push('solo ' + c.compite_en.toLowerCase());
    if (c.es_propia) etiquetas.push('del grupo');
    h += '<tr><td><div class="nom">' + esc(c.nombre) + '</div>' +
         '<div class="km">' + etiquetas.join(' · ');
    if (!c.en_radio) {
      h += '<br><span class="fuera" title="Fuera del radio de descubrimiento; ' +
           'el operador la agregó por conocimiento de la plaza">fuera del radio</span>';
    }
    h += '</div></td>';

    var disputa = COMPITEN[c.compite_en || 'AMBOS'] || PRODUCTOS;
    PRODUCTOS.forEach(function (p) {
      var suyo = c.precios[p], mio = d.precios[p];
      if (disputa.indexOf(p) === -1) {
        h += '<td class="nd" title="Este par no compite en ' + p.toLowerCase() + '">n/c</td>';
        return;
      }
      if (suyo === undefined) {
        h += '<td class="nd" title="No publicó precio ese día">—</td>';
        return;
      }
      var t = pesos(suyo);
      if (mio !== undefined) {
        var dif = Math.round((mio - suyo) * 100) / 100;
        t += '<div class="dif ' + claseDif(dif) + '">' + conSigno(dif, 2) + '</div>';
      }
      h += '<td>' + t + '</td>';
    });
    h += '</tr>';
  });
  return h + '</table>';
}

/* -------------------------------------------------------------------- panel */

function llenarPanel(d) {
  var e = d.estacion;
  var h = '<h2>' + esc(e.nombre) + '</h2>';

  var meta = [];
  if (e.marca) meta.push(esc(e.marca));
  if (e.municipio) meta.push(esc(e.municipio) + (e.estado ? ', ' + esc(e.estado) : ''));
  h += '<div class="meta">' + meta.join(' · ');
  if (e.domicilio) h += '<br>' + esc(e.domicilio);
  h += '<br>Permiso ' + esc(e.permiso) + '</div>';

  // --- mis precios
  h += '<h3>Mis precios</h3><div class="mios">';
  PRODUCTOS.forEach(function (p) {
    var v = d.precios[p];
    h += '<div class="mio"><div class="p">' + p + '</div><div class="v' +
         (v === undefined ? ' nd' : '') + '">' +
         (v === undefined ? 'sin dato' : pesos(v)) + '</div></div>';
  });
  h += '</div>';
  if (d.fecha_referencia) {
    h += '<div class="nota">Todos los precios de esta ficha son del <b>' +
         fechaLarga(d.fecha_referencia) + '</b>. Se comparan solo dentro del mismo día: ' +
         'contrastar cierres de fechas distintas no diría nada.</div>';
  }

  // --- radio
  var tope = topeRadio(d);
  var nVecinos = (d.vecinos || []).length;
  if (relacionadas(d).length) {
    h += '<h3>Radio de comparación</h3>' +
         '<div class="radio">' +
           '<input type="range" id="radioRango" min="0" max="' + tope + '" step="0.1" ' +
                  'value="' + tope + '" aria-label="Radio en kilómetros">' +
           '<output id="radioValor">' + tope.toFixed(1) + ' km</output>' +
         '</div>' +
         '<div class="radio-cuenta" id="radioCuenta"></div>';
    var fuera = d.competidores.filter(function (c) { return !c.en_radio; }).length;
    var nota = 'Filtra sobre las <b>' + relacionadas(d).length + ' estaciones relacionadas</b> ' +
               'con esta: ' + d.competidores.length + ' competencia directa ' +
               '(<span class="punto directa"></span> rojas) y ' + nVecinos +
               ' vecinas registradas que <b>no compiten</b> ' +
               '(<span class="punto nodirecta"></span> amarillas).';
    if (e.radio_km) {
      nota += ' Su radio de descubrimiento es de ' + e.radio_km + ' km';
      nota += fuera ? ', y ' + fuera + ' de sus directas quedan fuera de él.' : '.';
    }
    h += '<div class="nota">' + nota + '</div>';
  }

  // --- comparacion y tabla, las llena aplicarRadio()
  if (d.competidores.length) {
    h += '<h3>Comparación de precios</h3><div id="comparacion"></div>';
    h += '<h3>Competencia directa</h3><div id="tablaComp"></div>';
    h += '<div class="nota">El número bajo cada precio es mi precio menos el suyo. ' +
         'En <span class="dif caro">rojo</span> estoy más caro; en ' +
         '<span class="dif barato">verde</span>, más barato.<br>' +
         '<b>—</b> es que no publicó precio ese día. <b>n/c</b> es que ese par ' +
         'no compite en ese producto, por criterio del operador.</div>';
  } else if (e.es_propia === 1) {
    h += '<h3>Competencia confirmada</h3>' +
         '<div class="nota">Esta estación no tiene competidores registrados.</div>';
  }

  if (nVecinos) {
    h += '<h3>Vecinas que no compiten (' + nVecinos + ')</h3>' +
         '<div id="tablaVecinos"></div>' +
         '<div class="nota">Están registradas porque el radio las encontró, pero ' +
         '<b>no entran en ninguna métrica</b>: meter en un “promedio de competencia” ' +
         'a quien decidiste que no compite corrompe el número. Se muestran para ' +
         'tenerlas ubicadas y sirven de grupo de control.</div>';
  }

  if (d.aviso) h += '<div class="nota alerta">' + esc(d.aviso) + '</div>';

  // --- eventos
  if (d.eventos.length) {
    h += '<h3>Eventos (' + d.eventos.length + ')</h3><ul class="eventos">';
    d.eventos.forEach(function (ev) {
      var rango = ev.fecha_inicio
        ? fechaLarga(ev.fecha_inicio) + (ev.fecha_fin ? ' → ' + fechaLarga(ev.fecha_fin) : ' → en curso')
        : 'sin fecha';
      h += '<li><span class="t">' + esc(ev.titulo) + '</span>' +
           '<span class="rol">' + esc(ev.rol) + '</span>' +
           '<div class="d">' + rango + (ev.fecha_estimada ? ' (estimada)' : '') +
           (ev.efecto ? ' · ' + esc(ev.efecto) : '') + '</div></li>';
    });
    h += '</ul>';
  }

  var panel = document.getElementById('panel');
  document.getElementById('panelContenido').innerHTML = h;
  panel.hidden = false;
  panel.scrollTop = 0;

  var rango = document.getElementById('radioRango');
  if (rango) {
    rango.addEventListener('input', function () { aplicarRadio(parseFloat(this.value)); });
    rango.addEventListener('change', encuadrarSeleccion);
  }
}

/* ==================================================== tabla comparativa
 *
 * Copia el formato del Excel del operador: una fila por par, agrupadas por
 * estacion propia, con el orden DIESEL / PREMIUM / REGULAR.
 *
 * SIGNO: diferencial = mi precio - su precio, el mismo que usa la ficha del
 * mapa. Positivo = estoy mas caro. El semaforo se prende a los 10 centavos.
 */

function cargarComparativo() {
  var dias = document.getElementById('periodo').value;
  var solo = document.getElementById('soloDirectas').checked;
  var hasta = document.getElementById('fecha').value;
  var caja = document.getElementById('comparativo');
  caja.innerHTML = '<div class="cargando">Cargando…</div>';
  pedir('api/comparativo?dias=' + dias + '&solo_directas=' + solo +
        (hasta ? '&hasta=' + hasta : ''))
    .then(pintarComparativo)
    .catch(function (err) {
      caja.innerHTML = '<div class="cargando">No se pudo cargar: ' + esc(err.message) + '</div>';
    });
}

function celdaDif(info) {
  if (!info) return '<td class="dif vacio">—</td>';
  var v = Number(info.valor.toFixed(2));
  var clase = v <= -UMBRAL ? 'barato' : (v >= UMBRAL ? 'caro' : 'parejo');
  return '<td class="dif ' + clase + '" title="' + info.dias +
         (info.dias === 1 ? ' día comparado' : ' días comparados') + '">' +
         conSigno(v, 2) + '</td>';
}

function pintarComparativo(d) {
  var h = '<table class="comparativo"><thead>' +
    '<tr>' +
      '<th class="grupo" rowspan="2">Estación</th>' +
      '<th class="grupo" colspan="3">Mis precios</th>' +
      '<th class="grupo sep" rowspan="2">Competencia</th>' +
      '<th class="grupo" colspan="3">Sus precios</th>' +
      '<th class="grupo sep" colspan="3">Diferencial</th>' +
    '</tr><tr>';
  for (var b = 0; b < 3; b++) {
    ORDEN_TABLA.forEach(function (p, i) {
      h += '<th class="p' + p + (b > 0 && i === 0 ? ' sep' : '') + '">' +
           p.slice(0, 3) + '</th>';
    });
  }
  h += '</tr></thead><tbody>';

  var filas = 0;
  d.estaciones.forEach(function (e) {
    var rel = e.relacionadas;
    if (!rel.length) {
      h += '<tr class="inicio-grupo"><td class="base" data-id="' + e.id + '">' + esc(e.nombre) +
           '<span class="mun">' + esc(e.municipio || '') + '</span></td>' +
           '<td colspan="9" class="txt vacio">Sin estaciones relacionadas.</td></tr>';
      return;
    }
    rel.forEach(function (c, i) {
      filas++;
      h += '<tr' + (i === 0 ? ' class="inicio-grupo"' : '') + '>';
      if (i === 0) {
        h += '<td class="base" rowspan="' + rel.length + '" data-id="' + e.id + '">' +
             esc(e.nombre) + '<span class="mun">' + esc(e.municipio || '') + '</span></td>';
        ORDEN_TABLA.forEach(function (p) {
          var v = e.precios[p];
          h += '<td class="mio" rowspan="' + rel.length + '">' +
               (v === undefined ? '<span class="vacio">—</span>' : pesos(v)) + '</td>';
        });
      }
      h += '<td class="comp txt' + (i === 0 ? '' : ' sep') + '">' +
           '<span class="tipo ' + (c.es_competencia ? 'directa' : 'nodirecta') + '"></span>' +
           '<span class="nom">' + esc(c.nombre) + '</span>' +
           '<div class="km">' + c.distancia_km.toFixed(2) + ' km' +
           (c.marca ? ' · ' + esc(c.marca) : '') +
           (c.es_propia ? ' · del grupo' : '') +
           (c.compite_en && c.compite_en !== 'AMBOS' ? ' · solo ' + c.compite_en.toLowerCase() : '') +
           '</div></td>';

      ORDEN_TABLA.forEach(function (p, j) {
        var cl = j === 0 ? ' sep' : '';
        if (c.productos.indexOf(p) === -1) { h += '<td class="nc' + cl + '">n/c</td>'; return; }
        var v = c.precios[p];
        h += '<td class="' + (v === undefined ? 'vacio' : '') + cl + '">' +
             (v === undefined ? '—' : pesos(v)) + '</td>';
      });
      ORDEN_TABLA.forEach(function (p, j) {
        if (c.productos.indexOf(p) === -1) { h += '<td class="nc' + (j === 0 ? ' sep' : '') + '">n/c</td>'; return; }
        var celda = celdaDif(c.diferencial[p]);
        h += j === 0 ? celda.replace('class="dif', 'class="sep dif') : celda;
      });
      h += '</tr>';
    });
  });
  h += '</tbody></table>';

  document.getElementById('comparativo').innerHTML = h;
  document.querySelectorAll('td.base').forEach(function (td) {
    td.addEventListener('click', function () {
      var id = parseInt(td.dataset.id, 10);
      seleccionar(id);
      mapa.setView(marcadores[id].getLatLng(), 13);
      document.querySelector('.mapa-zona').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  var conPrecio = d.estaciones.filter(function (e) { return Object.keys(e.precios).length; }).length;
  var aviso = document.getElementById('avisoFecha');
  if (!conPrecio) {
    if (!aviso) {
      aviso = document.createElement('div');
      aviso.id = 'avisoFecha';
      aviso.className = 'sin-datos';
      document.getElementById('comparativo').after(aviso);
    }
    aviso.innerHTML = d.dias_pedidos === 1
      ? 'Ninguna estación publicó precio el <b>' + fechaLarga(d.hasta) + '</b>. ' +
        'Al archivo de la CNE le faltan cuatro fechas completas de 2026: 3 y 23 de mayo, ' +
        '4 de agosto y 3 de septiembre. Es la captura, no las estaciones.'
      : 'No hay precios entre el ' + fechaLarga(d.desde) + ' y el ' + fechaLarga(d.hasta) + '.';
    aviso.hidden = false;
  } else if (aviso) {
    aviso.hidden = true;
  }

  var periodo = d.dias_pedidos === 1
    ? 'Precios del ' + fechaLarga(d.hasta)
    : 'Promedio del ' + fechaLarga(d.desde) + ' al ' + fechaLarga(d.hasta);
  document.getElementById('piePeriodo').innerHTML =
    periodo + ' · ' + filas + ' pares. ' +
    '<b>Diferencial = mi precio menos el suyo</b>, igual que en la ficha del mapa: ' +
    'positivo significa que estoy más caro. El color se prende a partir de 10 centavos. ' +
    '<b>—</b> es que no hubo precio; <b>n/c</b> es que ese par no compite en ese producto.' +
    (d.dias_pedidos > 1
      ? '<br><b>Sobre los promedios:</b> cada diferencial se promedia solo sobre los días en que ' +
        'las dos estaciones publicaron — pasa el cursor sobre un número para ver cuántos días ' +
        'entraron. Las columnas de precio, en cambio, promedian cada estación por su cuenta. ' +
        'Por eso un diferencial puede no cuadrar exactamente con la resta de las dos columnas: ' +
        'el diferencial es el dato bueno, porque nunca mezcla fechas.'
      : '');
}

document.addEventListener('DOMContentLoaded', function () {
  iniciar();
  cargarComparativo();
});
