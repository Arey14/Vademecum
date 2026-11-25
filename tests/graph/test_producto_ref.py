"""producto_ref (identificador estable de producto) y su presencia en la base real del grafo."""
import sqlite3

import pytest

from src.config import GRAPH_DB_PATH
from src.graph.producto_ref import es_producto_ref, producto_ref_desde_url


@pytest.mark.parametrize(
    "url, esperado",
    [
        ("https://ar.prvademecum.com/medicamento/acimed-31091/", "pv-31091"),
        ("https://ar.prvademecum.com/medicamento/acimed-31091", "pv-31091"),
        # nombres con "/" agregan un tramo a la URL; el id es el último número
        ("https://ar.prvademecum.com/medicamento/cozaarex-d-100/12-5mg-18532/", "pv-18532"),
        ("https://ar.prvademecum.com/medicamento/cozaarex-d-100/25mg-12935/", "pv-12935"),
    ],
)
def test_producto_ref_desde_url(url, esperado):
    assert producto_ref_desde_url(url) == esperado


@pytest.mark.parametrize(
    "url",
    ["", None, "https://otro.com/medicamento/x-1/", "https://ar.prvademecum.com/medicamento/sin-id/"],
)
def test_producto_ref_url_invalida(url):
    with pytest.raises(ValueError):
        producto_ref_desde_url(url)


def test_es_producto_ref():
    assert es_producto_ref("pv-3989") and es_producto_ref(" PV-3989 ")
    assert not es_producto_ref("SINTROM") and not es_producto_ref("pv-") and not es_producto_ref("pv-12a")


@pytest.fixture(scope="module")
def con():
    con = sqlite3.connect(f"{GRAPH_DB_PATH.resolve().as_uri()}?mode=ro", uri=True)
    yield con
    con.close()


@pytest.mark.skipif(not GRAPH_DB_PATH.exists(), reason="no está la base del grafo")
class TestBaseReal:
    def test_todos_los_productos_tienen_ref_unico_y_bien_formado(self, con):
        refs = [r[0] for r in con.execute("SELECT producto_ref FROM productos")]
        assert len(refs) == len(set(refs)) > 8000
        assert all(es_producto_ref(r) for r in refs)

    def test_el_ref_coincide_con_la_url(self, con):
        for ref, url in con.execute("SELECT producto_ref, url FROM productos"):
            assert producto_ref_desde_url(url) == ref

    def test_no_hay_relaciones_huerfanas(self, con):
        for tabla in ("producto_sustancia", "producto_patologia"):
            huerfanas = con.execute(
                f"SELECT COUNT(*) FROM {tabla} t LEFT JOIN productos p USING (producto_ref) "
                "WHERE p.producto_ref IS NULL"
            ).fetchone()[0]
            assert huerfanas == 0, tabla

    def test_nombres_duplicados_conservan_sus_propios_principios(self, con):
        # antes se fusionaban por nombre: ahora cada producto tiene su fila
        refs = [r[0] for r in con.execute("SELECT producto_ref FROM productos WHERE nombre_producto = 'ACIMED'")]
        assert len(refs) == 2
        for ref in refs:
            principios = [r[0] for r in con.execute(
                "SELECT sustancia_name FROM producto_sustancia WHERE producto_ref = ?", (ref,))]
            assert principios == ["Omeprazol"]
