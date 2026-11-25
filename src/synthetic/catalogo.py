"""Acceso de solo lectura al vademécum para el generador de pacientes sintéticos.

Solo se usan productos de UN principio activo (más simples de razonar y de evaluar) y un
conjunto curado de patologías ambulatorias comunes. La lista curada es una simplificación
v0: la plausibilidad clínica se revisa con el médico (tarea M2 en docs/PLAN.md).
"""
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from src.config import GRAPH_DB_PATH


@dataclass(frozen=True)
class ProductoSimple:
    ref: str
    nombre: str
    sustancia: str


# patología del vademécum -> (crónica?, ¿se trata con varios fármacos?)
PATOLOGIAS_CRONICAS = (
    "Hipertensión arterial",
    "Diabetes mellitus",
    "Hipercolesterolemias - Dislipidemias",
    "Asma bronquial",
    "Depresión",
    "Ansiedad",
    "Esofagitis por reflujo",
    "Artrosis - Reumatismo",
)
PATOLOGIAS_AGUDAS = (
    "Dolor",
    "Fiebre - Hipertermia",
    "Alergia",
    "Infecciones respiratorias",
    "Infecciones bacterianas sistémicas",
    "Ulcera péptica",
)
# Patologías cuyos productos se usan para la automedicación de venta libre
PATOLOGIAS_VENTA_LIBRE = ("Dolor", "Fiebre - Hipertermia", "Alergia")

# Textos de la tabla de interacciones que declaran explícitamente que NO hay interacción
_SIN_INTERACCION = ("no se dan interacciones", "no han demostrado", "no se han observado")


class Catalogo:
    def __init__(self, db_path: str | Path | None = None):
        ruta = Path(db_path) if db_path else GRAPH_DB_PATH
        if not ruta.exists():
            raise FileNotFoundError(f"No existe la base del vademécum en {ruta}.")
        uri = f"{ruta.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as con:
            simples = {
                ref: (nombre, sust)
                for ref, nombre, sust in con.execute(
                    "SELECT p.producto_ref, p.nombre_producto, MIN(ps.sustancia_name) "
                    "FROM productos p JOIN producto_sustancia ps USING (producto_ref) "
                    "GROUP BY p.producto_ref HAVING COUNT(*) = 1"
                )
            }
            self._por_patologia: dict[str, list[ProductoSimple]] = {}
            for ref, pat in con.execute(
                "SELECT producto_ref, patologia_name FROM producto_patologia "
                "ORDER BY patologia_name, producto_ref"
            ):
                if ref in simples:
                    nombre, sust = simples[ref]
                    self._por_patologia.setdefault(pat, []).append(ProductoSimple(ref, nombre, sust))
            self._por_sustancia: dict[str, list[ProductoSimple]] = {}
            for ref, (nombre, sust) in sorted(simples.items()):
                self._por_sustancia.setdefault(sust, []).append(ProductoSimple(ref, nombre, sust))
            self.productos = {ref: ProductoSimple(ref, n, s) for ref, (n, s) in simples.items()}
            # Solo principios activos de patologías ambulatorias curadas: evita sembrar pares
            # clínicamente absurdos (p. ej. un antipsicótico con un fármaco oncológico).
            ambulatorias = {
                p.sustancia
                for pat in PATOLOGIAS_CRONICAS + PATOLOGIAS_AGUDAS
                for p in self._por_patologia.get(pat, [])
            }
            pares = set()
            for a, b, detalle in con.execute(
                "SELECT sustancia_origen, sustancia_destino, detalle FROM sustancia_interaccion"
            ):
                if a in ambulatorias and b in ambulatorias and a != b:
                    if not any(t in (detalle or "").lower() for t in _SIN_INTERACCION):
                        pares.add(tuple(sorted((a, b))))
            self.pares_interaccion: list[tuple[str, str]] = sorted(pares)

    def productos_de(self, patologia: str) -> list[ProductoSimple]:
        return list(self._por_patologia.get(patologia, []))

    def productos_de_sustancia(self, sustancia: str) -> list[ProductoSimple]:
        return list(self._por_sustancia.get(sustancia, []))

    def patologias_disponibles(self, nombres) -> list[str]:
        """Las patologías de la lista curada que tienen al menos un producto simple."""
        return [p for p in nombres if self._por_patologia.get(p)]
