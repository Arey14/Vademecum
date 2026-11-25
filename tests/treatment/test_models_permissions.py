from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from src.treatment.db import get_engine, init_db
from src.treatment.models import (
    EstadoToma,
    Origen,
    Medicacion,
    Rol,
    TipoPauta,
    TomaProgramada,
    Usuario,
    Vinculo,
)
from src.treatment.permissions import (
    PermisoDenegado,
    verificar_crear_medicacion,
    verificar_modificar_medicacion,
    verificar_registrar_toma,
)

T0 = datetime(2026, 11, 10, 11, 0, tzinfo=timezone.utc)


@pytest.fixture()
def session(tmp_path):
    engine = init_db(get_engine(tmp_path / "t.db"))
    with Session(engine) as s:
        yield s


@pytest.fixture()
def mundo(session):
    medico = Usuario(rol=Rol.MEDICO, nombre="Dra. Test", es_sintetico=True)
    otro_medico = Usuario(rol=Rol.MEDICO, nombre="Dr. Otro", es_sintetico=True)
    paciente = Usuario(rol=Rol.PACIENTE, nombre="Pac Uno", es_sintetico=True)
    otro_paciente = Usuario(rol=Rol.PACIENTE, nombre="Pac Dos", es_sintetico=True)
    session.add_all([medico, otro_medico, paciente, otro_paciente])
    session.commit()
    session.add(Vinculo(medico_id=medico.id, paciente_id=paciente.id))
    session.commit()

    def presc(origen, creado_por):
        p = Medicacion(
            paciente_id=paciente.id, creado_por_id=creado_por.id, origen=origen,
            producto_ref="tafirol-1g", producto_nombre="TAFIROL 1g",
            principios_activos=["Paracetamol"], dosis_cantidad=1, dosis_unidad="comprimido",
            tipo_pauta=TipoPauta.CADA_N_HORAS, cada_n_horas=8, inicio=T0,
        )
        session.add(p)
        session.commit()
        return p

    return dict(
        medico=medico, otro_medico=otro_medico, paciente=paciente, otro_paciente=otro_paciente,
        presc_medico=presc(Origen.MEDICO, medico), presc_paciente=presc(Origen.PACIENTE, paciente),
    )


def test_roundtrip_utc_y_json(session, mundo):
    p = session.get(Medicacion, mundo["presc_medico"].id)
    assert p.inicio == T0 and p.inicio.tzinfo is not None
    assert p.principios_activos == ["Paracetamol"]


def test_rechaza_datetime_sin_zona(session, mundo):
    session.add(TomaProgramada(medicacion_id=mundo["presc_medico"].id, fecha_hora_prevista=datetime(2026, 11, 10, 8)))
    with pytest.raises(Exception, match="zona horaria"):
        session.commit()


def test_no_duplica_la_misma_toma(session, mundo):
    pid = mundo["presc_medico"].id
    session.add(TomaProgramada(medicacion_id=pid, fecha_hora_prevista=T0))
    session.commit()
    session.add(TomaProgramada(medicacion_id=pid, fecha_hora_prevista=T0 + timedelta(seconds=0)))
    with pytest.raises(IntegrityError):
        session.commit()


def test_estado_toma_por_defecto_pendiente(session, mundo):
    t = TomaProgramada(medicacion_id=mundo["presc_medico"].id, fecha_hora_prevista=T0)
    session.add(t)
    session.commit()
    assert session.get(TomaProgramada, t.id).estado == EstadoToma.PENDIENTE


# --- permisos -------------------------------------------------------------- #
def test_medico_vinculado_puede_modificar_lo_del_medico(session, mundo):
    verificar_modificar_medicacion(session, mundo["medico"], mundo["presc_medico"])


def test_paciente_no_puede_modificar_lo_del_medico(session, mundo):
    with pytest.raises(PermisoDenegado):
        verificar_modificar_medicacion(session, mundo["paciente"], mundo["presc_medico"])


def test_medico_no_vinculado_no_puede_modificar(session, mundo):
    with pytest.raises(PermisoDenegado):
        verificar_modificar_medicacion(session, mundo["otro_medico"], mundo["presc_medico"])


def test_paciente_modifica_lo_propio_pero_no_el_medico_ni_otro_paciente(session, mundo):
    verificar_modificar_medicacion(session, mundo["paciente"], mundo["presc_paciente"])
    with pytest.raises(PermisoDenegado):
        verificar_modificar_medicacion(session, mundo["medico"], mundo["presc_paciente"])
    with pytest.raises(PermisoDenegado):
        verificar_modificar_medicacion(session, mundo["otro_paciente"], mundo["presc_paciente"])


def test_crear_medicacion_segun_rol(session, mundo):
    pid = mundo["paciente"].id
    verificar_crear_medicacion(session, mundo["medico"], pid, Origen.MEDICO)
    verificar_crear_medicacion(session, mundo["paciente"], pid, Origen.PACIENTE)
    for actor, origen in [
        (mundo["paciente"], Origen.MEDICO),       # paciente no crea esquema médico
        (mundo["otro_medico"], Origen.MEDICO),    # médico sin vínculo
        (mundo["medico"], Origen.PACIENTE),       # médico no agrega "por el paciente"
        (mundo["otro_paciente"], Origen.PACIENTE),
    ]:
        with pytest.raises(PermisoDenegado):
            verificar_crear_medicacion(session, actor, pid, origen)


def test_solo_el_paciente_tilda_sus_tomas(mundo):
    verificar_registrar_toma(mundo["paciente"], mundo["paciente"].id)
    for actor in (mundo["medico"], mundo["otro_paciente"]):
        with pytest.raises(PermisoDenegado):
            verificar_registrar_toma(actor, mundo["paciente"].id)
