import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import Session, select

from src.treatment import service, snapshots
from src.treatment.db import get_engine, init_db
from src.treatment.models import (
    Alerta,
    Consulta,
    EstadoToma,
    EventoPaciente,
    Medicacion,
    Rol,
    Severidad,
    TipoAlerta,
    TipoEvento,
    TipoPauta,
    TomaProgramada,
    Usuario,
    Vinculo,
)
from src.treatment.permissions import PermisoDenegado
from src.treatment.schemas import MedicacionInput
from src.treatment.service import NoEncontrado, ProductoResuelto

BA = ZoneInfo("America/Argentina/Buenos_Aires")
T0 = datetime(2026, 11, 5, 8, 0, tzinfo=BA)      # jueves: se indica Tafirol 08:00 y 20:00 por 10 días
AHORA = datetime(2026, 11, 10, 8, 30, tzinfo=BA)  # martes 08:30


def resolver(ref):
    catalogo = {
        "tafirol-1g": ProductoResuelto("TAFIROL 1g", ["Paracetamol"]),
        "paracetamol-gen": ProductoResuelto("PARACETAMOL GENERICO", ["Paracetamol"]),
        "ibupirac-400": ProductoResuelto("IBUPIRAC 400", ["Ibuprofeno"]),
    }
    return catalogo[ref]


@pytest.fixture()
def session(tmp_path):
    with Session(init_db(get_engine(tmp_path / "t.db"))) as s:
        yield s


@pytest.fixture()
def mundo(session):
    medico = Usuario(rol=Rol.MEDICO, nombre="Dra. Test")
    otro = Usuario(rol=Rol.MEDICO, nombre="Dr. Otro")
    pac = Usuario(rol=Rol.PACIENTE, nombre="Pac Uno")
    pac2 = Usuario(rol=Rol.PACIENTE, nombre="Pac Dos")
    session.add_all([medico, otro, pac, pac2])
    session.commit()
    session.add(Vinculo(medico_id=medico.id, paciente_id=pac.id))
    session.commit()
    return dict(medico=medico, otro=otro, paciente=pac, otro_paciente=pac2)


def entrada(mundo, **kw):
    base = dict(
        paciente_id=mundo["paciente"].id, producto_ref="tafirol-1g", dosis_cantidad=1,
        dosis_unidad="comprimido", tipo_pauta=TipoPauta.HORARIOS_FIJOS,
        horarios_fijos=["08:00", "20:00"], inicio=T0, duracion_dias=10,
    )
    return MedicacionInput(**{**base, **kw})


@pytest.fixture()
def escenario(session, mundo):
    """Tafirol desde el jueves 5. Mañanas cumplidas en hora; noches: 5 y 6 tomadas 3 h tarde,
    7 omitida explícita, 8 y 9 sin registrar. Hoy martes 10 a las 08:30 la de las 08:00 sigue
    pendiente pero dentro de la ventana."""
    med = service.indicar_medicacion(session, mundo["medico"], entrada(mundo), resolver, ahora=T0)
    pac = mundo["paciente"]
    por_hora = {t.fecha_hora_prevista.astimezone(BA): t for t in session.exec(select(TomaProgramada)).all()}
    for dia in (5, 6, 7, 8, 9):
        t = por_hora[datetime(2026, 11, dia, 8, 0, tzinfo=BA)]
        service.registrar_toma(session, pac, t.id, cuando=t.fecha_hora_prevista + timedelta(minutes=10))
    for dia in (5, 6):
        t = por_hora[datetime(2026, 11, dia, 20, 0, tzinfo=BA)]
        service.registrar_toma(session, pac, t.id, cuando=t.fecha_hora_prevista + timedelta(hours=3))
    t = por_hora[datetime(2026, 11, 7, 20, 0, tzinfo=BA)]
    service.registrar_toma(session, pac, t.id, estado=EstadoToma.OMITIDA)
    return med


def ids_de(hechos):
    return {h.split(":")[0]: [] for h in hechos}


# --- estado_paciente ------------------------------------------------------- #
def test_estado_paciente_es_json_y_compacto(session, mundo, escenario):
    est = snapshots.estado_paciente(session, mundo["paciente"], mundo["paciente"].id, ahora=AHORA)
    texto = json.dumps(est, ensure_ascii=False)
    assert len(texto) < 3500  # orden de magnitud de unos pocos cientos de tokens
    assert est["medicacion_vigente"][0]["producto"] == "TAFIROL 1g"
    assert est["medicacion_vigente"][0]["pauta"] == "08:00, 20:00"
    assert est["medicacion_vigente"][0]["principios_activos"] == ["Paracetamol"]
    assert est["ahora"] == "2026-11-10T08:30-03:00"


def test_estado_paciente_proximas_y_sin_registrar(session, mundo, escenario):
    est = snapshots.estado_paciente(session, mundo["paciente"], mundo["paciente"].id, ahora=AHORA)
    # la de las 08:00 de hoy está pendiente y a 60 min: todavía no venció
    assert est["proximas_tomas"][0]["cuando"] == "2026-11-10T08:00-03:00"
    assert est["proximas_tomas"][1]["cuando"] == "2026-11-10T20:00-03:00"
    assert len(est["proximas_tomas"]) == 5
    # la noche del 9 (sin registrar) entra en las últimas 24 h; la del 8 no
    assert [t["cuando"] for t in est["tomas_sin_registrar_24h"]] == ["2026-11-09T20:00-03:00"]


def test_estado_paciente_adherencia_7d(session, mundo, escenario):
    est = snapshots.estado_paciente(session, mundo["paciente"], mundo["paciente"].id, ahora=AHORA)
    a = est["adherencia_7d"]
    # 5 mañanas cumplidas + noches: 2 fuera de ventana, 1 omitida, 2 sin registrar (omitidas)
    assert (a["cumplidas"], a["fuera_de_ventana"], a["omitidas"]) == (5, 2, 3)
    assert a["total"] == 10 and a["adherencia"] == 0.5
    assert a["por_producto"][0]["producto"] == "TAFIROL 1g"


def test_estado_paciente_alertas_abiertas_y_proxima_consulta(session, mundo, escenario):
    pac = mundo["paciente"]
    session.add(Alerta(
        paciente_id=pac.id, medicacion_id=escenario.id, tipo=TipoAlerta.INTERACCION,
        severidad=Severidad.AMARILLO, entre=["Paracetamol", "Alcohol"], explicacion="Evitar alcohol.",
    ))
    session.add(Alerta(
        paciente_id=pac.id, tipo=TipoAlerta.DUPLICIDAD, severidad=Severidad.ROJO,
        entre=["a"], explicacion="ya visto", visto_por_medico=True,
    ))
    session.add(Consulta(paciente_id=pac.id, medico_id=mundo["medico"].id, fecha=T0,
                         proxima_consulta=AHORA + timedelta(days=20)))
    session.add(Consulta(paciente_id=pac.id, medico_id=mundo["medico"].id, fecha=T0 - timedelta(days=90),
                         proxima_consulta=T0 - timedelta(days=60)))  # pasada: se ignora
    session.commit()
    est = snapshots.estado_paciente(session, pac, pac.id, ahora=AHORA)
    assert [a["severidad"] for a in est["alertas_abiertas"]] == ["amarillo"]
    assert est["proxima_consulta"] == "2026-11-30T08:30-03:00"


def test_estado_sin_medicacion(session, mundo):
    est = snapshots.estado_paciente(session, mundo["paciente"], mundo["paciente"].id, ahora=AHORA)
    assert est["medicacion_vigente"] == [] and est["proximas_tomas"] == []
    assert est["adherencia_7d"]["adherencia"] is None and est["proxima_consulta"] is None


def test_estado_solo_incluye_vigentes(session, mundo, escenario):
    service.suspender_medicacion(session, mundo["medico"], escenario.id, ahora=AHORA)
    est = snapshots.estado_paciente(session, mundo["paciente"], mundo["paciente"].id, ahora=AHORA)
    assert est["medicacion_vigente"] == [] and est["proximas_tomas"] == []
    assert est["adherencia_7d"]["total"] == 10  # el historial se conserva


# --- permisos --------------------------------------------------------------- #
def test_permisos_de_lectura(session, mundo, escenario):
    pid = mundo["paciente"].id
    snapshots.estado_paciente(session, mundo["medico"], pid, ahora=AHORA)      # médico vinculado
    for actor in (mundo["otro"], mundo["otro_paciente"]):
        for fn in (
            lambda a: snapshots.estado_paciente(session, a, pid, ahora=AHORA),
            lambda a: snapshots.digest_periodo(session, a, pid, T0, AHORA, ahora=AHORA),
            lambda a: snapshots.cambios_medicacion(session, a, pid, T0, AHORA),
        ):
            with pytest.raises(PermisoDenegado):
                fn(actor)
    with pytest.raises(NoEncontrado):
        snapshots.estado_paciente(session, mundo["medico"], 9999, ahora=AHORA)


# --- digest_periodo --------------------------------------------------------- #
def test_digest_detecta_patron_y_lista_omitidas(session, mundo, escenario):
    d = snapshots.digest_periodo(session, mundo["medico"], mundo["paciente"].id, T0, AHORA, ahora=AHORA)
    adh = d["adherencia"]
    assert adh["total"] == 10 and adh["cumplidas"] == 5
    assert adh["por_franja"]["mañana"]["adherencia"] == 1.0
    assert adh["por_franja"]["noche"]["adherencia"] == 0.0
    assert adh["peor_franja"] == "noche"
    motivos = sorted(o["motivo"] for o in d["omitidas"])
    assert motivos == ["marcada_omitida", "sin_registrar", "sin_registrar"]
    assert len(d["fuera_de_ventana"]) == 2
    assert d["fuera_de_ventana"][0]["real"] is not None


def test_digest_incluye_eventos_y_alertas_y_hechos_fuente_existen(session, mundo, escenario):
    pac = mundo["paciente"]
    session.add(EventoPaciente(
        paciente_id=pac.id, fecha_evento=T0 + timedelta(days=2), tipo=TipoEvento.SINTOMA,
        texto_original="me duele el estómago",
    ))
    session.add(Alerta(
        paciente_id=pac.id, tipo=TipoAlerta.INTERACCION, severidad=Severidad.AMARILLO,
        entre=["x", "y"], explicacion="e", creado_en=T0 + timedelta(days=1),
    ))
    session.commit()
    d = snapshots.digest_periodo(session, mundo["medico"], pac.id, T0 - timedelta(hours=1), AHORA, ahora=AHORA)
    assert d["eventos"][0]["texto"] == "me duele el estómago" and len(d["alertas"]) == 1
    json.dumps(d)  # serializable
    # invariante: cada hecho citado existe en la base
    tablas = {"toma": TomaProgramada, "evento": EventoPaciente, "alerta": Alerta, "med": Medicacion}
    assert d["hechos_fuente"]
    for hecho in d["hechos_fuente"]:
        tipo, id_ = hecho.split(":")
        assert session.get(tablas[tipo], int(id_)) is not None, hecho


def test_digest_acota_las_listas_e_informa_el_resto(session, mundo, escenario, monkeypatch):
    monkeypatch.setattr(snapshots, "MAX_LISTA", 3)
    assert snapshots._limitar([1, 2, 3, 4, 5], 3) == ([1, 2, 3], 2)
    d = snapshots.digest_periodo(session, mundo["medico"], mundo["paciente"].id, T0,
                                 T0 + timedelta(days=11), ahora=T0 + timedelta(days=30))
    assert len(d["omitidas"]) == snapshots.MAX_LISTA
    assert d["adherencia"]["omitidas"] == len(d["omitidas"]) + d["omitidas_no_listadas"]  # el conteo es exacto


def test_digest_no_cuenta_lo_que_aun_no_vencio(session, mundo, escenario):
    d = snapshots.digest_periodo(session, mundo["medico"], mundo["paciente"].id,
                                 AHORA - timedelta(hours=1), AHORA + timedelta(days=1), ahora=AHORA)
    assert d["adherencia"]["total"] == 0 and d["adherencia"]["pendientes"] >= 1
    assert d["adherencia"]["adherencia"] is None and d["adherencia"]["peor_franja"] is None


# --- cambios_medicacion / diff_medicacion --------------------------------- #
def test_cambios_agregada_modificada_suspendida(session, mundo, escenario):
    medico, pac = mundo["medico"], mundo["paciente"]
    corte = AHORA - timedelta(days=1)  # lunes 08:30
    # lunes 12:00: el médico sube la dosis y cambia a genérico (mismo principio activo)
    nueva = service.versionar_medicacion(
        session, medico, escenario.id, {"dosis_cantidad": 2, "producto_ref": "paracetamol-gen"},
        ahora=corte + timedelta(hours=3), resolver=resolver,
    )
    # el paciente suma su propio ibuprofeno
    propia = service.agregar_medicacion_propia(
        session, pac, entrada(mundo, producto_ref="ibupirac-400", horarios_fijos=["09:00"], duracion_dias=3,
                inicio=corte + timedelta(hours=5)),
        resolver, ahora=corte + timedelta(hours=5),
    )
    service.suspender_medicacion(session, medico, nueva.id, ahora=AHORA - timedelta(hours=1))

    c = snapshots.cambios_medicacion(session, medico, pac.id, corte, AHORA)
    assert [m["producto"] for m in c["agregadas"]] == ["IBUPIRAC 400"]
    assert c["agregadas"][0]["origen"] == "paciente"
    (mod,) = c["modificadas"]
    assert mod["cambio_de_marca"] is True and mod["reemplaza_a"] == f"med:{escenario.id}"
    assert {x["campo"] for x in mod["cambios"]} == {"producto_ref", "dosis_cantidad"}
    dosis = next(x for x in mod["cambios"] if x["campo"] == "dosis_cantidad")
    assert (dosis["antes"], dosis["despues"]) == (1, 2)
    assert [m["id"] for m in c["suspendidas"]] == [f"med:{nueva.id}"]
    assert c["hay_cambios"] and f"med:{propia.id}" in c["hechos_fuente"]
    json.dumps(c)


def test_cambios_sin_novedades(session, mundo, escenario):
    c = snapshots.cambios_medicacion(session, mundo["medico"], mundo["paciente"].id,
                                     T0 + timedelta(days=1), AHORA)
    assert c["hay_cambios"] is False and c["hechos_fuente"] == []


def test_cambios_finalizadas(session, mundo, escenario):
    c = snapshots.cambios_medicacion(session, mundo["medico"], mundo["paciente"].id,
                                     AHORA, AHORA + timedelta(days=10))
    assert [m["id"] for m in c["finalizadas"]] == [f"med:{escenario.id}"]


def test_diff_medicacion_entre_consultas(session, mundo, escenario):
    medico, pac = mundo["medico"], mundo["paciente"]
    c1 = Consulta(paciente_id=pac.id, medico_id=medico.id, fecha=T0)
    c2 = Consulta(paciente_id=pac.id, medico_id=medico.id, fecha=AHORA)
    session.add_all([c1, c2])
    session.commit()
    service.versionar_medicacion(session, medico, escenario.id, {"horarios_fijos": ["09:00", "21:00"]},
                                 consulta_id=c2.id, ahora=AHORA)
    d = snapshots.diff_medicacion(session, medico, c1.id, c2.id)
    assert d["consultas"] == [f"consulta:{c1.id}", f"consulta:{c2.id}"]
    # incluye la indicación original (mismo día de c1 queda fuera: el intervalo es abierto en `desde`)
    assert len(d["modificadas"]) == 1 and d["modificadas"][0]["cambios"][0]["campo"] == "horarios_fijos"
    # el orden de los argumentos no importa
    assert snapshots.diff_medicacion(session, medico, c2.id, c1.id)["modificadas"] == d["modificadas"]


def test_diff_medicacion_valida_consultas(session, mundo):
    c = Consulta(paciente_id=mundo["paciente"].id, medico_id=mundo["medico"].id, fecha=T0)
    session.add(c)
    session.commit()
    with pytest.raises(NoEncontrado):
        snapshots.diff_medicacion(session, mundo["medico"], c.id, 999)
