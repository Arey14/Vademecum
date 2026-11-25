from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.treatment.models import TipoPauta
from src.treatment.schemas import MedicacionInput

BASE = dict(
    paciente_id=1,
    producto_ref="tafirol-1g",
    dosis_cantidad=1,
    dosis_unidad="comprimido",
    inicio=datetime(2026, 11, 10, 8, tzinfo=timezone.utc),
)


def test_valida_y_normaliza_horarios():
    p = MedicacionInput(**BASE, tipo_pauta=TipoPauta.HORARIOS_FIJOS, horarios_fijos=["20:00", "8:00".zfill(5), "08:00"])
    assert p.horarios_fijos == ["08:00", "20:00"]


@pytest.mark.parametrize(
    "extra",
    [
        dict(tipo_pauta=TipoPauta.HORARIOS_FIJOS),                       # sin horarios
        dict(tipo_pauta=TipoPauta.HORARIOS_FIJOS, horarios_fijos=["8am"]),  # formato inválido
        dict(tipo_pauta=TipoPauta.CADA_N_HORAS),                         # falta cada_n_horas
        dict(tipo_pauta=TipoPauta.A_DEMANDA),                            # falta max_por_dia
        dict(tipo_pauta=TipoPauta.CADA_N_HORAS, cada_n_horas=8, dosis_cantidad=0),
    ],
)
def test_rechaza_pautas_inconsistentes(extra):
    with pytest.raises(ValidationError):
        MedicacionInput(**{**BASE, **extra})


def test_exige_zona_horaria_en_inicio():
    with pytest.raises(ValidationError):
        MedicacionInput(**{**BASE, "inicio": datetime(2026, 11, 10, 8)}, tipo_pauta=TipoPauta.CADA_N_HORAS, cada_n_horas=8)


def test_a_demanda_valido():
    p = MedicacionInput(**BASE, tipo_pauta=TipoPauta.A_DEMANDA, max_por_dia=3)
    assert p.max_por_dia == 3 and p.duracion_dias is None
