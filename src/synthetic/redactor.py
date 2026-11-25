"""Redacción del texto que escribiría el paciente a partir de un hecho estructurado.

`Redactor` es una interfaz: la v0 usa plantillas (`RedactorPlantillas`, determinístico y
gratis). Cuando se defina el proveedor de LLM se agrega un redactor con LLM que cumpla la
misma interfaz y se compara con las plantillas en la evaluación del generador (realismo, L4).
Como el hecho estructurado se conoce, la verdad de cada texto es exacta.
"""
import random
import unicodedata
from dataclasses import dataclass
from typing import Protocol

SINTOMAS = (
    "dolor de cabeza", "dolor de garganta", "fiebre", "dolor de espalda", "alergia",
    "dolor de estomago", "acidez", "mareos", "nauseas", "tos", "dolor muscular", "insomnio",
)


@dataclass(frozen=True)
class HechoEvento:
    tipo: str                         # "toma_fuera_de_esquema" | "sintoma"
    producto_nombre: str | None = None
    sustancia: str | None = None
    sintoma: str | None = None


@dataclass(frozen=True)
class Redaccion:
    texto: str
    nombre_mencionado: str | None     # cómo se nombró el medicamento (con typos si los hubo)
    con_typo: bool


class Redactor(Protocol):
    nombre: str

    def redactar(self, hecho: HechoEvento, rng: random.Random) -> Redaccion: ...


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _typo(palabra: str, rng: random.Random) -> str:
    """Un error de tipeo plausible: letra omitida, letras intercambiadas o letra duplicada."""
    if len(palabra) < 4:
        return palabra
    i = rng.randrange(1, len(palabra) - 1)
    modo = rng.choice(("omitir", "intercambiar", "duplicar"))
    if modo == "omitir":
        return palabra[:i] + palabra[i + 1:]
    if modo == "intercambiar":
        return palabra[:i] + palabra[i + 1] + palabra[i] + palabra[i + 2:]
    return palabra[:i] + palabra[i] + palabra[i:]


PLANTILLAS_AUTOMEDICACION = (
    "me tome un {n} ayer xq tenia {s}",
    "hoy tome {n} por {s}",
    "anoche me mande un {n}, me dolia mucho, tenia {s}",
    "tome {n} de nuevo, sigo con {s}",
    "ayer a la tarde me tome {n} porque {s}",
    "me tome un {n} sin preguntar, tenia {s}",
)
PLANTILLAS_SINTOMA = (
    "desde ayer tengo {s}",
    "hoy tuve {s}, es normal?",
    "me vino {s} despues de la pastilla de la mañana",
    "sigo con {s}",
    "estuve toda la noche con {s}",
)


class RedactorPlantillas:
    nombre = "plantillas"

    def __init__(self, p_typo: float = 0.3, p_usar_sustancia: float = 0.25):
        self.p_typo = p_typo
        self.p_usar_sustancia = p_usar_sustancia

    def redactar(self, hecho: HechoEvento, rng: random.Random) -> Redaccion:
        if hecho.tipo == "sintoma":
            texto = rng.choice(PLANTILLAS_SINTOMA).format(s=hecho.sintoma)
            return Redaccion(self._informal(texto, rng), None, False)
        if hecho.sustancia and rng.random() < self.p_usar_sustancia:
            nombre = hecho.sustancia.lower()
        else:
            nombre = (hecho.producto_nombre or "").split()[0].lower()
        con_typo = rng.random() < self.p_typo
        if con_typo:
            nombre = _typo(nombre, rng)
        texto = rng.choice(PLANTILLAS_AUTOMEDICACION).format(n=nombre, s=hecho.sintoma or "dolor")
        return Redaccion(self._informal(texto, rng), nombre, con_typo)

    @staticmethod
    def _informal(texto: str, rng: random.Random) -> str:
        """Escritura de chat: a veces sin tildes, sin mayúscula inicial."""
        if rng.random() < 0.5:
            texto = _sin_tildes(texto)
        return texto[0].lower() + texto[1:]
