"""Identificador estable de producto (`producto_ref`).

Formato: ``pv-<id numérico de PR Vademécum>``, ej. ``pv-31091`` para
``https://ar.prvademecum.com/medicamento/acimed-31091/``.

Por qué así (ver docs/MODELO_DATOS.md):
- El nombre NO sirve de clave: hay nombres duplicados (ej. ACIMED de MEDISOL y de LEPETIT).
- El id numérico del final de la URL es único en los 8.349 productos y no depende del orden
  de scraping ni de reconstruir el grafo, a diferencia de un autoincremental.
- El prefijo ``pv`` identifica la fuente, por si se suma otra más adelante.
"""
import re

PREFIJO = "pv"
_URL_ID = re.compile(r"^https?://ar\.prvademecum\.com/medicamento/[^?#]*?-(\d+)/?$")
_REF = re.compile(rf"^{PREFIJO}-\d+$")


def producto_ref_desde_url(url: str) -> str:
    """Devuelve el producto_ref de una URL de producto. Lanza ValueError si no la reconoce."""
    m = _URL_ID.match((url or "").strip())
    if not m:
        raise ValueError(f"URL de producto no reconocida: {url!r}")
    return f"{PREFIJO}-{m.group(1)}"


def es_producto_ref(texto: str) -> bool:
    return bool(_REF.match((texto or "").strip().lower()))
