from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from src.treatment.models import TipoPauta
from src.treatment.schedule import generar_cronograma

BA = ZoneInfo("America/Argentina/Buenos_Aires")


def dt(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=BA)


def test_horarios_fijos_siete_dias_son_14_tomas():
    tomas = generar_cronograma(
        tipo_pauta=TipoPauta.HORARIOS_FIJOS,
        inicio=dt(2026, 11, 10, 8),
        duracion_dias=7,
        horarios_fijos=["08:00", "20:00"],
    )
    assert len(tomas) == 14
    assert tomas[0] == dt(2026, 11, 10, 8)
    assert tomas[-1] == dt(2026, 11, 16, 20)
    assert tomas == sorted(tomas)


def test_horarios_fijos_inicio_a_mitad_del_dia_saltea_las_pasadas():
    tomas = generar_cronograma(
        tipo_pauta=TipoPauta.HORARIOS_FIJOS,
        inicio=dt(2026, 11, 10, 14),
        duracion_dias=7,
        horarios_fijos=["08:00", "20:00"],
    )
    assert tomas[0] == dt(2026, 11, 10, 20)  # la de las 08:00 ya pasó
    assert len(tomas) == 14  # 7 días * 2 tomas, sin pasarse de la duración


def test_horarios_fijos_desordenados_y_repetidos():
    tomas = generar_cronograma(
        tipo_pauta=TipoPauta.HORARIOS_FIJOS,
        inicio=dt(2026, 11, 10, 0),
        duracion_dias=1,
        horarios_fijos=["20:00", "08:00", "08:00"],
    )
    assert tomas == [dt(2026, 11, 10, 8), dt(2026, 11, 10, 20)]


def test_cada_8_horas_tres_por_dia():
    tomas = generar_cronograma(
        tipo_pauta=TipoPauta.CADA_N_HORAS,
        inicio=dt(2026, 11, 10, 6),
        duracion_dias=2,
        cada_n_horas=8,
    )
    assert [t.hour for t in tomas] == [6, 14, 22, 6, 14, 22]
    assert tomas[1] - tomas[0] == timedelta(hours=8)


def test_cronico_se_limita_al_horizonte():
    tomas = generar_cronograma(
        tipo_pauta=TipoPauta.HORARIOS_FIJOS,
        inicio=dt(2026, 11, 10, 0),
        duracion_dias=None,
        horarios_fijos=["09:00"],
        horizonte_dias=14,
    )
    assert len(tomas) == 14


def test_desde_genera_solo_hacia_adelante_y_no_repite_fase():
    # Tratamiento cada 8 h desde las 06:00; "hoy" es 11/11 a las 10:00.
    tomas = generar_cronograma(
        tipo_pauta=TipoPauta.CADA_N_HORAS,
        inicio=dt(2026, 11, 10, 6),
        duracion_dias=7,
        cada_n_horas=8,
        desde=dt(2026, 11, 11, 10),
        horizonte_dias=1,
    )
    assert tomas[0] == dt(2026, 11, 11, 14)  # mantiene la fase 06/14/22
    assert all(t >= dt(2026, 11, 11, 10) for t in tomas)
    assert all(t < dt(2026, 11, 12, 10) for t in tomas)


def test_a_demanda_no_tiene_cronograma():
    assert generar_cronograma(tipo_pauta=TipoPauta.A_DEMANDA, inicio=dt(2026, 11, 10, 8)) == []


def test_acepta_inicio_en_utc_y_devuelve_hora_local():
    inicio_utc = datetime(2026, 11, 10, 11, 0, tzinfo=timezone.utc)  # 08:00 en Buenos Aires
    tomas = generar_cronograma(
        tipo_pauta=TipoPauta.HORARIOS_FIJOS,
        inicio=inicio_utc,
        duracion_dias=1,
        horarios_fijos=["08:00"],
    )
    assert tomas == [dt(2026, 11, 10, 8)]


def test_exige_zona_horaria():
    with pytest.raises(ValueError, match="zona horaria"):
        generar_cronograma(
            tipo_pauta=TipoPauta.CADA_N_HORAS,
            inicio=datetime(2026, 11, 10, 8),
            cada_n_horas=8,
            duracion_dias=1,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(tipo_pauta=TipoPauta.HORARIOS_FIJOS, horarios_fijos=[]),
        dict(tipo_pauta=TipoPauta.HORARIOS_FIJOS, horarios_fijos=["25:00"]),
        dict(tipo_pauta=TipoPauta.CADA_N_HORAS, cada_n_horas=None),
        dict(tipo_pauta=TipoPauta.CADA_N_HORAS, cada_n_horas=0),
        dict(tipo_pauta=TipoPauta.HORARIOS_FIJOS, horarios_fijos=["08:00"], duracion_dias=0),
    ],
)
def test_entradas_invalidas(kwargs):
    with pytest.raises(ValueError):
        generar_cronograma(inicio=dt(2026, 11, 10, 8), **{"duracion_dias": 1, **kwargs})


def test_fin_explicito_recorta_la_ventana():
    tomas = generar_cronograma(
        tipo_pauta=TipoPauta.HORARIOS_FIJOS,
        inicio=dt(2026, 11, 10, 8),
        duracion_dias=7,
        fin=dt(2026, 11, 11, 12),
        horarios_fijos=["08:00", "20:00"],
    )
    assert tomas == [dt(2026, 11, 10, 8), dt(2026, 11, 10, 20), dt(2026, 11, 11, 8)]
