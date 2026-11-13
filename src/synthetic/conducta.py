"""Simulación de la conducta del paciente frente a cada toma (determinística dada la semilla).

Genera, para cada toma programada, lo que PASÓ (verdad) y lo que QUEDÓ REGISTRADO en el
sistema. La brecha entre ambos (se tomó pero no se tildó; no se tomó y no lo dijo) es lo que
hace realista el problema de medir adherencia y es una métrica de la evaluación.
"""
import random
from dataclasses import asdict, dataclass
from datetime import datetime

ARQUETIPOS = {
    # nombre: (rango p_olvido, probabilidad de abandonar un medicamento)
    "cumplidor": ((0.02, 0.08), 0.02),
    "regular": ((0.12, 0.25), 0.12),
    "olvidadizo": ((0.30, 0.50), 0.30),
}
PESOS_ARQUETIPO = (("cumplidor", 0.35), ("regular", 0.40), ("olvidadizo", 0.25))


@dataclass
class ParametrosConducta:
    arquetipo: str
    p_olvido: float          # probabilidad base de olvidar una toma
    mult_noche: float        # el olvido se multiplica por esto de 20 a 6 h
    mult_finde: float        # ... y por esto sábados y domingos
    p_tarde: float           # probabilidad de tomarla fuera de ventana (61–180 min tarde)
    p_tilde: float           # si la tomó, probabilidad de tildarla
    p_marca_omitida: float   # si NO la tomó, probabilidad de avisar que no la tomó
    abandono_ref: str | None = None   # producto que deja de tomar...
    abandono_desde: str | None = None  # ...a partir de esta fecha (ISO)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Decision:
    resultado: str           # tomada_en_hora | tomada_tarde | omitida
    registro: str            # tildada | marcada_omitida | sin_registrar
    desvio_min: int | None
    motivo: str | None


def sortear_parametros(rng: random.Random, refs_esquema: list[str], inicio: datetime,
                       fin: datetime) -> ParametrosConducta:
    nombres, pesos = zip(*PESOS_ARQUETIPO)
    arq = rng.choices(nombres, weights=pesos)[0]
    (lo, hi), p_abandono = ARQUETIPOS[arq]
    params = ParametrosConducta(
        arquetipo=arq,
        p_olvido=round(rng.uniform(lo, hi), 3),
        mult_noche=round(rng.uniform(1.0, 2.5), 2),
        mult_finde=round(rng.uniform(1.0, 2.0), 2),
        p_tarde=round(rng.uniform(0.05, 0.25), 3),
        p_tilde=round(rng.uniform(0.85, 0.98), 3),
        p_marca_omitida=round(rng.uniform(0.2, 0.5), 3),
    )
    if refs_esquema and rng.random() < p_abandono:
        params.abandono_ref = rng.choice(refs_esquema)
        # abandona entre el 30 % y el 90 % del período
        params.abandono_desde = (inicio + (fin - inicio) * rng.uniform(0.3, 0.9)).isoformat()
    return params


def decidir(rng: random.Random, p: ParametrosConducta, prevista: datetime, ref: str,
            tz) -> Decision:
    """Qué hace el paciente con una toma. `prevista` es tz-aware."""
    if p.abandono_ref == ref and prevista >= datetime.fromisoformat(p.abandono_desde):
        # quien abandonó un medicamento casi nunca lo avisa
        marca = rng.random() < p.p_marca_omitida / 3
        return Decision("omitida", "marcada_omitida" if marca else "sin_registrar", None, "abandono")

    local = prevista.astimezone(tz)
    prob = p.p_olvido
    if local.hour >= 20 or local.hour < 6:
        prob *= p.mult_noche
    if local.weekday() >= 5:
        prob *= p.mult_finde
    if rng.random() < min(prob, 0.95):
        marca = rng.random() < p.p_marca_omitida
        return Decision("omitida", "marcada_omitida" if marca else "sin_registrar", None, "olvido")

    if rng.random() < p.p_tarde:
        desvio, resultado = rng.randint(61, 180), "tomada_tarde"
    else:
        desvio, resultado = rng.randint(-20, 30), "tomada_en_hora"
    registro = "tildada" if rng.random() < p.p_tilde else "sin_registrar"
    return Decision(resultado, registro, desvio, None)
