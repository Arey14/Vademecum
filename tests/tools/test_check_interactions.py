"""evaluate_combination sobre la base real: ya no elige en silencio (H-05)."""
import pytest

from src.config import GRAPH_DB_PATH
from src.tools.check_interactions import evaluate_combination, find_product, get_connection

pytestmark = pytest.mark.skipif(not GRAPH_DB_PATH.exists(), reason="no está la base del grafo")


def test_una_marca_ambigua_frena_el_analisis_en_vez_de_elegir_una_al_azar():
    r = evaluate_combination(["Sintrom", "ibu"])
    assert r["status"] == "ambiguous"
    assert "No se hizo ningún análisis parcial" in r["message"]
    assert r["ambiguous"][0]["consulta"] == "ibu" and len(r["ambiguous"][0]["candidatos"]) > 1
    assert "found_products" not in r  # nada de análisis parcial


def test_marcas_exactas_detectan_la_interaccion():
    r = evaluate_combination(["Sintrom", "Ibupirac"])
    assert r["status"] == "success" and r["avisos"] == []
    pares = {frozenset((i["sustancia_1"], i["sustancia_2"])) for i in r["interactions"]}
    assert frozenset(("Acenocumarol", "Ibuprofeno")) in pares


def test_acepta_un_principio_activo_directamente():
    r = evaluate_combination(["Sintrom", "Ibuprofeno"])
    assert r["status"] == "success"
    assert r["found_products"][1]["tipo"] == "sustancia"
    assert r["interactions"], "Acenocumarol + Ibuprofeno debería interactuar"


def test_acepta_codigos_producto_ref():
    r = evaluate_combination(["pv-3989", "pv-16362"])  # SINTROM + IBUPIRAC
    assert r["status"] == "success" and r["interactions"]


def test_empate_con_la_misma_composicion_sigue_pero_avisa():
    r = evaluate_combination(["acimed", "sintrom"])
    assert r["status"] == "success" and len(r["avisos"]) == 1 and "pv-" in r["avisos"][0]


def test_un_typo_no_se_analiza_sin_confirmar():
    r = evaluate_combination(["sintrom", "ibupirak"])
    assert r["status"] == "ambiguous"
    assert r["ambiguous"][0]["candidatos"][0]["motivo"] == "difuso"


def test_nada_encontrado_es_error():
    r = evaluate_combination(["xyzabc", "qwerty"])
    assert r["status"] == "error" and set(r["missing"]) == {"xyzabc", "qwerty"}


def test_find_product_ya_no_hace_coincidencia_parcial():
    cur = get_connection().cursor()
    assert find_product(cur, "ibu") is None            # antes: AMOXICILINA SANT GALL FRIBURG
    assert find_product(cur, "Amoxicilina") is None    # antes: AMOXICILINA CLAVULANICO FORTE
    assert find_product(cur, "Alcohol") is None        # antes: DG-6 ALCOHOL AEROSOL
    assert find_product(cur, "sintrom®")["producto_ref"] == "pv-3989"
    assert find_product(cur, "PV-3989")["nombre"].startswith("SINTROM")
