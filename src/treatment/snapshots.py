"""Resúmenes de estado para el LLM (solo lectura, determinísticos).

El LLM nunca ve las tablas crudas: recibe estos diccionarios, armados por código, y
solo redacta sobre ellos (ver docs/MODELO_DATOS.md §6). Todo lo que se cuenta o se
calcula (adherencia, cambios de medicación, próximas tomas) se resuelve acá.

Convenciones:
- Salida JSON-serializable (`json.dumps` directo). Fechas en ISO 8601 con la zona del paciente.
- Cada hecho lleva un id (`med:12`, `toma:7`, `evento:3`, `alerta:5`); `digest_periodo` y
  `cambios_medicacion` devuelven además `hechos_fuente`, que se guarda en `Resumen.hechos_fuente`
  para evaluar si un resumen cubre los hechos relevantes y si inventa alguno.
- `texto` de los eventos es texto escrito por el paciente: el prompt debe tratarlo
  como dato, nunca como instrucciones.
- Permisos: lee el propio paciente o un médico vinculado (`verificar_ver_paciente`).
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from src.treatment.adherence import (
    DIAS,
    FRANJAS,
    FUERA_DE_VENTANA,
    OMITIDA,
    VENTANA_DEFAULT_MIN,
    Conteo,
    calcular_adherencia,
    clasificar_toma,
)
from src.treatment.models import (
    Alerta,
    Consulta,
    EstadoMedicacion,
    EstadoToma,
    EventoPaciente,
    Medicacion,
    TipoPauta,
    TomaProgramada,
    Usuario,
    utcnow,
)
from src.treatment.permissions import verificar_ver_paciente
from src.treatment.service import NoEncontrado

MAX_LISTA = 20          # tope de ítems por lista en los digests (se informa cuántos quedan fuera)
MIN_TOMAS_PATRON = 3    # mínimo de tomas en una franja/día para señalarla como la peor

# Campos de la medicación que se comparan al describir un cambio de versión.
CAMPOS_COMPARABLES = (
    "producto_ref", "dosis_cantidad", "dosis_unidad", "tipo_pauta", "horarios_fijos",
    "cada_n_horas", "max_por_dia", "con_comida", "indicaciones_medico", "fin",
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _paciente(session: Session, actor: Usuario, paciente_id: int) -> Usuario:
    paciente = session.get(Usuario, paciente_id)
    if paciente is None:
        raise NoEncontrado(f"No existe el paciente {paciente_id}.")
    verificar_ver_paciente(session, actor, paciente_id)
    return paciente


def _iso(dt: datetime | None, zona: ZoneInfo) -> str | None:
    return None if dt is None else dt.astimezone(zona).isoformat(timespec="minutes")


def _conteo(c: Conteo) -> dict:
    return {
        "cumplidas": c.cumplidas,
        "fuera_de_ventana": c.fuera_de_ventana,
        "omitidas": c.omitidas,
        "total": c.total,
        "adherencia": None if c.adherencia is None else round(c.adherencia, 3),
    }


def _peor(conteos: dict[str, Conteo], orden: tuple[str, ...]) -> str | None:
    """Franja/día con menor adherencia entre los que tienen suficientes tomas.
    Si todos rinden igual no hay patrón y devuelve None."""
    candidatos = [
        (conteos[k].adherencia, i, k)
        for i, k in enumerate(orden)
        if k in conteos and conteos[k].total >= MIN_TOMAS_PATRON
    ]
    if not candidatos:
        return None
    peor, mejor = min(candidatos), max(candidatos)
    return peor[2] if peor[0] < mejor[0] else None


def _adherencia_dict(tomas: list, ahora: datetime, tz: str, ventana_min: int) -> dict:
    res = calcular_adherencia(tomas, ahora, ventana_min, tz)
    return {
        **_conteo(res.global_),
        "pendientes": res.pendientes,
        "por_franja": {k: _conteo(res.por_franja[k]) for k, *_ in FRANJAS if k in res.por_franja},
        "por_dia_semana": {d: _conteo(res.por_dia_semana[d]) for d in DIAS if d in res.por_dia_semana},
        "peor_franja": _peor(res.por_franja, tuple(k for k, *_ in FRANJAS)),
        "peor_dia": _peor(res.por_dia_semana, DIAS),
    }


def _por_producto(tomas: list, meds: dict[int, Medicacion], ahora, tz, ventana_min) -> list[dict]:
    """Adherencia por producto (agrupa todas las versiones de una misma medicación)."""
    grupos: dict[str, list] = {}
    for t in tomas:
        grupos.setdefault(meds[t.medicacion_id].producto_ref, []).append(t)
    salida = []
    for ref, ts in grupos.items():
        res = calcular_adherencia(ts, ahora, ventana_min, tz)
        nombre = meds[ts[0].medicacion_id].producto_nombre
        salida.append({"producto_ref": ref, "producto": nombre, **_conteo(res.global_)})
    return sorted(salida, key=lambda d: (d["producto"], d["producto_ref"]))


def _tomas_y_meds(session: Session, paciente_id: int, desde: datetime, hasta: datetime):
    """Tomas con fecha prevista en [desde, hasta) y las medicaciones del paciente."""
    meds = {
        m.id: m
        for m in session.exec(select(Medicacion).where(Medicacion.paciente_id == paciente_id)).all()
    }
    if not meds:
        return [], meds
    tomas = session.exec(
        select(TomaProgramada)
        .where(
            TomaProgramada.medicacion_id.in_(list(meds)),
            TomaProgramada.fecha_hora_prevista >= desde,
            TomaProgramada.fecha_hora_prevista < hasta,
        )
        .order_by(TomaProgramada.fecha_hora_prevista, TomaProgramada.id)
    ).all()
    return tomas, meds


def _texto_pauta(m: Medicacion) -> str:
    if m.tipo_pauta == TipoPauta.HORARIOS_FIJOS:
        return ", ".join(m.horarios_fijos)
    if m.tipo_pauta == TipoPauta.CADA_N_HORAS:
        return f"cada {m.cada_n_horas} h"
    return f"a demanda (máx. {m.max_por_dia}/día)" if m.max_por_dia else "a demanda"


def _alerta_dict(a: Alerta, zona: ZoneInfo) -> dict:
    return {
        "id": f"alerta:{a.id}", "tipo": a.tipo.value, "severidad": a.severidad.value,
        "entre": list(a.entre), "explicacion": a.explicacion,
        "visto_por_medico": a.visto_por_medico, "creada": _iso(a.creado_en, zona),
    }


def _limitar(lista: list, tope: int | None = None) -> tuple[list, int]:
    tope = MAX_LISTA if tope is None else tope
    return lista[:tope], max(0, len(lista) - tope)


# --------------------------------------------------------------------------- #
# 1) Estado actual del paciente (contexto del chat)
# --------------------------------------------------------------------------- #
def estado_paciente(
    session: Session,
    actor: Usuario,
    paciente_id: int,
    ahora: datetime | None = None,
    dias_adherencia: int = 7,
    max_proximas: int = 5,
    ventana_min: int = VENTANA_DEFAULT_MIN,
) -> dict:
    """Foto compacta del paciente: medicación vigente, próximas tomas, adherencia reciente,
    alertas abiertas y próxima consulta."""
    ahora = ahora or utcnow()
    paciente = _paciente(session, actor, paciente_id)
    zona = ZoneInfo(paciente.zona_horaria)

    vigentes = session.exec(
        select(Medicacion)
        .where(Medicacion.paciente_id == paciente_id, Medicacion.estado == EstadoMedicacion.VIGENTE)
        .order_by(Medicacion.id)
    ).all()
    medicacion = [
        {
            "id": f"med:{m.id}", "producto_ref": m.producto_ref, "producto": m.producto_nombre,
            "principios_activos": list(m.principios_activos),
            "dosis": f"{m.dosis_cantidad:g} {m.dosis_unidad}", "pauta": _texto_pauta(m),
            "con_comida": m.con_comida.value, "origen": m.origen.value,
            "indicaciones": m.indicaciones_medico, "hasta": _iso(m.fin, zona),
        }
        for m in vigentes
    ]
    por_id = {m.id: m for m in vigentes}

    proximas, sin_registrar = [], []
    if por_id:
        pendientes = session.exec(
            select(TomaProgramada)
            .where(
                TomaProgramada.medicacion_id.in_(list(por_id)),
                TomaProgramada.estado == EstadoToma.PENDIENTE,
            )
            .order_by(TomaProgramada.fecha_hora_prevista, TomaProgramada.id)
        ).all()
        limite_atraso = ahora - timedelta(hours=24)
        for t in pendientes:
            item = {
                "id": f"toma:{t.id}", "medicamento": por_id[t.medicacion_id].producto_nombre,
                "cuando": _iso(t.fecha_hora_prevista, zona),
            }
            if clasificar_toma(t, ahora, ventana_min) == OMITIDA:  # pendiente ya vencida
                if t.fecha_hora_prevista >= limite_atraso:
                    sin_registrar.append(item)
            else:
                proximas.append(item)
    sin_registrar = sin_registrar[-max_proximas:]

    tomas, meds = _tomas_y_meds(session, paciente_id, ahora - timedelta(days=dias_adherencia), ahora)
    adh = calcular_adherencia(tomas, ahora, ventana_min, paciente.zona_horaria)

    alertas = session.exec(
        select(Alerta)
        .where(Alerta.paciente_id == paciente_id, Alerta.visto_por_medico == False)  # noqa: E712
        .order_by(Alerta.id)
    ).all()
    proxima = session.exec(
        select(Consulta.proxima_consulta)
        .where(Consulta.paciente_id == paciente_id, Consulta.proxima_consulta > ahora)
        .order_by(Consulta.proxima_consulta)
    ).first()
    n_eventos = len(
        session.exec(
            select(EventoPaciente.id).where(
                EventoPaciente.paciente_id == paciente_id,
                EventoPaciente.fecha_evento >= ahora - timedelta(days=dias_adherencia),
                EventoPaciente.fecha_evento <= ahora,
            )
        ).all()
    )

    return {
        "paciente": {"id": paciente.id, "nombre": paciente.nombre},
        "ahora": _iso(ahora, zona),
        "medicacion_vigente": medicacion,
        "proximas_tomas": proximas[:max_proximas],
        "tomas_sin_registrar_24h": sin_registrar,
        f"adherencia_{dias_adherencia}d": {
            **_conteo(adh.global_),
            "por_producto": _por_producto(tomas, meds, ahora, paciente.zona_horaria, ventana_min),
        },
        "alertas_abiertas": [_alerta_dict(a, zona) for a in alertas],
        "proxima_consulta": _iso(proxima, zona),
        "eventos_recientes": n_eventos,
    }


# --------------------------------------------------------------------------- #
# 2) Cambios de medicación en un intervalo
# --------------------------------------------------------------------------- #
def _describir(m: Medicacion, zona: ZoneInfo) -> dict:
    return {
        "id": f"med:{m.id}", "producto_ref": m.producto_ref, "producto": m.producto_nombre,
        "dosis": f"{m.dosis_cantidad:g} {m.dosis_unidad}", "pauta": _texto_pauta(m),
        "con_comida": m.con_comida.value, "origen": m.origen.value,
        "indicaciones": m.indicaciones_medico, "hasta": _iso(m.fin, zona),
    }


def _valor(m: Medicacion, campo: str, zona: ZoneInfo):
    v = getattr(m, campo)
    if hasattr(v, "value"):
        return v.value
    if isinstance(v, datetime):
        return _iso(v, zona)
    return v


def cambios_medicacion(
    session: Session, actor: Usuario, paciente_id: int, desde: datetime, hasta: datetime
) -> dict:
    """Qué se agregó, modificó, suspendió o terminó en el intervalo (desde, hasta].

    - agregadas: sin versión anterior, con inicio en el intervalo.
    - modificadas: versión nueva con inicio en el intervalo; lista campo por campo antes/después
      (`cambio_de_marca` si cambió `producto_ref`, que por D-16 implica el mismo principio activo).
    - suspendidas / finalizadas: cuyo cierre cae en el intervalo.
    """
    paciente = _paciente(session, actor, paciente_id)
    zona = ZoneInfo(paciente.zona_horaria)
    meds = {
        m.id: m
        for m in session.exec(
            select(Medicacion).where(Medicacion.paciente_id == paciente_id).order_by(Medicacion.id)
        ).all()
    }

    agregadas, modificadas, suspendidas, finalizadas = [], [], [], []
    for m in meds.values():
        if desde < m.inicio <= hasta:
            if m.reemplaza_a_id is None:
                agregadas.append(_describir(m, zona))
            else:
                previa = meds[m.reemplaza_a_id]
                campos = [
                    {"campo": c, "antes": _valor(previa, c, zona), "despues": _valor(m, c, zona)}
                    for c in CAMPOS_COMPARABLES
                    if _valor(previa, c, zona) != _valor(m, c, zona)
                ]
                modificadas.append({
                    **_describir(m, zona),
                    "reemplaza_a": f"med:{previa.id}",
                    "cambio_de_marca": previa.producto_ref != m.producto_ref,
                    "cambios": campos,
                })
        if (
            m.estado == EstadoMedicacion.SUSPENDIDA
            and m.vigente_hasta is not None
            and desde < m.vigente_hasta <= hasta
        ):
            suspendidas.append(_describir(m, zona))
        if (
            m.estado in (EstadoMedicacion.FINALIZADA, EstadoMedicacion.VIGENTE)
            and m.fin is not None
            and desde < m.fin <= hasta
        ):
            finalizadas.append(_describir(m, zona))

    ids = [x["id"] for lista in (agregadas, modificadas, suspendidas, finalizadas) for x in lista]
    return {
        "periodo": {"desde": _iso(desde, zona), "hasta": _iso(hasta, zona)},
        "agregadas": agregadas,
        "modificadas": modificadas,
        "suspendidas": suspendidas,
        "finalizadas": finalizadas,
        "hay_cambios": bool(ids),
        "hechos_fuente": sorted(set(ids) | {x["reemplaza_a"] for x in modificadas}),
    }


def diff_medicacion(session: Session, actor: Usuario, consulta_a_id: int, consulta_b_id: int) -> dict:
    """Cambios de medicación entre dos consultas del mismo paciente (insumo del resumen
    posterior a la consulta para el paciente).

    La medicación indicada en una consulta suele empezar ese mismo día, por eso el borde
    superior se extiende un día después de la fecha de la segunda consulta."""
    a, b = session.get(Consulta, consulta_a_id), session.get(Consulta, consulta_b_id)
    if a is None or b is None:
        raise NoEncontrado("No existe alguna de las consultas.")
    if a.paciente_id != b.paciente_id:
        raise ValueError("Las consultas son de pacientes distintos.")
    desde, hasta = sorted((a.fecha, b.fecha))
    res = cambios_medicacion(session, actor, a.paciente_id, desde, hasta + timedelta(days=1))
    return {**res, "consultas": [f"consulta:{a.id}", f"consulta:{b.id}"]}


# --------------------------------------------------------------------------- #
# 3) Digest de un período (insumo del resumen previo para el médico)
# --------------------------------------------------------------------------- #
def digest_periodo(
    session: Session,
    actor: Usuario,
    paciente_id: int,
    desde: datetime,
    hasta: datetime,
    ahora: datetime | None = None,
    ventana_min: int = VENTANA_DEFAULT_MIN,
) -> dict:
    """Estadísticas del período [desde, hasta): adherencia global, por franja, día y producto,
    tomas omitidas / fuera de ventana, eventos, alertas y cambios de medicación."""
    ahora = ahora or utcnow()
    paciente = _paciente(session, actor, paciente_id)
    zona = ZoneInfo(paciente.zona_horaria)
    tomas, meds = _tomas_y_meds(session, paciente_id, desde, hasta)

    omitidas, fuera = [], []
    for t in tomas:
        clase = clasificar_toma(t, ahora, ventana_min)
        base = {
            "id": f"toma:{t.id}", "medicamento": meds[t.medicacion_id].producto_nombre,
            "prevista": _iso(t.fecha_hora_prevista, zona),
        }
        if clase == OMITIDA:
            motivo = "marcada_omitida" if t.estado == EstadoToma.OMITIDA else "sin_registrar"
            omitidas.append({**base, "motivo": motivo})
        elif clase == FUERA_DE_VENTANA:
            fuera.append({**base, "real": _iso(t.fecha_hora_real, zona)})

    eventos = session.exec(
        select(EventoPaciente)
        .where(
            EventoPaciente.paciente_id == paciente_id,
            EventoPaciente.fecha_evento >= desde,
            EventoPaciente.fecha_evento < hasta,
        )
        .order_by(EventoPaciente.fecha_evento, EventoPaciente.id)
    ).all()
    alertas = session.exec(
        select(Alerta)
        .where(Alerta.paciente_id == paciente_id, Alerta.creado_en >= desde, Alerta.creado_en < hasta)
        .order_by(Alerta.id)
    ).all()
    cambios = cambios_medicacion(session, actor, paciente_id, desde, hasta)

    omitidas_l, omitidas_extra = _limitar(omitidas)
    fuera_l, fuera_extra = _limitar(fuera)
    eventos_l, eventos_extra = _limitar([
        {
            "id": f"evento:{e.id}", "fecha": _iso(e.fecha_evento, zona), "tipo": e.tipo.value,
            "texto": e.texto_original, "producto_ref": e.producto_ref,
            "estado_revision": e.estado_revision.value,
        }
        for e in eventos
    ])

    hechos = (
        [x["id"] for x in omitidas_l + fuera_l]
        + [x["id"] for x in eventos_l]
        + [f"alerta:{a.id}" for a in alertas]
        + cambios["hechos_fuente"]
    )
    return {
        "paciente": {"id": paciente.id, "nombre": paciente.nombre},
        "periodo": {"desde": _iso(desde, zona), "hasta": _iso(hasta, zona)},
        "adherencia": {
            **_adherencia_dict(tomas, ahora, paciente.zona_horaria, ventana_min),
            "por_producto": _por_producto(tomas, meds, ahora, paciente.zona_horaria, ventana_min),
        },
        "omitidas": omitidas_l, "omitidas_no_listadas": omitidas_extra,
        "fuera_de_ventana": fuera_l, "fuera_de_ventana_no_listadas": fuera_extra,
        "eventos": eventos_l, "eventos_no_listados": eventos_extra,
        "alertas": [_alerta_dict(a, zona) for a in alertas],
        "cambios_medicacion": cambios,
        "hechos_fuente": hechos,
    }
