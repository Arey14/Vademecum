"""Generación determinística del cronograma de tomas.

Función pura (sin base de datos, sin LLM): dada una pauta devuelve los
datetimes de las tomas. Los LLMs no deben calcular horarios (ver PLAN.md §4).
"""
import math
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from src.treatment.models import TipoPauta

DEFAULT_TZ = "America/Argentina/Buenos_Aires"
HORIZONTE_DEFAULT_DIAS = 14
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(valor: str) -> time:
    m = _HHMM.match(valor.strip())
    if not m:
        raise ValueError(f"Horario inválido {valor!r}: usar formato HH:MM (24 h).")
    return time(int(m.group(1)), int(m.group(2)))


def generar_cronograma(
    *,
    tipo_pauta: TipoPauta,
    inicio: datetime,
    duracion_dias: int | None = None,
    fin: datetime | None = None,
    horarios_fijos: list[str] | None = None,
    cada_n_horas: int | None = None,
    desde: datetime | None = None,
    horizonte_dias: int = HORIZONTE_DEFAULT_DIAS,
    tz: str = DEFAULT_TZ,
) -> list[datetime]:
    """Devuelve las tomas programadas, ordenadas, como datetimes tz-aware.

    Ventana generada: [max(inicio, desde), min(inicio + duracion, fin, desde + horizonte)).
    - HORARIOS_FIJOS: cada día, a esas horas locales (zona `tz`).
    - CADA_N_HORAS: inicio, inicio + n h, inicio + 2n h... (tiempo transcurrido real).
    - A_DEMANDA: no hay tomas programadas -> [].
    Si `duracion_dias` es None (crónico) se genera solo hasta el horizonte.
    """
    if any(x is not None and x.tzinfo is None for x in (inicio, desde, fin)):
        raise ValueError("`inicio`, `desde` y `fin` deben ser datetimes con zona horaria.")
    if duracion_dias is not None and duracion_dias < 1:
        raise ValueError("`duracion_dias` debe ser >= 1 o None.")
    if horizonte_dias < 1:
        raise ValueError("`horizonte_dias` debe ser >= 1.")

    if tipo_pauta == TipoPauta.A_DEMANDA:
        return []

    zona = ZoneInfo(tz)
    inicio_utc = inicio.astimezone(timezone.utc)
    ini = max(inicio_utc, desde.astimezone(timezone.utc)) if desde else inicio_utc
    limite = ini + timedelta(days=horizonte_dias)
    if duracion_dias is not None:
        fin_efectivo = min(inicio_utc + timedelta(days=duracion_dias), limite)
    else:
        fin_efectivo = limite

    if fin is not None:
        fin_efectivo = min(fin_efectivo, fin.astimezone(timezone.utc))

    if tipo_pauta == TipoPauta.CADA_N_HORAS:
        if not cada_n_horas or cada_n_horas < 1:
            raise ValueError("CADA_N_HORAS requiere `cada_n_horas` >= 1.")
        paso = timedelta(hours=cada_n_horas)
        k = max(0, math.ceil((ini - inicio_utc) / paso))
        out = []
        t = inicio_utc + k * paso
        while t < fin_efectivo:
            out.append(t.astimezone(zona))
            t += paso
        return out

    if tipo_pauta == TipoPauta.HORARIOS_FIJOS:
        if not horarios_fijos:
            raise ValueError("HORARIOS_FIJOS requiere al menos un horario.")
        horas = sorted({parse_hhmm(h) for h in horarios_fijos})
        dia: date = ini.astimezone(zona).date()
        ultimo: date = fin_efectivo.astimezone(zona).date()
        out = []
        while dia <= ultimo:
            for h in horas:
                t = datetime.combine(dia, h, tzinfo=zona)
                if ini <= t.astimezone(timezone.utc) < fin_efectivo:
                    out.append(t)
            dia += timedelta(days=1)
        return out

    raise ValueError(f"Tipo de pauta no soportado: {tipo_pauta!r}")
