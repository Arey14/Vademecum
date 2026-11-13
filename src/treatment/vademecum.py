"""Adaptador entre el servicio de tratamiento y el vademécum (grafo en SQLite).

Resuelve un `producto_ref` a su nombre y principios activos. Abre la base en modo
solo lectura: el servicio de tratamiento nunca escribe en el grafo.
"""
import sqlite3
from contextlib import closing
from pathlib import Path

from src.config import GRAPH_DB_PATH
from src.treatment.service import ProductoNoEncontrado, ProductoResuelto, ResolverProducto


def crear_resolver(db_path: str | Path | None = None) -> ResolverProducto:
    """Devuelve `resolver(producto_ref) -> ProductoResuelto` sobre la base del grafo."""
    ruta = Path(db_path) if db_path else GRAPH_DB_PATH
    if not ruta.exists():
        raise FileNotFoundError(f"No existe la base del vademécum en {ruta}. Ver README (make graph).")
    uri = f"{ruta.resolve().as_uri()}?mode=ro"

    def resolver(producto_ref: str) -> ProductoResuelto:
        ref = (producto_ref or "").strip().lower()
        with closing(sqlite3.connect(uri, uri=True)) as con:
            fila = con.execute(
                "SELECT nombre_producto FROM productos WHERE producto_ref = ?", (ref,)
            ).fetchone()
            if fila is None:
                raise ProductoNoEncontrado(f"No existe el producto {producto_ref!r} en el vademécum.")
            principios = [
                r[0]
                for r in con.execute(
                    "SELECT sustancia_name FROM producto_sustancia WHERE producto_ref = ? "
                    "ORDER BY sustancia_name",
                    (ref,),
                )
            ]
        return ProductoResuelto(nombre=fila[0], principios_activos=principios)

    return resolver
