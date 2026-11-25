"""Perfil determinístico de un paciente sintético: patologías y esquema de medicación.

Los productos salen del vademécum real (solo de un principio activo) y se siembran a propósito
casos con interacción y con duplicidad, registrados como verdad en `gt_problema`.
"""
import random
from dataclasses import dataclass, field

from src.synthetic.catalogo import (
    PATOLOGIAS_AGUDAS,
    PATOLOGIAS_CRONICAS,
    Catalogo,
    ProductoSimple,
)

PESOS_N_MEDICAMENTOS = ((1, 0.25), (2, 0.30), (3, 0.20), (4, 0.12), (5, 0.07), (6, 0.04), (7, 0.01), (8, 0.01))
MAX_ITEMS = 8

PAUTAS_CRONICAS = (
    ({"tipo_pauta": "horarios_fijos", "horarios_fijos": ["08:00"]}, 0.45),
    ({"tipo_pauta": "horarios_fijos", "horarios_fijos": ["08:00", "20:00"]}, 0.40),
    ({"tipo_pauta": "horarios_fijos", "horarios_fijos": ["08:00", "14:00", "20:00"]}, 0.15),
)
PAUTAS_AGUDAS = (
    ({"tipo_pauta": "horarios_fijos", "horarios_fijos": ["08:00", "20:00"]}, 0.35),
    ({"tipo_pauta": "horarios_fijos", "horarios_fijos": ["08:00", "14:00", "20:00"]}, 0.25),
    ({"tipo_pauta": "cada_n_horas", "cada_n_horas": 8}, 0.25),
    ({"tipo_pauta": "cada_n_horas", "cada_n_horas": 12}, 0.15),
)
PAUTA_PROPIA = {"tipo_pauta": "horarios_fijos", "horarios_fijos": ["09:00"]}


@dataclass
class ItemEsquema:
    producto: ProductoSimple
    patologia: str | None
    cronica: bool
    pauta: dict
    duracion_dias: int | None
    origen: str = "medico"  # medico | paciente


@dataclass
class ProblemaSembrado:
    tipo: str                 # interaccion | duplicidad
    sustancias: list[str]
    indices: list[int]        # posiciones en Perfil.items


@dataclass
class Perfil:
    edad: int
    patologias: list[str]
    items: list[ItemEsquema] = field(default_factory=list)
    problemas: list[ProblemaSembrado] = field(default_factory=list)


def _elegir(rng: random.Random, opciones):
    valores, pesos = zip(*opciones)
    return rng.choices(valores, weights=pesos)[0]


def crear_perfil(rng: random.Random, cat: Catalogo, p_interaccion: float = 0.25,
                 p_duplicidad: float = 0.15) -> Perfil:
    cronicas = cat.patologias_disponibles(PATOLOGIAS_CRONICAS)
    agudas = cat.patologias_disponibles(PATOLOGIAS_AGUDAS)
    n_pat = rng.choices((1, 2, 3), weights=(0.4, 0.4, 0.2))[0]
    patologias: list[str] = []
    if rng.random() < 0.7:
        patologias.append(rng.choice(cronicas))
    pool = [p for p in cronicas + agudas if p not in patologias]
    patologias += rng.sample(pool, n_pat - len(patologias))
    perfil = Perfil(edad=rng.randint(18, 85), patologias=patologias)

    usadas: set[str] = set()
    n_meds = _elegir(rng, PESOS_N_MEDICAMENTOS)

    def agregar(prod: ProductoSimple, patologia: str | None, origen: str = "medico") -> int:
        cronica = patologia in PATOLOGIAS_CRONICAS if patologia else origen == "paciente"
        if origen == "paciente":
            pauta, duracion = dict(PAUTA_PROPIA), None
        elif cronica:
            pauta, duracion = dict(_elegir(rng, PAUTAS_CRONICAS)), None
        else:
            pauta, duracion = dict(_elegir(rng, PAUTAS_AGUDAS)), rng.randint(5, 10)
        usadas.add(prod.sustancia)
        perfil.items.append(ItemEsquema(prod, patologia, cronica, pauta, duracion, origen))
        return len(perfil.items) - 1

    # 1) esquema base: un producto por medicamento, sin repetir principio activo
    for i in range(n_meds):
        pat = patologias[i % len(patologias)]
        candidatos = [p for p in cat.productos_de(pat) if p.sustancia not in usadas]
        if candidatos:
            agregar(rng.choice(candidatos), pat)
    if not perfil.items:  # no debería pasar con la lista curada; por robustez
        pat = patologias[0]
        agregar(rng.choice(cat.productos_de(pat)), pat)

    # 2) interacción sembrada: dos principios activos con interacción documentada
    if rng.random() < p_interaccion and len(perfil.items) + 2 <= MAX_ITEMS:
        pares = [p for p in cat.pares_interaccion if not (set(p) & usadas)]
        if pares:
            a, b = rng.choice(pares)
            ia = agregar(rng.choice(cat.productos_de_sustancia(a)), None)
            origen_b = "paciente" if rng.random() < 0.5 else "medico"
            ib = agregar(rng.choice(cat.productos_de_sustancia(b)), None, origen_b)
            perfil.problemas.append(ProblemaSembrado("interaccion", [a, b], [ia, ib]))

    # 3) duplicidad sembrada: el paciente compra por su cuenta otra marca del mismo principio activo
    if rng.random() < p_duplicidad and len(perfil.items) + 1 <= MAX_ITEMS:
        base = [i for i, it in enumerate(perfil.items) if it.origen == "medico"]
        rng.shuffle(base)
        for i in base:
            original = perfil.items[i].producto
            otras = [p for p in cat.productos_de_sustancia(original.sustancia) if p.ref != original.ref]
            if otras:
                j = len(perfil.items)
                perfil.items.append(ItemEsquema(rng.choice(otras), None, True, dict(PAUTA_PROPIA), None, "paciente"))
                perfil.problemas.append(ProblemaSembrado("duplicidad", [original.sustancia], [i, j]))
                break
    return perfil
