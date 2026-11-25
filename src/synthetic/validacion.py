"""Evaluación del generador (la consigna exige evaluarlo): validez, diversidad y brecha
entre la verdad y lo que queda registrado. El realismo y la plausibilidad clínica los
revisan personas (tareas L4 y M2 de docs/PLAN.md).
"""
from collections import Counter
from datetime import datetime
from statistics import mean

from sqlmodel import Session, select

from src.synthetic.catalogo import Catalogo
from src.synthetic.gt import GtEvento, GtPaciente, GtProblema, GtToma
from src.treatment.adherence import calcular_adherencia
from src.treatment.models import EventoPaciente, Medicacion, TomaProgramada

DOSIS_MAX = 4  # unidades por toma (v0: todo es "comprimido")


def adherencia_verdadera(gt: Session, paciente_id: int) -> float | None:
    """Según la verdad: tomas simuladas tomadas en hora / tomas simuladas (definición D-10)."""
    tomas = gt.exec(select(GtToma).where(GtToma.paciente_id == paciente_id)).all()
    if not tomas:
        return None
    return sum(t.resultado == "tomada_en_hora" for t in tomas) / len(tomas)


def adherencia_registrada(session: Session, gt: Session, paciente_id: int, ahora: datetime) -> float | None:
    """La que calcularía el sistema con lo registrado, sobre las MISMAS tomas que la verdad."""
    ids = [t.toma_id for t in gt.exec(select(GtToma).where(GtToma.paciente_id == paciente_id)).all()]
    if not ids:
        return None
    tomas = session.exec(select(TomaProgramada).where(TomaProgramada.id.in_(ids))).all()
    return calcular_adherencia(tomas, ahora).global_.adherencia


def validar_cohorte(session: Session, gt: Session, cat: Catalogo, ahora: datetime) -> dict:
    """Informe de validez y diversidad. `ok` es False si hay alguna violación (en `errores`)."""
    errores: list[str] = []
    pacientes = gt.exec(select(GtPaciente).order_by(GtPaciente.indice)).all()
    meds = session.exec(select(Medicacion)).all()
    por_paciente: dict[int, list[Medicacion]] = {}
    for m in meds:
        por_paciente.setdefault(m.paciente_id, []).append(m)

    # Validez
    for m in meds:
        if m.producto_ref not in cat.productos:
            errores.append(f"med:{m.id} producto inexistente o no simple: {m.producto_ref}")
        if not 0 < m.dosis_cantidad <= DOSIS_MAX:
            errores.append(f"med:{m.id} dosis fuera de rango: {m.dosis_cantidad}")
    for p in pacientes:
        if not por_paciente.get(p.paciente_id):
            errores.append(f"paciente {p.paciente_id} sin medicación")
    for pr in gt.exec(select(GtProblema)).all():
        sust = {s for m in por_paciente.get(pr.paciente_id, []) for s in m.principios_activos}
        if pr.origen == "esquema" and not set(pr.entre) <= sust:
            errores.append(f"problema {pr.id}: {pr.entre} no está en el esquema")
        if pr.origen == "automedicacion" and not set(pr.entre) & sust:
            errores.append(f"problema {pr.id}: ninguna sustancia en el esquema")
    n_eventos = len(session.exec(select(EventoPaciente.id)).all())
    gt_eventos = gt.exec(select(GtEvento)).all()
    if n_eventos != len(gt_eventos):
        errores.append(f"eventos sin verdad: {n_eventos} vs {len(gt_eventos)}")

    # Diversidad y brecha verdad/registro
    problemas = gt.exec(select(GtProblema)).all()
    con = lambda tipo: len({p.paciente_id for p in problemas if p.tipo == tipo})  # noqa: E731
    n = len(pacientes) or 1
    verdad, registrada, por_arq = [], [], {}
    for p in pacientes:
        v = adherencia_verdadera(gt, p.paciente_id)
        r = adherencia_registrada(session, gt, p.paciente_id, ahora)
        if v is not None and r is not None:
            verdad.append(v)
            registrada.append(r)
            por_arq.setdefault(p.arquetipo, []).append(v)
    return {
        "ok": not errores,
        "errores": errores[:50],
        "n_pacientes": len(pacientes),
        "por_split": dict(Counter(p.split for p in pacientes)),
        "n_medicamentos": dict(sorted(Counter(len(por_paciente.get(p.paciente_id, [])) for p in pacientes).items())),
        "patologias": dict(Counter(x for p in pacientes for x in p.patologias).most_common()),
        "arquetipos": dict(Counter(p.arquetipo for p in pacientes)),
        "tasa_con_interaccion": round(con("interaccion") / n, 3),
        "tasa_con_duplicidad": round(con("duplicidad") / n, 3),
        "eventos": {
            "total": len(gt_eventos),
            "automedicacion": sum(e.tipo == "toma_fuera_de_esquema" for e in gt_eventos),
            "con_typo": sum(e.con_typo for e in gt_eventos),
        },
        "adherencia_verdadera_media": round(mean(verdad), 3) if verdad else None,
        "adherencia_registrada_media": round(mean(registrada), 3) if registrada else None,
        "adherencia_verdadera_por_arquetipo": {k: round(mean(v), 3) for k, v in sorted(por_arq.items())},
    }
