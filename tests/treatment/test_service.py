from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from src.treatment import service
from src.treatment.db import get_engine, init_db
from src.treatment.models import (
    EstadoMedicacion,
    EstadoToma,
    Medicacion,
    Origen,
    Rol,
    TipoPauta,
    TomaProgramada,
    Usuario,
    Vinculo,
)
from src.treatment.permissions import PermisoDenegado
from src.treatment.schemas import MedicacionInput
from src.treatment.service import (
    EstadoInvalido,
    ProductoNoEncontrado,
    ProductoResuelto,
    ServicioError,
)

BA = ZoneInfo("America/Argentina/Buenos_Aires")
AHORA = datetime(2026, 11, 10, 8, 0, tzinfo=BA)  # martes 08:00


def resolver(ref):
    catalogo = {
        "tafirol-1g": ProductoResuelto("TAFIROL 1g", ["Paracetamol"]),
        "ibupirac-400": ProductoResuelto("IBUPIRAC 400", ["Ibuprofeno"]),
        "paracetamol-gen": ProductoResuelto("PARACETAMOL GENERICO", ["PARACETAMOL "]),  # mismo principio
        "paracetamol-ibu": ProductoResuelto("PARACETAMOL IBU", ["Paracetamol", "Ibuprofeno"]),
        "desconocido-a": ProductoResuelto("DESCONOCIDO A", []),
        "desconocido-b": ProductoResuelto("DESCONOCIDO B", []),
    }
    if ref not in catalogo:
        raise ProductoNoEncontrado(ref)
    return catalogo[ref]


@pytest.fixture()
def session(tmp_path):
    with Session(init_db(get_engine(tmp_path / "t.db"))) as s:
        yield s


@pytest.fixture()
def mundo(session):
    medico = Usuario(rol=Rol.MEDICO, nombre="Dra. Test")
    otro_medico = Usuario(rol=Rol.MEDICO, nombre="Dr. Otro")
    paciente = Usuario(rol=Rol.PACIENTE, nombre="Pac Uno")
    session.add_all([medico, otro_medico, paciente])
    session.commit()
    session.add(Vinculo(medico_id=medico.id, paciente_id=paciente.id))
    session.commit()
    return dict(medico=medico, otro_medico=otro_medico, paciente=paciente)


def data(mundo, **kw):
    base = dict(
        paciente_id=mundo["paciente"].id,
        producto_ref="tafirol-1g",
        dosis_cantidad=1,
        dosis_unidad="comprimido",
        tipo_pauta=TipoPauta.HORARIOS_FIJOS,
        horarios_fijos=["08:00", "20:00"],
        inicio=AHORA,
        duracion_dias=7,
    )
    return MedicacionInput(**{**base, **kw})


def tomas_de(session, med_id):
    return session.exec(
        select(TomaProgramada)
        .where(TomaProgramada.medicacion_id == med_id)
        .order_by(TomaProgramada.fecha_hora_prevista)
    ).all()


@pytest.fixture()
def indicada(session, mundo):
    return service.indicar_medicacion(
        session, mundo["medico"], data(mundo), resolver, ahora=AHORA
    )


# --- crear ---------------------------------------------------------------- #
def test_indicar_crea_medicacion_con_snapshot_y_cronograma(session, indicada):
    assert indicada.origen == Origen.MEDICO and indicada.estado == EstadoMedicacion.VIGENTE
    assert indicada.producto_nombre == "TAFIROL 1g"
    assert indicada.principios_activos == ["Paracetamol"]
    assert len(tomas_de(session, indicada.id)) == 14  # 7 días x 2 tomas


def test_indicar_requiere_medico_vinculado(session, mundo):
    for actor in (mundo["paciente"], mundo["otro_medico"]):
        with pytest.raises(PermisoDenegado):
            service.indicar_medicacion(session, actor, data(mundo), resolver, ahora=AHORA)
    assert session.exec(select(Medicacion)).all() == []


def test_producto_inexistente_no_deja_nada_a_medias(session, mundo):
    with pytest.raises(ProductoNoEncontrado):
        service.indicar_medicacion(
            session, mundo["medico"], data(mundo, producto_ref="no-existe"), resolver, ahora=AHORA
        )
    assert session.exec(select(Medicacion)).all() == []


def test_paciente_agrega_medicacion_propia(session, mundo):
    med = service.agregar_medicacion_propia(
        session, mundo["paciente"], data(mundo, producto_ref="ibupirac-400"), resolver, ahora=AHORA
    )
    assert med.origen == Origen.PACIENTE and med.creado_por_id == mundo["paciente"].id
    with pytest.raises(PermisoDenegado):
        service.agregar_medicacion_propia(session, mundo["medico"], data(mundo), resolver, ahora=AHORA)


def test_a_demanda_no_genera_tomas(session, mundo):
    med = service.indicar_medicacion(
        session, mundo["medico"],
        data(mundo, tipo_pauta=TipoPauta.A_DEMANDA, horarios_fijos=[], max_por_dia=3, duracion_dias=None),
        resolver, ahora=AHORA,
    )
    assert med.max_por_dia == 3 and tomas_de(session, med.id) == []


# --- versionar ------------------------------------------------------------ #
def test_versionar_cierra_la_anterior_y_crea_la_nueva(session, mundo, indicada):
    ahora = AHORA + timedelta(days=2, hours=4)  # jueves 12:00 (pasaron 4 tomas)
    nueva = service.versionar_medicacion(
        session, mundo["medico"], indicada.id, {"dosis_cantidad": 2}, ahora=ahora
    )
    session.refresh(indicada)
    assert indicada.estado == EstadoMedicacion.REEMPLAZADA
    assert indicada.vigente_hasta == ahora
    assert nueva.reemplaza_a_id == indicada.id and nueva.estado == EstadoMedicacion.VIGENTE
    assert nueva.dosis_cantidad == 2 and nueva.creado_por_id == mundo["medico"].id
    assert nueva.producto_nombre == "TAFIROL 1g" and nueva.origen == Origen.MEDICO


def test_versionar_conserva_historial_y_borra_solo_futuras_pendientes(session, mundo, indicada):
    # el paciente tildó la primera toma
    primera = tomas_de(session, indicada.id)[0]
    service.registrar_toma(session, mundo["paciente"], primera.id, cuando=AHORA, ahora=AHORA)
    ahora = AHORA + timedelta(days=2, hours=4)
    nueva = service.versionar_medicacion(
        session, mundo["medico"], indicada.id, {"dosis_cantidad": 2}, ahora=ahora
    )
    viejas = tomas_de(session, indicada.id)
    assert all(t.fecha_hora_prevista < ahora for t in viejas)  # no quedan futuras
    assert viejas[0].estado == EstadoToma.TOMADA                 # el historial sigue
    assert len(viejas) == 5                                      # mar 08/20, mié 08/20 y jue 08:00
    nuevas = tomas_de(session, nueva.id)
    assert all(t.fecha_hora_prevista >= ahora for t in nuevas)
    assert not {t.fecha_hora_prevista for t in viejas} & {t.fecha_hora_prevista for t in nuevas}


def test_versionar_conserva_la_fecha_de_fin(session, mundo, indicada):
    fin_original = indicada.fin
    assert fin_original == AHORA + timedelta(days=7)
    ahora = AHORA + timedelta(days=2, hours=4)
    nueva = service.versionar_medicacion(
        session, mundo["medico"], indicada.id, {"horarios_fijos": ["09:00"]}, ahora=ahora
    )
    ultima = tomas_de(session, nueva.id)[-1].fecha_hora_prevista
    assert ultima < fin_original
    assert nueva.fin == fin_original  # se hereda el fin exacto: ni una dosis más ni una menos
    assert nueva.horarios_fijos == ["09:00"]


def test_versionar_cambia_de_tipo_de_pauta_y_limpia_campos(session, mundo, indicada):
    nueva = service.versionar_medicacion(
        session, mundo["medico"], indicada.id,
        {"tipo_pauta": TipoPauta.CADA_N_HORAS, "cada_n_horas": 8}, ahora=AHORA + timedelta(hours=1),
    )
    assert nueva.tipo_pauta == TipoPauta.CADA_N_HORAS and nueva.horarios_fijos == []


def test_paciente_no_puede_versionar_lo_del_medico(session, mundo, indicada):
    with pytest.raises(PermisoDenegado):
        service.versionar_medicacion(session, mundo["paciente"], indicada.id, {"dosis_cantidad": 9}, ahora=AHORA)
    session.refresh(indicada)
    assert indicada.estado == EstadoMedicacion.VIGENTE and indicada.dosis_cantidad == 1


def test_medico_no_puede_versionar_lo_del_paciente(session, mundo):
    propia = service.agregar_medicacion_propia(
        session, mundo["paciente"], data(mundo, producto_ref="ibupirac-400"), resolver, ahora=AHORA
    )
    with pytest.raises(PermisoDenegado):
        service.versionar_medicacion(session, mundo["medico"], propia.id, {"dosis_cantidad": 2}, ahora=AHORA)
    nueva = service.versionar_medicacion(session, mundo["paciente"], propia.id, {"dosis_cantidad": 2}, ahora=AHORA)
    assert nueva.origen == Origen.PACIENTE


def test_cambio_de_marca_con_el_mismo_principio_activo(session, mundo, indicada):
    nueva = service.versionar_medicacion(
        session, mundo["medico"], indicada.id, {"producto_ref": "paracetamol-gen"},
        ahora=AHORA + timedelta(days=1), resolver=resolver,
    )
    assert nueva.producto_ref == "paracetamol-gen" and nueva.producto_nombre == "PARACETAMOL GENERICO"
    assert nueva.principios_activos == ["PARACETAMOL "]  # snapshot del producto nuevo
    session.refresh(indicada)
    assert indicada.estado == EstadoMedicacion.REEMPLAZADA and indicada.producto_ref == "tafirol-1g"
    assert nueva.reemplaza_a_id == indicada.id and nueva.fin == indicada.fin


@pytest.mark.parametrize(
    "nuevo_ref",
    ["ibupirac-400", "paracetamol-ibu"],  # otra droga / agrega una droga
)
def test_cambio_de_principio_activo_se_rechaza_y_no_modifica_nada(session, mundo, indicada, nuevo_ref):
    antes = len(tomas_de(session, indicada.id))
    with pytest.raises(ServicioError, match="cambia el principio activo"):
        service.versionar_medicacion(
            session, mundo["medico"], indicada.id, {"producto_ref": nuevo_ref},
            ahora=AHORA + timedelta(days=1), resolver=resolver,
        )
    session.refresh(indicada)
    assert indicada.estado == EstadoMedicacion.VIGENTE and len(tomas_de(session, indicada.id)) == antes
    assert len(session.exec(select(Medicacion)).all()) == 1


def test_cambio_de_marca_sin_resolver_se_rechaza(session, mundo, indicada):
    with pytest.raises(ServicioError, match="resolver"):
        service.versionar_medicacion(
            session, mundo["medico"], indicada.id, {"producto_ref": "paracetamol-gen"}, ahora=AHORA
        )


def test_cambio_de_marca_sin_principio_activo_conocido_se_rechaza(session, mundo):
    # Dos productos sin principio activo NO se consideran "el mismo": no se puede verificar.
    med = service.indicar_medicacion(
        session, mundo["medico"], data(mundo, producto_ref="desconocido-a"), resolver, ahora=AHORA
    )
    with pytest.raises(ServicioError, match="falta el principio activo"):
        service.versionar_medicacion(
            session, mundo["medico"], med.id, {"producto_ref": "desconocido-b"},
            ahora=AHORA, resolver=resolver,
        )


def test_campo_desconocido_se_rechaza(session, mundo, indicada):
    with pytest.raises(ServicioError, match="no modificables"):
        service.versionar_medicacion(session, mundo["medico"], indicada.id, {"paciente_id": 99}, ahora=AHORA)


def test_no_se_versiona_una_medicacion_ya_reemplazada(session, mundo, indicada):
    service.versionar_medicacion(session, mundo["medico"], indicada.id, {"dosis_cantidad": 2}, ahora=AHORA)
    with pytest.raises(EstadoInvalido):
        service.versionar_medicacion(session, mundo["medico"], indicada.id, {"dosis_cantidad": 3}, ahora=AHORA)


def test_versionar_con_datos_invalidos_es_atomico(session, mundo, indicada):
    antes = len(tomas_de(session, indicada.id))
    with pytest.raises(ValidationError):
        service.versionar_medicacion(
            session, mundo["medico"], indicada.id,
            {"tipo_pauta": TipoPauta.CADA_N_HORAS},  # falta cada_n_horas
            ahora=AHORA + timedelta(days=1),
        )
    session.refresh(indicada)
    assert indicada.estado == EstadoMedicacion.VIGENTE and indicada.vigente_hasta is None
    assert len(tomas_de(session, indicada.id)) == antes
    assert len(session.exec(select(Medicacion)).all()) == 1


def test_no_versiona_si_ya_cumplio_la_duracion(session, mundo, indicada):
    with pytest.raises(EstadoInvalido, match="duración"):
        service.versionar_medicacion(
            session, mundo["medico"], indicada.id, {"dosis_cantidad": 2}, ahora=AHORA + timedelta(days=8)
        )


# --- suspender ------------------------------------------------------------ #
def test_suspender_borra_futuras_y_conserva_pasadas(session, mundo, indicada):
    ahora = AHORA + timedelta(days=1, hours=1)
    service.suspender_medicacion(session, mundo["medico"], indicada.id, ahora=ahora)
    session.refresh(indicada)
    assert indicada.estado == EstadoMedicacion.SUSPENDIDA
    assert all(t.fecha_hora_prevista < ahora for t in tomas_de(session, indicada.id))
    with pytest.raises(PermisoDenegado):
        service.suspender_medicacion(session, mundo["paciente"], indicada.id, ahora=ahora)


# --- registrar toma ---------------------------------------------------------- #
def test_paciente_tilda_y_omite_tomas(session, mundo, indicada):
    t1, t2, *_ = tomas_de(session, indicada.id)
    r1 = service.registrar_toma(session, mundo["paciente"], t1.id, cuando=AHORA + timedelta(minutes=5))
    assert r1.estado == EstadoToma.TOMADA and r1.fecha_hora_real == AHORA + timedelta(minutes=5)
    r2 = service.registrar_toma(session, mundo["paciente"], t2.id, estado=EstadoToma.OMITIDA)
    assert r2.estado == EstadoToma.OMITIDA and r2.fecha_hora_real is None
    for actor in (mundo["medico"], mundo["otro_medico"]):
        with pytest.raises(PermisoDenegado):
            service.registrar_toma(session, actor, t1.id)


# --- mantenimiento -------------------------------------------------------- #
def test_mantenimiento_extiende_cronicos_sin_duplicar(session, mundo):
    cronica = service.indicar_medicacion(
        session, mundo["medico"],
        data(mundo, horarios_fijos=["09:00"], duracion_dias=None), resolver, ahora=AHORA,
    )
    assert len(tomas_de(session, cronica.id)) == 14  # horizonte por defecto
    r = service.mantenimiento(session, ahora=AHORA + timedelta(days=10))
    assert r == {"finalizadas": 0, "tomas_agregadas": 10}
    assert len(tomas_de(session, cronica.id)) == 24
    assert service.mantenimiento(session, ahora=AHORA + timedelta(days=10))["tomas_agregadas"] == 0


def test_mantenimiento_finaliza_las_que_cumplieron_su_duracion(session, mundo, indicada):
    r = service.mantenimiento(session, ahora=AHORA + timedelta(days=8))
    session.refresh(indicada)
    assert r["finalizadas"] == 1 and indicada.estado == EstadoMedicacion.FINALIZADA
    assert indicada.vigente_hasta == AHORA + timedelta(days=7)
