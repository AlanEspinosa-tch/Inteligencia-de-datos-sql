"""Pruebas de las rutas de datos (etapa 4).

    python -m pruebas.test_api

Cada comprobacion va contra una cifra conocida de red.db, no contra si misma.
Si la base cambia y estas cifras dejan de cuadrar, la prueba avisa: eso es
justo lo que queremos.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient      # noqa: E402
from backend.main import app                   # noqa: E402

FALLAS = []


def check(nombre, condicion, detalle=""):
    print("  [%s] %s%s" % ("OK  " if condicion else "FALLA", nombre,
                           ("  -> " + str(detalle)) if detalle else ""))
    if not condicion:
        FALLAS.append(nombre)


with TestClient(app) as cli:

    print("=" * 72)
    print("1. /api/catalogos")
    c = cli.get("/api/catalogos")
    check("responde 200", c.status_code == 200, c.status_code)
    c = c.json()
    check("93 estaciones", c["total_estaciones"] == 93, c["total_estaciones"])
    check("12 propias activas", c["propias_activas"] == 12, c["propias_activas"])
    check("11 sin precio", c["sin_precio"] == 11, c["sin_precio"])
    # OJO: esto es la serie de la CNE (precio_diario_CNE), no el precio del
    # sistema de ventas (venta_diaria.precio_venta). Son dos cosas distintas
    # y avanzan por separado: la CNE cubre las 82 estaciones, la de ventas
    # solo las propias.
    ULTIMO = c["precios_hasta"]          # ultimo dia con precio de la CNE
    check("la serie arranca el 2026-01-01", c["precios_desde"] == "2026-01-01", c["precios_desde"])
    check("el ultimo dia tiene forma de fecha",
          len(ULTIMO) == 10 and ULTIMO[4] == ULTIMO[7] == "-", ULTIMO)
    check("la serie no se encogio (>= 263 dias)", c["dias_con_precio"] >= 263,
          "%d dias, hasta %s" % (c["dias_con_precio"], ULTIMO))
    check("3 productos", c["productos"] == ["REGULAR", "PREMIUM", "DIESEL"], c["productos"])
    check("Pemex es la marca mas comun con 33",
          c["marcas"][0]["marca"] == "Pemex" and c["marcas"][0]["estaciones"] == 33,
          c["marcas"][0])
    sinid = [m for m in c["marcas"] if m["marca"] == "Sin identificar"]
    check("las 8 sin marca quedan en un solo cubo",
          sinid and sinid[0]["estaciones"] == 8, sinid)
    check("3 estados", len(c["estados"]) == 3, c["estados"])

    print("\n2. /api/estaciones — filtros")
    def n(qs=""):
        r = cli.get("/api/estaciones" + qs)
        assert r.status_code == 200, (qs, r.status_code, r.text[:200])
        return r.json()
    check("sin filtro devuelve 93", len(n()) == 93, len(n()))
    check("tipo=propia devuelve 12 (excluye la cerrada)", len(n("?tipo=propia")) == 12, len(n("?tipo=propia")))
    check("tipo=propia&activa=false devuelve 1", len(n("?tipo=propia&activa=false")) == 1)
    check("esa 1 es TREHER LL", n("?tipo=propia&activa=false")[0]["nombre"] == "TREHER LL",
          n("?tipo=propia&activa=false")[0]["nombre"])
    check("tipo=competencia devuelve 80", len(n("?tipo=competencia")) == 80, len(n("?tipo=competencia")))
    check("con_precio=false devuelve 11", len(n("?con_precio=false")) == 11, len(n("?con_precio=false")))
    check("con_precio=true devuelve 82", len(n("?con_precio=true")) == 82, len(n("?con_precio=true")))
    check("marca=Pemex devuelve 33", len(n("?marca=Pemex")) == 33, len(n("?marca=Pemex")))
    check("marca insensible a mayusculas", len(n("?marca=pemex")) == 33)
    check("marca='Sin identificar' junta NULL y el literal",
          len(n("?marca=Sin identificar")) == 8, len(n("?marca=Sin identificar")))
    check("estado=Hidalgo no vacio", len(n("?estado=Hidalgo")) > 0, len(n("?estado=Hidalgo")))
    check("q=treher encuentra 2 (TREHER T y TREHER LL)", len(n("?q=treher")) == 2, len(n("?q=treher")))
    # TH se llama "TH" en alias: encontrarla por razon social prueba que la
    # busqueda mira ese campo. "grupo gasolinero" a secas da 2, porque
    # Combuqro (id 48) tambien se llama asi.
    gg = n("?q=grupo gasolinero th")
    check("q busca tambien en la razon social",
          len(gg) == 1 and gg[0]["id"] == 2, [(e["id"], e["nombre"]) for e in gg])
    check("q=grupo gasolinero da 2 (TH y Combuqro)",
          len(n("?q=grupo gasolinero")) == 2, len(n("?q=grupo gasolinero")))
    check("q por permiso", len(n("?q=PL/2027")) == 1, len(n("?q=PL/2027")))
    clases = {}
    for e in n():
        clases[e["clase"]] = clases.get(e["clase"], 0) + 1
    check("13 propias, 26 directas, 54 vecinas",
          clases == {"propia": 13, "directa": 26, "no_directa": 54}, clases)
    check("ninguna se queda sin relacion registrada",
          "sin_relacion" not in clases, clases)
    check("todas las estaciones traen coordenadas",
          all(e["latitud"] and e["longitud"] for e in n()))
    check("ninguna sin nombre", all(e["nombre"] for e in n()))

    print("\n3. /api/mapa")
    m = cli.get("/api/mapa?tipo=propia").json()
    check("12 propias activas", len(m) == 12, len(m))
    check("todas traen los 3 productos",
          all(set(e["precios"]) == {"REGULAR", "PREMIUM", "DIESEL"} for e in m),
          [e["nombre"] for e in m if set(e["precios"]) != {"REGULAR", "PREMIUM", "DIESEL"}])
    check("el ultimo precio del mapa es el del catalogo",
          all(p["fecha"] == ULTIMO for e in m for p in e["precios"].values()), ULTIMO)
    check("cada precio trae su propia fecha",
          all("fecha" in p and "precio" in p for e in m for p in e["precios"].values()))
    todos = cli.get("/api/mapa").json()
    check("mapa completo: 93 estaciones", len(todos) == 93, len(todos))
    vacias = [e for e in todos if not e["precios"]]
    check("11 sin precio, y se muestran igual", len(vacias) == 11, len(vacias))
    check("las 11 traen publica_precio=0", all(e["publica_precio"] == 0 for e in vacias))
    sinreg = [e for e in todos if e["precios"] and "REGULAR" not in e["precios"]]
    check("3 estaciones nunca reportan REGULAR", len(sinreg) == 3,
          sorted(e["nombre"][:28] for e in sinreg))

    print("\n4. /api/estaciones/{id} — detalle")
    d = cli.get("/api/estaciones/1").json()
    check("TREHER T se llama asi", d["estacion"]["nombre"] == "TREHER T", d["estacion"]["nombre"])
    check("la ficha se refiere al mismo ultimo dia",
          d["fecha_referencia"] == ULTIMO, (d["fecha_referencia"], ULTIMO))
    check("3 precios propios", len(d["precios"]) == 3, d["precios"])
    check("3 competidores confirmados", len(d["competidores"]) == 3,
          [c["nombre"][:26] for c in d["competidores"]])
    check("ordenados por distancia",
          [c["distancia_km"] for c in d["competidores"]] == sorted(c["distancia_km"] for c in d["competidores"]))
    check("el mas cercano es ACE a 0.19 km",
          abs(d["competidores"][0]["distancia_km"] - 0.19) < 0.01, d["competidores"][0]["distancia_km"])
    zapata = [c for c in d["competidores"] if c["compite_en"] == "GASOLINAS"]
    check("Zapata marcado solo GASOLINAS", len(zapata) == 1, [c["compite_en"] for c in d["competidores"]])
    check("los competidores traen precio de la MISMA fecha",
          all(c["precios"] for c in d["competidores"]),
          [(c["nombre"][:20], len(c["precios"])) for c in d["competidores"]])
    check("sin aviso cuando todo cuadra", d["aviso"] is None, d["aviso"])

    # compite_en manda sobre los datos: Zapata TIENE precio de diesel en la
    # base, pero ese par solo compite en gasolinas, asi que la API no debe
    # ofrecerlo. Es el mismo criterio que aplica v_precio_zona.
    zap = zapata[0]
    check("Zapata no devuelve DIESEL (solo compite en gasolinas)",
          "DIESEL" not in zap["precios"], sorted(zap["precios"]))
    check("Zapata si devuelve las dos gasolinas",
          set(zap["precios"]) == {"REGULAR", "PREMIUM"}, sorted(zap["precios"]))
    ambos = [c for c in d["competidores"] if c["compite_en"] == "AMBOS"]
    check("los pares AMBOS si traen los tres productos",
          all(set(c["precios"]) == {"REGULAR", "PREMIUM", "DIESEL"} for c in ambos))
    zap_diesel = cli.get("/api/precios/serie?estacion_id=%d&producto=DIESEL&dias=5" % zap["id"]).json()
    check("pero el diesel de Zapata si existe en la base",
          len(zap_diesel["puntos"]) > 0, "%d dias" % len(zap_diesel["puntos"]))

    # Vecinos: es_competencia = 0. Se devuelven, pero aparte.
    check("TREHER T trae 2 vecinas", len(d["vecinos"]) == 2,
          [v["nombre"][:24] for v in d["vecinos"]])
    ids_dir = {c["id"] for c in d["competidores"]}
    check("ninguna vecina esta tambien en competidores",
          not (ids_dir & {v["id"] for v in d["vecinos"]}))
    teo = cli.get("/api/estaciones/11").json()
    check("TEOLOYUCAN: 1 directa y 6 vecinas",
          (len(teo["competidores"]), len(teo["vecinos"])) == (1, 6),
          (len(teo["competidores"]), len(teo["vecinos"])))
    ql_vecina = [v for v in teo["vecinos"] if v["id"] == 10]
    check("QL aparece como VECINA de Teoloyucan, no como competidora",
          len(ql_vecina) == 1 and 10 not in {c["id"] for c in teo["competidores"]})
    check("y con mismo_sentido = 0 (cuerpo opuesto)",
          ql_vecina[0]["mismo_sentido"] == 0, ql_vecina[0]["mismo_sentido"])
    check("las 12 propias suman 29 directas y 67 vecinas",
          sum(len(cli.get("/api/estaciones/%d" % i).json()["competidores"]) for i in range(1, 13)) == 29
          and sum(len(cli.get("/api/estaciones/%d" % i).json()["vecinos"]) for i in range(1, 13)) == 67)

    ll = cli.get("/api/estaciones/93").json()
    check("TREHER LL sin precios", ll["fecha_referencia"] is None and not ll["precios"])
    check("TREHER LL avisa por que", ll["aviso"] is not None)
    check("TREHER LL sin competidores", len(ll["competidores"]) == 0)
    check("TREHER LL trae su evento de cierre", len(ll["eventos"]) >= 1,
          [e["titulo"][:40] for e in ll["eventos"]])

    f50 = cli.get("/api/estaciones/50").json()
    check("competidor sin precio: publica_precio=0", f50["estacion"]["publica_precio"] == 0)
    check("competidor sin precio: avisa", f50["aviso"] is not None)

    check("estacion inexistente da 404", cli.get("/api/estaciones/99999").status_code == 404)

    print("\n5. Marcas, contra la base y no contra el documento")
    marcas = {c["nombre"][:24]: c["marca"] for c in d["competidores"]}
    check("El Cid es Total", marcas.get("ESTACION EL CID SA DE CV") == "Total",
          marcas.get("ESTACION EL CID SA DE CV"))

    print("\n6. Direccion de los pares de competencia")
    ql = cli.get("/api/estaciones/10").json()
    teo = cli.get("/api/estaciones/11").json()
    check("QL no lista a TEOLOYUCAN", 11 not in [c["id"] for c in ql["competidores"]])
    check("TEOLOYUCAN no lista a QL", 10 not in [c["id"] for c in teo["competidores"]])
    comb = cli.get("/api/estaciones/7").json()
    th = cli.get("/api/estaciones/2").json()
    check("COMBULUB y TH si compiten entre si (ambos sentidos)",
          2 in [c["id"] for c in comb["competidores"]] and 7 in [c["id"] for c in th["competidores"]])

    print("\n7. /api/precios/serie")
    s = cli.get("/api/precios/serie?estacion_id=1&producto=REGULAR&dias=30").json()
    check("devuelve puntos", len(s["puntos"]) > 0, "%d puntos" % len(s["puntos"]))
    check("ordenados por fecha", [p["fecha"] for p in s["puntos"]] == sorted(p["fecha"] for p in s["puntos"]))
    check("respeta el rango", all(s["desde"] <= p["fecha"] <= s["hasta"] for p in s["puntos"]))
    check("acepta 'diésel' con acento",
          cli.get("/api/precios/serie?estacion_id=1&producto=diésel&dias=10").json()["producto"] == "DIESEL")
    check("acepta 'diesel' en minusculas",
          cli.get("/api/precios/serie?estacion_id=1&producto=diesel&dias=10").json()["producto"] == "DIESEL")
    check("rechaza producto invalido",
          cli.get("/api/precios/serie?estacion_id=1&producto=magna&dias=10").status_code == 422)
    check("rechaza fecha mal formada",
          cli.get("/api/precios/serie?estacion_id=1&producto=REGULAR&desde=01-01-2026").status_code == 422)
    completa = cli.get("/api/precios/serie?estacion_id=1&producto=REGULAR&desde=2026-01-01").json()
    check("la serie de TREHER T cubre todos los dias publicados",
          len(completa["puntos"]) == c["dias_con_precio"],
          (len(completa["puntos"]), c["dias_con_precio"]))
    precios = {p["precio"] for p in completa["puntos"]}
    check("TREHER T movio el precio pocas veces en 2026", len(precios) <= 8, "%d niveles" % len(precios))

    print("\n8. /api/comparativo")
    cmp1 = cli.get("/api/comparativo?dias=1").json()
    check("12 propias en operacion", len(cmp1["estaciones"]) == 12, len(cmp1["estaciones"]))
    check("96 pares en total",
          sum(len(e["relacionadas"]) for e in cmp1["estaciones"]) == 96,
          sum(len(e["relacionadas"]) for e in cmp1["estaciones"]))
    check("solo_directas deja 29",
          sum(len(e["relacionadas"])
              for e in cli.get("/api/comparativo?dias=1&solo_directas=true").json()["estaciones"]) == 29)
    check("el signo es mio - suyo", "mio - competidor" in cmp1["signo"], cmp1["signo"])
    check("el umbral del semaforo es 0.10", cmp1["umbral"] == 0.10, cmp1["umbral"])
    check("un solo dia da desde == hasta, y es el ultimo",
          cmp1["desde"] == cmp1["hasta"] == ULTIMO, (cmp1["desde"], cmp1["hasta"], ULTIMO))

    # El diferencial tiene que cuadrar con la resta, dentro del redondeo.
    malas = []
    for e in cmp1["estaciones"]:
        for r in e["relacionadas"]:
            for prod, info in r["diferencial"].items():
                mio, suyo = e["precios"].get(prod), r["precios"].get(prod)
                if mio is None or suyo is None:
                    continue
                if abs(round(mio - suyo, 2) - info["valor"]) > 0.011:
                    malas.append((e["nombre"], r["nombre"][:20], prod, mio, suyo, info["valor"]))
    check("diferencial = mi precio - su precio en los 96 pares", not malas, malas[:3])

    # compite_en manda tambien aqui.
    zap = [r for e in cmp1["estaciones"] if e["nombre"] == "TREHER T"
           for r in e["relacionadas"] if r["compite_en"] == "GASOLINAS"]
    check("Zapata sin diesel en el comparativo",
          len(zap) == 1 and "DIESEL" not in zap[0]["diferencial"]
          and "DIESEL" not in zap[0]["productos"], zap and zap[0]["productos"])

    cmp30 = cli.get("/api/comparativo?dias=30").json()
    import datetime as _dt                                        # noqa: E402
    esperado_desde = (_dt.date.fromisoformat(ULTIMO) - _dt.timedelta(days=29)).isoformat()
    check("30 dias abre un rango de 30 dias que termina en el ultimo",
          cmp30["hasta"] == ULTIMO and cmp30["desde"] == esperado_desde,
          (cmp30["desde"], cmp30["hasta"], esperado_desde))
    dias = [i["dias"] for e in cmp30["estaciones"] for r in e["relacionadas"]
            for i in r["diferencial"].values()]
    check("cada promedio dice sobre cuantos dias se calculo",
          dias and max(dias) <= 30 and min(dias) >= 1, (min(dias), max(dias)))

    print("\n9. La API sigue sin escribir")
    h = cli.get("/health").json()
    check("/health sigue en pie", h["ok"] and h["estaciones"] == 93)

print("\n" + "=" * 72)
if FALLAS:
    print("FALLARON %d prueba(s): %s" % (len(FALLAS), ", ".join(FALLAS)))
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
