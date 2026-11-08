"""Adaptador al vademécum (`crear_resolver`). Incluye pruebas de integración con la base real
(Final/vademecum_graph.db), que se saltean si no está."""
import sqlite3

import pytest

from src.config import GRAPH_DB_PATH
from src.treatment.service import ProductoNoEncontrado
from src.treatment.vademecum import crear_resolver


@pytest.fixture()
def mini_db(tmp_path):
    ruta = tmp_path / "g.db"
    con = sqlite3.connect(ruta)
    con.executescript(
        """
        CREATE TABLE productos (producto_ref TEXT PRIMARY KEY, nombre_producto TEXT);
        CREATE TABLE producto_sustancia (producto_ref TEXT, sustancia_name TEXT);
        INSERT INTO productos VALUES ('pv-1', 'ACIMED'), ('pv-2', 'ACIMED'), ('pv-3', 'COMBO');
        INSERT INTO producto_sustancia VALUES ('pv-1', 'Omeprazol'), ('pv-3', 'Zeta'), ('pv-3', 'Alfa');
        """
    )
    con.commit()
    con.close()
    return ruta


def test_resolver_distingue_productos_con_el_mismo_nombre(mini_db):
    r = crear_resolver(mini_db)
    assert r("pv-1").principios_activos == ["Omeprazol"]
    assert r("pv-2").principios_activos == []  # mismo nombre, otro producto


def test_resolver_ordena_principios_y_normaliza_el_ref(mini_db):
    assert crear_resolver(mini_db)(" PV-3 ").principios_activos == ["Alfa", "Zeta"]


def test_resolver_producto_inexistente(mini_db):
    with pytest.raises(ProductoNoEncontrado):
        crear_resolver(mini_db)("pv-999")


def test_resolver_es_de_solo_lectura(mini_db):
    crear_resolver(mini_db)("pv-1")
    con = sqlite3.connect(f"{mini_db.resolve().as_uri()}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("INSERT INTO productos VALUES ('pv-9', 'X')")
    con.close()


def test_resolver_sin_base(tmp_path):
    with pytest.raises(FileNotFoundError):
        crear_resolver(tmp_path / "no-existe.db")


@pytest.mark.skipif(not GRAPH_DB_PATH.exists(), reason="no está la base del grafo")
class TestBaseReal:
    def test_resuelve_sintrom_con_su_principio_activo(self):
        con = sqlite3.connect(f"{GRAPH_DB_PATH.resolve().as_uri()}?mode=ro", uri=True)
        ref = con.execute(
            "SELECT producto_ref FROM productos WHERE nombre_producto LIKE 'SINTROM%'"
        ).fetchone()[0]
        con.close()
        p = crear_resolver()(ref)
        assert p.nombre.startswith("SINTROM") and p.principios_activos == ["Acenocumarol"]

    def test_nombres_duplicados_se_resuelven_por_su_ref(self):
        con = sqlite3.connect(f"{GRAPH_DB_PATH.resolve().as_uri()}?mode=ro", uri=True)
        refs = [r[0] for r in con.execute("SELECT producto_ref FROM productos WHERE nombre_producto = 'ACIMED'")]
        con.close()
        resolver = crear_resolver()
        assert len(refs) == 2 and all(resolver(r).principios_activos == ["Omeprazol"] for r in refs)
