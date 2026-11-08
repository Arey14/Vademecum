"""Cálculo de adherencia (determinístico).

Definición (decisión D-10 en docs/PLAN.md):
- Una toma es CUMPLIDA si se tildó dentro de ±ventana (por defecto 60 min) de la hora prevista.
- Una toma es VENCIDA si estaba pendiente y ya pasó prevista + ventana.
- Denominador = cumplidas + fuera de ventana + omitidas (incluye vencidas). Las pendientes
  que todavía no vencieron NO cuentan. Las tomas a demanda no generan tomas programadas,
  por lo tanto no entran.
- adherencia = cumplidas / denominador (None si el denominador es 0).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from src.treatment.models import EstadoToma
from src.treatment.schedule import DEFAULT_TZ

VENTANA_DEFAULT_MIN = 60

CUMPLIDA = "cumplida"
FUERA_DE_VENTANA = "fuera_de_ventana"
OMITIDA = "omitida"
PENDIENTE = "pendiente"

FRANJAS = (  # (nombre, hora_desde_inclusive, hora_hasta_exclusiva) en hora local
    ("madrugada", 0, 6),
    ("mañana", 6, 12),
    ("tarde", 12, 20),
    ("noche", 20, 24),
)
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


@dataclass
class Conteo:
    cumplidas: int = 0
    fuera_de_ventana: int = 0
    omitidas: int = 0

    @property
    def total(self) -> int:
        return self.cumplidas + self.fuera_de_ventana + self.omitidas

    @property
    def adherencia(self) -> float | None:
        return self.cumplidas / self.total if self.total else None


@dataclass
class ResumenAdherencia:
    global_: Conteo = field(default_factory=Conteo)
    por_franja: dict[str, Conteo] = field(default_factory=dict)
    por_dia_semana: dict[str, Conteo] = field(default_factory=dict)
    pendientes: int = 0


def clasificar_toma(toma, ahora: datetime, ventana_min: int = VENTANA_DEFAULT_MIN) -> str:
    """`toma` necesita: fecha_hora_prevista, estado, fecha_hora_real (p. ej. TomaProgramada)."""
    ventana = timedelta(minutes=ventana_min)
    if toma.estado == EstadoToma.TOMADA and toma.fecha_hora_real is not None:
        desvio = abs(toma.fecha_hora_real - toma.fecha_hora_prevista)
        return CUMPLIDA if desvio <= ventana else FUERA_DE_VENTANA
    if toma.estado == EstadoToma.OMITIDA:
        return OMITIDA
    # pendiente (o tomada sin hora real, dato inconsistente: se trata como pendiente)
    return OMITIDA if toma.fecha_hora_prevista + ventana <= ahora else PENDIENTE


def _franja(hora: int) -> str:
    for nombre, desde, hasta in FRANJAS:
        if desde <= hora < hasta:
            return nombre
    raise ValueError(hora)


def _sumar(conteo: Conteo, clase: str) -> None:
    if clase == CUMPLIDA:
        conteo.cumplidas += 1
    elif clase == FUERA_DE_VENTANA:
        conteo.fuera_de_ventana += 1
    elif clase == OMITIDA:
        conteo.omitidas += 1


def calcular_adherencia(
    tomas: Iterable,
    ahora: datetime,
    ventana_min: int = VENTANA_DEFAULT_MIN,
    tz: str = DEFAULT_TZ,
) -> ResumenAdherencia:
    """Adherencia global y desglosada por franja horaria y día de la semana (hora local)."""
    if ahora.tzinfo is None:
        raise ValueError("`ahora` debe tener zona horaria.")
    zona = ZoneInfo(tz)
    res = ResumenAdherencia()
    franjas: dict[str, Conteo] = defaultdict(Conteo)
    dias: dict[str, Conteo] = defaultdict(Conteo)
    for toma in tomas:
        clase = clasificar_toma(toma, ahora, ventana_min)
        if clase == PENDIENTE:
            res.pendientes += 1
            continue
        local = toma.fecha_hora_prevista.astimezone(zona)
        _sumar(res.global_, clase)
        _sumar(franjas[_franja(local.hour)], clase)
        _sumar(dias[DIAS[local.weekday()]], clase)
    res.por_franja = dict(franjas)
    res.por_dia_semana = dict(dias)
    return res
