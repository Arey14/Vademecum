"""Búsqueda de medicamentos y sustancias con candidatos, puntaje y desambiguación (H-05).

Reemplaza la heurística original de `find_product` (primer resultado de `LIKE '%texto%'`),
que devolvía por ejemplo AMOXICILINA SANT GALL FRIBURG para la consulta "ibu".

Principios:
- Nunca se elige en silencio entre candidatos parecidos: si hay empate, el estado es
  `ambiguo` y se devuelven los candidatos para que el usuario (o el agente) elija.
- Un typo (coincidencia difusa) nunca se resuelve solo: siempre pide confirmación.
- Se distingue PRODUCTO (marca comercial, con `producto_ref`) de SUSTANCIA (principio
  activo). "Amoxicilina" es una sustancia: resolverla a un producto cualquiera sería inventar.
- Si todos los candidatos empatados comparten composición (`misma_composicion`), la
  ambigüedad no cambia el análisis de interacciones y el llamador puede seguir.

Puntajes por nivel (el empate dentro de un nivel es ambigüedad):
    exacto 1.00 · alias 0.97 · prefijo 0.90 · tokens 0.80 · difuso 0.60–0.75
"""
import sqlite3
import unicodedata
import re
from contextlib import closing
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

from src.config import GRAPH_DB_PATH
from src.graph.pharmacological_classes import SUBSTANCE_ALIASES
from src.graph.producto_ref import es_producto_ref

# Estados
RESUELTO = "resuelto"
AMBIGUO = "ambiguo"
NO_ENCONTRADO = "no_encontrado"

# Motivos / niveles
EXACTO, ALIAS, PREFIJO, TOKENS, DIFUSO = "exacto", "alias", "prefijo", "tokens", "difuso"
_SCORE = {EXACTO: 1.0, ALIAS: 0.97, PREFIJO: 0.90, TOKENS: 0.80}

MIN_LARGO_CONSULTA = 3        # por debajo no se busca (demasiado ambiguo)
MIN_LARGO_PARA_RESOLVER = 4   # prefijo/tokens con menos letras nunca se resuelven solos
UMBRAL_RESOLVER = 0.85        # solo exacto/alias/prefijo/tokens pueden resolverse
UMBRAL_DIFUSO = 80            # ratio mínimo (0-100) de rapidfuzz
_NO_ALNUM = re.compile(r"[^a-z0-9]+")


def normalizar(texto: str) -> str:
    """minúsculas, sin tildes ni símbolos (®, ™, puntuación), espacios colapsados."""
    sin_tildes = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return _NO_ALNUM.sub(" ", sin_tildes.lower()).strip()


@dataclass(frozen=True)
class Candidato:
    tipo: str                      # "producto" | "sustancia"
    ref: str                       # producto_ref (pv-…) o nombre canónico de la sustancia
    nombre: str
    score: float
    motivo: str                    # exacto | alias | prefijo | tokens | difuso
    laboratorio: str | None = None
    principios_activos: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["principios_activos"] = list(self.principios_activos)
        return d


@dataclass
class Resolucion:
    consulta: str
    estado: str                    # resuelto | ambiguo | no_encontrado
    candidatos: list[Candidato] = field(default_factory=list)  # top-k, mejor primero
    elegido: Candidato | None = None   # solo si estado == resuelto
    misma_composicion: bool = False    # los candidatos empatados comparten principios activos
    n_empatados: int = 0
    mensaje: str = ""
    # Candidato que se puede usar SIN preguntar al usuario para analizar interacciones:
    # el elegido si está resuelto, o el primero si hay un empate real con la misma composición
    # (ej. dos productos ACIMED de distinto laboratorio) y la coincidencia es exacta, por alias
    # o por prefijo de >= 4 letras. Un typo o una coincidencia parcial NUNCA se usan sin confirmar.
    candidato_para_analisis: Candidato | None = None

    def to_dict(self) -> dict:
        return {
            "consulta": self.consulta,
            "estado": self.estado,
            "elegido": self.elegido.to_dict() if self.elegido else None,
            "candidatos": [c.to_dict() for c in self.candidatos],
            "misma_composicion": self.misma_composicion,
            "n_empatados": self.n_empatados,
            "mensaje": self.mensaje,
        }


@dataclass(frozen=True)
class _Entrada:
    tipo: str
    ref: str
    nombre: str
    norm: str
    tokens: tuple[str, ...]
    laboratorio: str | None
    principios: tuple[str, ...]
    es_alias: bool = False


def _principios_clave(principios) -> frozenset[str]:
    return frozenset(normalizar(p) for p in principios if p and p.strip())


class Buscador:
    """Índice en memoria del vademécum (productos, sustancias y alias)."""

    def __init__(self, db_path: str | Path | None = None):
        ruta = Path(db_path) if db_path else GRAPH_DB_PATH
        if not ruta.exists():
            raise FileNotFoundError(f"No existe la base del vademécum en {ruta}.")
        uri = f"{ruta.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as con:
            productos = con.execute(
                "SELECT producto_ref, nombre_producto, laboratorio_nombre FROM productos "
                "WHERE nombre_producto IS NOT NULL AND nombre_producto != ''"
            ).fetchall()
            principios: dict[str, list[str]] = {}
            for ref, sust in con.execute(
                "SELECT producto_ref, sustancia_name FROM producto_sustancia ORDER BY sustancia_name"
            ):
                principios.setdefault(ref, []).append(sust)
            sustancias = [r[0] for r in con.execute(
                "SELECT nombre FROM sustancias WHERE nombre IS NOT NULL AND nombre != ''"
            )]

        self._entradas: list[_Entrada] = []
        for ref, nombre, lab in productos:
            norm = normalizar(nombre)
            if norm:
                self._entradas.append(_Entrada(
                    "producto", ref, nombre, norm, tuple(norm.split()), lab,
                    tuple(principios.get(ref, ())),
                ))
        por_norm = {normalizar(s): s for s in sustancias}
        for s in sustancias:
            norm = normalizar(s)
            if norm:
                self._entradas.append(_Entrada("sustancia", s, s, norm, tuple(norm.split()), None, (s,)))
            # "Acetilsalicílico ácido" también se puede escribir "ácido acetilsalicílico"
            partes = norm.split()
            if len(partes) >= 2 and partes[-1] == "acido":
                base = " ".join(partes[:-1])
                for alias in (f"acido {base}", base):
                    self._entradas.append(_Entrada(
                        "sustancia", s, s, alias, tuple(alias.split()), None, (s,), es_alias=True))
        for alias, canonico in SUBSTANCE_ALIASES.items():
            canon = por_norm.get(normalizar(canonico))
            if canon and normalizar(alias):
                a = normalizar(alias)
                self._entradas.append(_Entrada(
                    "sustancia", canon, canon, a, tuple(a.split()), None, (canon,), es_alias=True))

        self._por_ref = {e.ref: e for e in self._entradas if e.tipo == "producto"}

        # Para la búsqueda difusa: los primeros m tokens de cada nombre (m = 1..3)
        self._lideres = {
            m: [" ".join(e.tokens[:m]) for e in self._entradas] for m in (1, 2, 3)
        }

    # ------------------------------------------------------------------ #
    def _puntuar(self, q: str, q_tokens: list[str]) -> dict[tuple[str, str], tuple[float, str, _Entrada]]:
        """Mejor coincidencia por entidad (tipo, ref)."""
        mejores: dict[tuple[str, str], tuple[float, str, _Entrada]] = {}

        def ofrecer(e: _Entrada, score: float, motivo: str):
            clave = (e.tipo, e.ref)
            actual = mejores.get(clave)
            if actual is None or score > actual[0]:
                mejores[clave] = (score, motivo, e)

        for e in self._entradas:
            if e.norm == q:
                ofrecer(e, _SCORE[ALIAS] if e.es_alias else _SCORE[EXACTO], ALIAS if e.es_alias else EXACTO)
            elif len(q) >= MIN_LARGO_CONSULTA and e.norm.startswith(q):
                ofrecer(e, _SCORE[PREFIJO], PREFIJO)
            elif len(q) >= MIN_LARGO_CONSULTA and all(
                any(nt.startswith(qt) for nt in e.tokens) for qt in q_tokens
            ):
                ofrecer(e, _SCORE[TOKENS], TOKENS)

        # Difuso (errores de tipeo): compara contra los primeros m tokens del nombre
        m = min(len(q_tokens), 3)
        for _, ratio, idx in process.extract(
            q, self._lideres[m], scorer=fuzz.ratio, score_cutoff=UMBRAL_DIFUSO, limit=None
        ):
            e = self._entradas[idx]
            if (e.tipo, e.ref) in mejores:
                continue
            ofrecer(e, 0.60 + (ratio - UMBRAL_DIFUSO) / (100 - UMBRAL_DIFUSO) * 0.15, DIFUSO)
        return mejores

    def buscar(self, texto: str, k: int = 5) -> Resolucion:
        if es_producto_ref(texto):  # código exacto (ej. "pv-3989"): sin ambigüedad posible
            e = self._por_ref.get(texto.strip().lower())
            if e is None:
                return Resolucion(texto, NO_ENCONTRADO, mensaje=f"No existe el código {texto!r}.")
            c = Candidato(e.tipo, e.ref, e.nombre, 1.0, EXACTO, e.laboratorio, e.principios)
            return Resolucion(texto, RESUELTO, [c], c, True, 1, f"Producto: {c.nombre}.", c)
        q = normalizar(texto)
        if len(q) < MIN_LARGO_CONSULTA:
            return Resolucion(texto, NO_ENCONTRADO,
                              mensaje=f"La consulta {texto!r} es demasiado corta (mínimo {MIN_LARGO_CONSULTA} letras).")

        mejores = self._puntuar(q, q.split())
        if not mejores:
            return Resolucion(texto, NO_ENCONTRADO, mensaje=f"No se encontró ningún medicamento parecido a {texto!r}.")

        todos = sorted(
            (Candidato(e.tipo, e.ref, e.nombre, round(score, 4), motivo, e.laboratorio, e.principios)
             for score, motivo, e in mejores.values()),
            # A igual puntaje: primero la sustancia (si escribió un principio activo, no un
            # laboratorio al azar), después el nombre más corto, y por último orden estable.
            key=lambda c: (-c.score, c.tipo != "sustancia", len(c.nombre), c.nombre, c.ref),
        )
        top = todos[0]
        empatados = [c for c in todos if c.score == top.score]
        composiciones = {_principios_clave(c.principios_activos) for c in empatados}
        misma = len(composiciones) == 1 and bool(next(iter(composiciones)))

        res = Resolucion(texto, AMBIGUO, todos[:k], None, misma, len(empatados))
        puede_resolver = (
            len(empatados) == 1
            and top.score >= UMBRAL_RESOLVER
            and (top.motivo in (EXACTO, ALIAS) or len(q) >= MIN_LARGO_PARA_RESOLVER)
        )
        empate_equivalente = (
            len(empatados) > 1 and misma
            and (top.motivo in (EXACTO, ALIAS) or (top.motivo == PREFIJO and len(q) >= MIN_LARGO_PARA_RESOLVER))
        )
        if puede_resolver:
            res.estado, res.elegido = RESUELTO, top
            res.candidato_para_analisis = top
            res.mensaje = f"{top.tipo.capitalize()}: {top.nombre}."
        elif empate_equivalente:
            res.candidato_para_analisis = top
            res.mensaje = (f"{len(empatados)} candidatos igual de buenos para {texto!r}, "
                           "todos con la misma composición.")
        elif top.motivo == DIFUSO:
            res.mensaje = f"No hay coincidencia exacta con {texto!r}. ¿Quiso decir {top.nombre}?"
        elif len(empatados) > 1:
            res.mensaje = (
                f"{len(empatados)} candidatos igual de buenos para {texto!r}; "
                + ("todos tienen la misma composición. " if misma else "elegir uno. ")
            ).strip()
        else:
            res.mensaje = f"Coincidencia parcial con {texto!r}: confirmar {top.nombre}."
        return res


@lru_cache(maxsize=4)
def _buscador_cacheado(ruta: str, firma_mtime: float) -> Buscador:
    return Buscador(ruta)


def get_buscador(db_path: str | Path | None = None) -> Buscador:
    """Buscador compartido; se reconstruye si cambia la base (mtime)."""
    ruta = Path(db_path) if db_path else GRAPH_DB_PATH
    return _buscador_cacheado(str(ruta.resolve()), ruta.stat().st_mtime)


def buscar_medicamento(texto: str, k: int = 5, db_path: str | Path | None = None) -> Resolucion:
    return get_buscador(db_path).buscar(texto, k)
