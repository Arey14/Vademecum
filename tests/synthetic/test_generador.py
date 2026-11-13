"""Tests del generador de pacientes sintéticos (integración con la base real del vademécum)."""
import random
import sqlite3

import pytest
from sqlmodel import Session, select

from src.config import GRAPH_DB_PATH
from src.synthetic import generador
from src.synthetic.catalogo import Catalogo
from src.synthetic.conducta import ParametrosConducta, decidir
from src.synthetic.generador import FECHA_REFERENCIA, Config, generar_cohorte, particion, seed_paciente
from src.synthetic.gt import GtEvento, GtPaciente, GtProblema, GtToma
from src.synthetic.redactor import HechoEvento, RedactorPlantillas, _typo
from src.synthetic.validacion import adherencia_registrada, adherencia_verdadera, validar_cohorte
from src.treatment.adherence import CUMPLIDA, FUERA_DE_VENTANA, clasificar_toma
from src.treatment.db import get_engine
from src.treatment.models import EstadoToma, EventoPaciente, TipoEvento, TomaProgramada

pytestmark = pytest.mark.skipif(not GRAPH_DB_PATH.exists(), reason="falta la base del vademécum")
AHORA = FECHA_REFERENCIA


@pytest.fixture(scope="module")
def catalogo():
    return Catalogo()


@pytest.fixture(scope="module")
def cohorte(tmp_path_factory):
    d = tmp_path_factory.mktemp("sint")
    generar_cohorte(d / "t.db", d / "g.db", n=10, seed=7)
    return d


@pytest.fixture()
def sesiones(cohorte):
    from src.synthetic.gt import get_gt_engine
    with Session(get_engine(cohorte / "t.db")) as s, Session(get_gt_engine(cohorte / "g.db")) as g:
        yield s, g


# --- catálogo ---------------------------------------------------------------- #
def test_catalogo_solo_productos_de_un_principio_y_pares_ambulatorios(catalogo):
    assert len(catalogo.productos) > 1000
    ambulatorias = {p.sustancia for lista in catalogo._por_patologia.values() for p in lista}
    assert catalogo.pares_interaccion
    for a, b in catalogo.pares_interaccion[:500]:
        assert a in catalogo._por_sustancia and b in catalogo._por_sustancia
    con = sqlite3.connect(f"file:{GRAPH_DB_PATH}?mode=ro", uri=True)
    ref = next(iter(catalogo.productos))
    assert con.execute("SELECT COUNT(*) FROM producto_sustancia WHERE producto_ref=?", (ref,)).fetchone()[0] == 1
    assert ambulatorias


# --- determinismo, aislamiento y partición ---------------------------------- #
def test_misma_semilla_misma_cohorte(tmp_path, cohorte, sesiones):
    generar_cohorte(tmp_path / "t.db", tmp_path / "g.db", n=3, seed=7)
    s, _ = sesiones
    with Session(get_engine(tmp_path / "t.db")) as s2:
        for modelo in (EventoPaciente,):
            a = [(e.paciente_id, e.texto_original, e.fecha_evento) for e in s.exec(select(modelo)).all() if e.paciente_id <= 4]
            b = [(e.paciente_id, e.texto_original, e.fecha_evento) for e in s2.exec(select(modelo)).all()]
            assert a == b and a  # los pacientes 2..4 de la cohorte grande == los de la chica
        from src.treatment.models import Medicacion
        ma = [(m.paciente_id, m.producto_ref, m.tipo_pauta) for m in s.exec(select(Medicacion)).all() if m.paciente_id <= 4]
        mb = [(m.paciente_id, m.producto_ref, m.tipo_pauta) for m in s2.exec(select(Medicacion)).all()]
        assert ma == mb


def test_semilla_distinta_cohorte_distinta(tmp_path, sesiones):
    generar_cohorte(tmp_path / "t.db", tmp_path / "g.db", n=2, seed=99)
    s, _ = sesiones
    with Session(get_engine(tmp_path / "t.db")) as s2:
        from src.treatment.models import Medicacion
        assert [m.producto_ref for m in s2.exec(select(Medicacion)).all()] != \
               [m.producto_ref for m in s.exec(select(Medicacion)).all()][:len(s2.exec(select(Medicacion)).all())]


def test_la_verdad_no_esta_en_la_base_del_sistema(cohorte):
    t = sqlite3.connect(cohorte / "t.db")
    g = sqlite3.connect(cohorte / "g.db")
    tablas_t = {r[0] for r in t.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tablas_g = {r[0] for r in g.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any(n.startswith("gt_") for n in tablas_t)
    assert tablas_g and all(n.startswith("gt_") for n in tablas_g)


def test_no_pisa_una_cohorte_existente(tmp_path, cohorte):
    with pytest.raises(FileExistsError):
        generar_cohorte(cohorte / "t.db", tmp_path / "g2.db", n=1, seed=1)


def test_particion_fija_e_independiente_de_la_semilla(sesiones):
    assert [particion(i) for i in range(50)] == [particion(i) for i in range(50)]
    frac = sum(particion(i) == "test" for i in range(2000)) / 2000
    assert 0.25 < frac < 0.35
    _, g = sesiones
    for p in g.exec(select(GtPaciente)).all():
        assert p.split == particion(p.indice)
    assert seed_paciente(1, 5) != seed_paciente(2, 5) and seed_paciente(1, 5) == seed_paciente(1, 5)


# --- validez y coherencia verdad ↔ registro -------------------------------- #
def test_validar_cohorte_ok(sesiones, catalogo):
    s, g = sesiones
    rep = validar_cohorte(s, g, catalogo, AHORA)
    assert rep["ok"], rep["errores"]
    assert rep["n_pacientes"] == 10 and sum(rep["por_split"].values()) == 10
    assert all(1 <= k <= 8 for k in rep["n_medicamentos"])
    assert 0 < rep["adherencia_verdadera_media"] < 1


def test_registro_coherente_con_la_verdad(sesiones):
    s, g = sesiones
    ids = {t.id: t for t in s.exec(select(TomaProgramada)).all()}
    verdades = g.exec(select(GtToma)).all()
    assert verdades
    for v in verdades:
        t = ids[v.toma_id]
        if v.registro == "tildada":
            assert t.estado == EstadoToma.TOMADA and t.fecha_hora_real is not None and v.resultado != "omitida"
            esperado = CUMPLIDA if v.resultado == "tomada_en_hora" else FUERA_DE_VENTANA
            assert clasificar_toma(t, AHORA) == esperado
        elif v.registro == "marcada_omitida":
            assert t.estado == EstadoToma.OMITIDA and v.resultado == "omitida"
        else:
            assert t.estado == EstadoToma.PENDIENTE and t.fecha_hora_real is None
        assert (v.desvio_min is None) == (v.resultado == "omitida")
        assert (v.motivo is not None) == (v.resultado == "omitida")


def test_lo_registrado_nunca_supera_a_la_verdad(sesiones):
    s, g = sesiones
    for p in g.exec(select(GtPaciente)).all():
        v = adherencia_verdadera(g, p.paciente_id)
        r = adherencia_registrada(s, g, p.paciente_id, AHORA)
        assert r <= v + 1e-9


def test_eventos_tienen_verdad_y_el_sistema_no_la_conoce(sesiones):
    s, g = sesiones
    eventos = s.exec(select(EventoPaciente)).all()
    assert eventos
    verdad = {e.evento_id: e for e in g.exec(select(GtEvento)).all()}
    for e in eventos:
        assert e.texto_original.strip() and e.id in verdad
        assert e.tipo == TipoEvento.OTRO and e.producto_ref is None and e.extraccion is None
        if verdad[e.id].tipo == "toma_fuera_de_esquema":
            assert verdad[e.id].producto_ref and verdad[e.id].nombre_mencionado


# --- problemas sembrados ----------------------------------------------------- #
@pytest.mark.parametrize("tipo,cfg", [
    ("interaccion", Config(dias=10, p_interaccion=1.0, p_duplicidad=0.0)),
    ("duplicidad", Config(dias=10, p_interaccion=0.0, p_duplicidad=1.0)),
])
def test_siembra_de_problemas(tmp_path, catalogo, tipo, cfg):
    generar_cohorte(tmp_path / "t.db", tmp_path / "g.db", n=4, seed=3, cfg=cfg)
    from src.synthetic.gt import get_gt_engine
    from src.treatment.models import Medicacion
    with Session(get_engine(tmp_path / "t.db")) as s, Session(get_gt_engine(tmp_path / "g.db")) as g:
        problemas = [p for p in g.exec(select(GtProblema)).all() if p.tipo == tipo and p.origen == "esquema"]
        assert len({p.paciente_id for p in problemas}) >= 3  # casi todos (a veces no hay lugar o par disponible)
        for p in problemas:
            sust = {x for m in s.exec(select(Medicacion).where(Medicacion.paciente_id == p.paciente_id)).all()
                    for x in m.principios_activos}
            assert set(p.entre) <= sust
            if tipo == "duplicidad":  # dos productos distintos con el mismo principio activo
                refs = [s.get(Medicacion, i).producto_ref for i in p.medicacion_ids]
                assert len(set(refs)) == 2
    if tipo == "interaccion":
        assert all(tuple(sorted(p.entre)) in set(catalogo.pares_interaccion) for p in problemas)


# --- conducta y redactor ----------------------------------------------------- #
def _params(**kw):
    base = dict(arquetipo="x", p_olvido=0.0, mult_noche=1.0, mult_finde=1.0, p_tarde=0.0, p_tilde=1.0,
                p_marca_omitida=1.0)
    return ParametrosConducta(**{**base, **kw})


def test_conducta_extremos():
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Argentina/Buenos_Aires")
    rng = random.Random(0)
    d = decidir(rng, _params(), AHORA, "pv-1", tz)
    assert d.resultado == "tomada_en_hora" and d.registro == "tildada" and -20 <= d.desvio_min <= 30
    ds = [decidir(rng, _params(p_olvido=1.0), AHORA, "pv-1", tz) for _ in range(2000)]
    omitidas = [d for d in ds if d.resultado == "omitida"]
    assert len(omitidas) / 2000 == pytest.approx(0.95, abs=0.02)  # el olvido tiene tope 0.95
    assert all(d.motivo == "olvido" and d.registro == "marcada_omitida" and d.desvio_min is None for d in omitidas)
    d = decidir(rng, _params(p_tarde=1.0), AHORA, "pv-1", tz)
    assert d.resultado == "tomada_tarde" and 61 <= d.desvio_min <= 180
    p = _params(abandono_ref="pv-1", abandono_desde=AHORA.isoformat())
    assert decidir(rng, p, AHORA, "pv-1", tz).motivo == "abandono"
    assert decidir(rng, p, AHORA, "pv-2", tz).resultado == "tomada_en_hora"  # otro medicamento


def test_conducta_noche_y_finde_aumentan_el_olvido():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Argentina/Buenos_Aires")
    p = _params(p_olvido=0.2, mult_noche=3.0, mult_finde=2.0, p_marca_omitida=0.0)
    manana_lab = datetime(2026, 11, 17, 8, 0, tzinfo=tz)   # martes
    noche_finde = datetime(2026, 11, 21, 21, 0, tzinfo=tz)  # sábado
    def tasa(f):
        rng = random.Random(1)
        return sum(decidir(rng, p, f, "r", tz).resultado == "omitida" for _ in range(4000)) / 4000
    assert tasa(manana_lab) == pytest.approx(0.2, abs=0.03)
    assert tasa(noche_finde) == pytest.approx(0.95, abs=0.03)  # 0.2*3*2 = 1.2, tope 0.95


def test_redactor_plantillas_determinista_y_con_typos():
    r = RedactorPlantillas(p_typo=1.0, p_usar_sustancia=0.0)
    hecho = HechoEvento("toma_fuera_de_esquema", "IBUPIRAC 400", "Ibuprofeno", "dolor de cabeza")
    a = r.redactar(hecho, random.Random(5))
    assert a == r.redactar(hecho, random.Random(5))
    assert a.con_typo and a.nombre_mencionado != "ibupirac" and a.nombre_mencionado in a.texto
    sin = RedactorPlantillas(p_typo=0.0, p_usar_sustancia=0.0).redactar(hecho, random.Random(5))
    assert sin.nombre_mencionado == "ibupirac" and not sin.con_typo
    s = r.redactar(HechoEvento("sintoma", sintoma="tos"), random.Random(1))
    assert "tos" in s.texto and s.nombre_mencionado is None
    for w in ("ibuprofeno", "paracetamol"):
        assert abs(len(_typo(w, random.Random(2))) - len(w)) <= 1
    assert _typo("ab", random.Random(0)) == "ab"


def test_la_verdad_incluye_todo_par_del_esquema_con_interaccion(sesiones, catalogo):
    """Completitud: cada par de principios activos del esquema que figura en la tabla de
    interacciones está en gt_problema (no solo los sembrados)."""
    from itertools import combinations
    from src.treatment.models import Medicacion
    s, g = sesiones
    pares = set(catalogo.pares_interaccion)
    registrados = {(p.paciente_id, tuple(sorted(p.entre))) for p in g.exec(select(GtProblema)).all()
                   if p.tipo == "interaccion"}
    for pid in {p.paciente_id for p in g.exec(select(GtPaciente)).all()}:
        sust = {x for m in s.exec(select(Medicacion).where(Medicacion.paciente_id == pid)).all()
                for x in m.principios_activos}
        for a, b in combinations(sorted(sust), 2):
            if (a, b) in pares:
                assert (pid, (a, b)) in registrados, (pid, a, b)
