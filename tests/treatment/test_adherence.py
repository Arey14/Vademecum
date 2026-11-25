from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.treatment.adherence import (
    CUMPLIDA,
    FUERA_DE_VENTANA,
    OMITIDA,
    PENDIENTE,
    calcular_adherencia,
    clasificar_toma,
)
from src.treatment.models import EstadoToma

BA = ZoneInfo("America/Argentina/Buenos_Aires")
PREVISTA = datetime(2026, 11, 10, 8, 0, tzinfo=BA)  # martes
AHORA = datetime(2026, 11, 12, 12, 0, tzinfo=BA)


def toma(prevista=PREVISTA, estado=EstadoToma.PENDIENTE, real=None):
    return SimpleNamespace(fecha_hora_prevista=prevista, estado=estado, fecha_hora_real=real)


@pytest.mark.parametrize(
    "minutos, esperado",
    [(0, CUMPLIDA), (60, CUMPLIDA), (-60, CUMPLIDA), (61, FUERA_DE_VENTANA), (-90, FUERA_DE_VENTANA)],
)
def test_ventana_de_60_minutos(minutos, esperado):
    t = toma(estado=EstadoToma.TOMADA, real=PREVISTA + timedelta(minutes=minutos))
    assert clasificar_toma(t, AHORA) == esperado


def test_pendiente_vencida_cuenta_como_omitida():
    assert clasificar_toma(toma(), AHORA) == OMITIDA


def test_pendiente_dentro_de_la_ventana_sigue_pendiente():
    ahora = PREVISTA + timedelta(minutes=59)
    assert clasificar_toma(toma(), ahora) == PENDIENTE


def test_omitida_explicita():
    assert clasificar_toma(toma(estado=EstadoToma.OMITIDA), AHORA) == OMITIDA


def test_ventana_parametrizable():
    t = toma(estado=EstadoToma.TOMADA, real=PREVISTA + timedelta(minutes=90))
    assert clasificar_toma(t, AHORA, ventana_min=120) == CUMPLIDA


def test_adherencia_global_y_pendientes_no_cuentan():
    d = lambda dia, h: datetime(2026, 11, dia, h, 0, tzinfo=BA)  # noqa: E731
    tomas = [
        toma(d(10, 8), EstadoToma.TOMADA, d(10, 8)),                       # cumplida
        toma(d(10, 20), EstadoToma.TOMADA, d(10, 20) + timedelta(hours=3)),  # fuera de ventana
        toma(d(11, 8), EstadoToma.OMITIDA),                                # omitida
        toma(d(11, 20)),                                                   # vencida -> omitida
        toma(datetime(2026, 11, 12, 20, 0, tzinfo=BA)),                    # futura -> pendiente
    ]
    r = calcular_adherencia(tomas, AHORA)
    assert (r.global_.cumplidas, r.global_.fuera_de_ventana, r.global_.omitidas) == (1, 1, 2)
    assert r.global_.total == 4
    assert r.global_.adherencia == pytest.approx(0.25)
    assert r.pendientes == 1


def test_adherencia_por_franja_y_dia_de_semana():
    d = lambda dia, h: datetime(2026, 11, dia, h, 0, tzinfo=BA)  # noqa: E731
    tomas = [
        toma(d(10, 8), EstadoToma.TOMADA, d(10, 8)),  # martes mañana, cumplida
        toma(d(11, 8), EstadoToma.TOMADA, d(11, 8)),  # miércoles mañana, cumplida
        toma(d(10, 22), EstadoToma.OMITIDA),          # martes noche, omitida
        toma(d(11, 22), EstadoToma.OMITIDA),          # miércoles noche, omitida
    ]
    r = calcular_adherencia(tomas, AHORA)
    assert r.por_franja["mañana"].adherencia == 1.0
    assert r.por_franja["noche"].adherencia == 0.0
    assert r.por_dia_semana["martes"].total == 2
    assert r.por_dia_semana["miércoles"].total == 2


def test_sin_tomas_vencidas_la_adherencia_es_none():
    r = calcular_adherencia([toma(datetime(2026, 11, 20, 8, tzinfo=BA))], AHORA)
    assert r.global_.adherencia is None
    assert r.pendientes == 1


def test_ahora_exige_zona_horaria():
    with pytest.raises(ValueError):
        calcular_adherencia([], datetime(2026, 11, 12, 12))
