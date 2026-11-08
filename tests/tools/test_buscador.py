"""Búsqueda de medicamentos (H-05). Unitarios con una base mínima + integración con la base real."""
import json
import sqlite3
import time

import pytest

from src.config import GRAPH_DB_PATH
from src.tools.buscador import (
    AMBIGUO,
    DIFUSO,
    NO_ENCONTRADO,
    RESUELTO,
    Buscador,
    buscar_medicamento,
    normalizar,
)


# --------------------------------------------------------------------------- #
# Normalización
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("SINTROM®", "sintrom"),
        ("  Losartán  ", "losartan"),
        ("Acetilsalicílico ácido", "acetilsalicilico acido"),
        ("IBUPIRAC 600 Cápsulas blandas", "ibupirac 600 capsulas blandas"),
        ("COZAAREX D 100/12.5MG", "cozaarex d 100 12 5mg"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalizar(texto, esperado):
    assert normalizar(texto) == esperado


# --------------------------------------------------------------------------- #
# Unitarios sobre una base mínima y controlada
# --------------------------------------------------------------------------- #
PRODUCTOS = [
    ("pv-1", "SINTROM®", "SIEGFRIED", ["Acenocumarol"]),
    ("pv-2", "IBUPIRAC", "PFIZER", ["Ibuprofeno"]),
    ("pv-3", "IBUPIRAC 600", "PFIZER", ["Ibuprofeno"]),
    ("pv-4", "AMOXICILINA SANT GALL FRIBURG", "SANT GALL", ["Amoxicilina"]),  # contiene "ibu" adentro
    ("pv-5", "TAFIROL 1g", "GENOMMA", ["Paracetamol"]),
    ("pv-6", "TAFIROL FLEX", "GENOMMA", ["Paracetamol", "Orfenadrina"]),
    ("pv-7", "ACIMED", "MEDISOL", ["Omeprazol"]),
    ("pv-8", "ACIMED", "LEPETIT", ["Omeprazol"]),
    ("pv-9", "IBUPROFENO ROSPAW 400 VL", "ROSPAW", ["Ibuprofeno"]),
    ("pv-10", "ASPIRINA PREVENT 100", "BAYER", ["Acetilsalicílico ácido"]),
    ("pv-11", "PRODUCTO SIN COMPOSICION", "X", []),
    ("pv-12", "PRODUCTO SIN COMPOSICION B", "X", []),
]
SUSTANCIAS = ["Acenocumarol", "Ibuprofeno", "Amoxicilina", "Paracetamol", "Orfenadrina",
              "Omeprazol", "Acetilsalicílico ácido"]


@pytest.fixture(scope="module")
def buscador(tmp_path_factory):
    ruta = tmp_path_factory.mktemp("bd") / "g.db"
    con = sqlite3.connect(ruta)
    con.executescript(
        """
        CREATE TABLE productos (producto_ref TEXT PRIMARY KEY, nombre_producto TEXT, laboratorio_nombre TEXT);
        CREATE TABLE producto_sustancia (producto_ref TEXT, sustancia_name TEXT);
        CREATE TABLE sustancias (nombre TEXT);
        """
    )
    for ref, nombre, lab, principios in PRODUCTOS:
        con.execute("INSERT INTO productos VALUES (?,?,?)", (ref, nombre, lab))
        con.executemany("INSERT INTO producto_sustancia VALUES (?,?)", [(ref, p) for p in principios])
    con.executemany("INSERT INTO sustancias VALUES (?)", [(s,) for s in SUSTANCIAS])
    con.commit()
    con.close()
    return Buscador(ruta)


def test_marca_exacta_se_resuelve_ignorando_tildes_mayusculas_y_simbolos(buscador):
    for consulta in ("sintrom", "SINTROM®", "  Sintrom "):
        r = buscador.buscar(consulta)
        assert r.estado == RESUELTO and r.elegido.ref == "pv-1" and r.elegido.motivo == "exacto"


def test_H05_ibu_no_devuelve_un_producto_que_solo_contiene_ibu_adentro(buscador):
    r = buscador.buscar("ibu")
    assert r.estado == AMBIGUO and r.elegido is None
    nombres = [c.nombre for c in r.candidatos]
    assert "AMOXICILINA SANT GALL FRIBURG" not in nombres
    assert all(n.upper().startswith("IBU") for n in nombres)
    assert r.candidato_para_analisis is None  # con 3 letras nunca se sigue sin preguntar


def test_sustancia_exacta_se_resuelve_como_sustancia_y_no_como_un_producto_cualquiera(buscador):
    r = buscador.buscar("Amoxicilina")
    assert r.estado == RESUELTO
    assert r.elegido.tipo == "sustancia" and r.elegido.nombre == "Amoxicilina"


def test_alias_y_acidos_invertidos(buscador):
    for consulta in ("aspirina", "acido acetilsalicilico", "ácido acetilsalicílico"):
        r = buscador.buscar(consulta)
        assert r.estado == RESUELTO, consulta
        assert r.elegido.nombre == "Acetilsalicílico ácido" and r.elegido.motivo == "alias", consulta


def test_empate_con_la_misma_composicion_es_ambiguo_pero_utilizable(buscador):
    r = buscador.buscar("acimed")
    assert r.estado == AMBIGUO and r.n_empatados == 2 and r.misma_composicion
    assert {c.ref for c in r.candidatos[:2]} == {"pv-7", "pv-8"}
    assert r.candidato_para_analisis is not None


def test_empate_con_distinta_composicion_exige_elegir(buscador):
    r = buscador.buscar("tafirol")
    assert r.estado == AMBIGUO and r.n_empatados == 2 and not r.misma_composicion
    assert r.candidato_para_analisis is None


def test_un_prefijo_corto_con_empate_equivalente_no_se_usa_sin_preguntar(buscador):
    # "ibu": 4 candidatos, todos ibuprofeno, pero con 3 letras siempre se pide confirmar
    r = buscador.buscar("ibu")
    assert r.n_empatados > 1 and r.misma_composicion and r.candidato_para_analisis is None
    # con 4+ letras el mismo empate sí es utilizable
    r = buscador.buscar("ibup")
    assert r.misma_composicion and r.candidato_para_analisis is not None


def test_en_un_empate_exacto_la_sustancia_va_primero(buscador):
    # "Ibuprofeno" es una sustancia y no hay producto con ese nombre exacto: se resuelve.
    # Con un producto homónimo la sustancia debe ganar el desempate (ver test de integración).
    r = buscador.buscar("ibuprofeno")
    assert r.candidatos[0].tipo == "sustancia"


def test_un_error_de_tipeo_nunca_se_resuelve_solo(buscador):
    for consulta in ("tafirrol", "ibupirak", "sintrum"):
        r = buscador.buscar(consulta)
        assert r.estado == AMBIGUO and r.elegido is None, consulta
        assert r.candidatos[0].motivo == DIFUSO, consulta
        assert r.candidato_para_analisis is None, consulta
        assert "¿Quiso decir" in r.mensaje


def test_la_sugerencia_de_un_typo_es_la_correcta(buscador):
    assert buscador.buscar("sintrum").candidatos[0].ref == "pv-1"


def test_una_coincidencia_parcial_unica_no_se_usa_sin_confirmar(buscador):
    r = buscador.buscar("ibuprofeno 400")
    assert r.estado == AMBIGUO and r.candidato_para_analisis is None
    assert r.candidatos[0].ref == "pv-9"


def test_productos_sin_composicion_no_se_consideran_la_misma_composicion(buscador):
    r = buscador.buscar("producto sin")  # empata pv-11 y pv-12, ambos sin principio activo cargado
    assert r.estado == AMBIGUO and r.n_empatados == 2
    assert not r.misma_composicion and r.candidato_para_analisis is None


def test_codigo_producto_ref(buscador):
    r = buscador.buscar(" PV-1 ")
    assert r.estado == RESUELTO and r.elegido.ref == "pv-1" and r.elegido.nombre == "SINTROM®"
    assert r.candidato_para_analisis == r.elegido
    r = buscador.buscar("pv-999")
    assert r.estado == NO_ENCONTRADO and "No existe el código" in r.mensaje


@pytest.mark.parametrize("consulta", ["", "  ", "al", "ib"])
def test_consulta_demasiado_corta(buscador, consulta):
    r = buscador.buscar(consulta)
    assert r.estado == NO_ENCONTRADO and "demasiado corta" in r.mensaje


def test_sin_coincidencias(buscador):
    r = buscador.buscar("xyzabc")
    assert r.estado == NO_ENCONTRADO and r.candidatos == []


def test_es_determinista_y_serializable(buscador):
    a, b = buscador.buscar("tafirol"), buscador.buscar("tafirol")
    assert a.to_dict() == b.to_dict()
    json.dumps(a.to_dict(), ensure_ascii=False)  # no lanza


def test_k_limita_los_candidatos_devueltos_pero_no_el_conteo_de_empates(buscador):
    r = buscador.buscar("ibu", k=2)
    assert len(r.candidatos) == 2 and r.n_empatados >= 3


def test_sin_base(tmp_path):
    with pytest.raises(FileNotFoundError):
        Buscador(tmp_path / "no.db")


# --------------------------------------------------------------------------- #
# Integración con la base real (casos documentados en H-05)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not GRAPH_DB_PATH.exists(), reason="no está la base del grafo")
class TestBaseReal:
    def test_H05_ibu(self):
        r = buscar_medicamento("ibu")
        assert r.estado == AMBIGUO and r.n_empatados > 10
        assert all("FRIBURG" not in c.nombre.upper() for c in r.candidatos)

    def test_H05_amoxicilina_es_la_sustancia(self):
        r = buscar_medicamento("Amoxicilina")
        assert r.estado == RESUELTO and r.elegido.tipo == "sustancia"

    def test_H05_alcohol_es_la_sustancia_y_no_un_aerosol(self):
        r = buscar_medicamento("Alcohol")
        assert r.estado == RESUELTO and r.elegido.tipo == "sustancia"
        assert "AEROSOL" not in r.elegido.nombre.upper()

    @pytest.mark.parametrize(
        "consulta, ref",
        [("sintrom", "pv-3989"), ("SINTROM®", "pv-3989"), ("qura plus", "pv-15336"), ("Qura", "pv-6702")],
    )
    def test_marcas_argentinas_conocidas(self, consulta, ref):
        r = buscar_medicamento(consulta)
        assert r.estado == RESUELTO and r.elegido.ref == ref

    def test_marca_con_variantes_pide_elegir(self):
        r = buscar_medicamento("tafirol")
        assert r.estado == AMBIGUO and r.n_empatados >= 10 and r.candidato_para_analisis is None

    def test_la_sustancia_gana_el_desempate_con_un_producto_homonimo(self):
        r = buscar_medicamento("metronidazol")  # existe la sustancia y un producto METRONIDAZOL
        assert r.candidatos[0].tipo == "sustancia" and r.misma_composicion

    def test_nombres_duplicados_con_misma_composicion(self):
        r = buscar_medicamento("acimed")
        assert r.estado == AMBIGUO and r.misma_composicion and r.candidato_para_analisis is not None

    def test_typos_de_marcas_conocidas_se_sugieren_pero_no_se_resuelven(self):
        for consulta in ("tafirrol", "ibupirak", "omeprasol"):
            r = buscar_medicamento(consulta)
            assert r.estado == AMBIGUO and r.candidatos[0].motivo == DIFUSO and r.elegido is None

    def test_rendimiento(self):
        buscar_medicamento("sintrom")  # arma el índice
        t = time.perf_counter()
        for q in ["ibu", "tafirol", "sintrom", "amoxicilina", "qura plus"] * 10:
            buscar_medicamento(q)
        assert time.perf_counter() - t < 5.0  # ~15 ms por consulta
