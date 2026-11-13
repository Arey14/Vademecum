"""Generador de pacientes sintéticos (v0): perfil + conducta determinísticos + texto con plantillas.

Uso:
    python -m src.synthetic.generador --n 50 --seed 7 --out data/synthetic

Genera dos bases separadas:
- `treatment_sint.db`: lo que ve el sistema (usuarios, medicación, tomas tildadas, textos de eventos).
- `gt_sint.db`: la verdad (conducta real, problemas sembrados, hecho detrás de cada texto).
El mismo `seed` produce exactamente la misma cohorte. Ver docs/PLAN.md §5.3.
"""
import argparse
import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from src.synthetic import conducta
from src.synthetic.catalogo import PATOLOGIAS_VENTA_LIBRE, Catalogo, ProductoSimple
from src.synthetic.gt import GtEvento, GtPaciente, GtProblema, GtToma, get_gt_engine
from src.synthetic.perfil import Perfil, crear_perfil
from src.synthetic.redactor import SINTOMAS, HechoEvento, Redactor, RedactorPlantillas
from src.treatment import service
from src.treatment.db import get_engine, init_db
from src.treatment.models import (
    Consulta,
    EstadoToma,
    EventoPaciente,
    Medicacion,
    Rol,
    TomaProgramada,
    Usuario,
    Vinculo,
)
from src.treatment.schedule import DEFAULT_TZ
from src.treatment.schemas import MedicacionInput
from src.treatment.vademecum import crear_resolver

FECHA_REFERENCIA = datetime(2026, 11, 20, 20, 30, tzinfo=ZoneInfo(DEFAULT_TZ))
SALT_PARTICION = "IAA-2026-particion-v1"
PCT_TEST = 0.30
MARGEN_SIMULACION = timedelta(minutes=180)  # toma más tardía simulable (ver `decidir`)


@dataclass
class Config:
    dias: int = 30
    p_interaccion: float = 0.20
    p_duplicidad: float = 0.15
    p_automedicacion_conflictiva: float = 0.25   # la automedicación elige algo que choca con el esquema
    pesos_automedicacion: tuple = ((0, 0.4), (1, 0.3), (2, 0.2), (3, 0.1))
    pesos_sintomas: tuple = ((0, 0.4), (1, 0.3), (2, 0.2), (3, 0.1))


def seed_paciente(seed: int, indice: int) -> int:
    return int(hashlib.sha256(f"{seed}:{indice}".encode()).hexdigest()[:12], 16)


def particion(indice: int, pct_test: float = PCT_TEST) -> str:
    """Partición dev/test FIJA por índice (hash con sal registrada): no depende de la semilla
    de la cohorte, así un paciente nunca cambia de lado. Durante el desarrollo no se mira test."""
    h = int(hashlib.sha256(f"{SALT_PARTICION}:{indice}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if h < pct_test else "dev"


def _sortear(rng: random.Random, pesos):
    valores, w = zip(*pesos)
    return rng.choices(valores, weights=w)[0]


def _entrada(paciente_id: int, item, inicio: datetime) -> MedicacionInput:
    return MedicacionInput(
        paciente_id=paciente_id, producto_ref=item.producto.ref, dosis_cantidad=1,
        dosis_unidad="comprimido", inicio=inicio, duracion_dias=item.duracion_dias, **item.pauta,
    )


def _elegir_automedicacion(rng, cat: Catalogo, sustancias_esquema: set[str], p_conflicto: float) -> ProductoSimple:
    otc = [p for pat in PATOLOGIAS_VENTA_LIBRE for p in cat.productos_de(pat)]
    pares = set(cat.pares_interaccion)
    if rng.random() < p_conflicto:
        conflictivos = [
            p for p in otc
            if p.sustancia in sustancias_esquema
            or any(tuple(sorted((p.sustancia, s))) in pares for s in sustancias_esquema)
        ]
        if conflictivos:
            return rng.choice(conflictivos)
    return rng.choice(otc)


def generar_paciente(
    session: Session, gt: Session, medico: Usuario, cat: Catalogo, resolver, indice: int, seed: int,
    ahora: datetime = FECHA_REFERENCIA, cfg: Config | None = None, redactor: Redactor | None = None,
) -> Usuario:
    cfg = cfg or Config()
    redactor = redactor or RedactorPlantillas()
    rng = random.Random(seed_paciente(seed, indice))
    tz = ZoneInfo(DEFAULT_TZ)
    inicio = (ahora - timedelta(days=cfg.dias)).astimezone(tz).replace(hour=8, minute=0, second=0, microsecond=0)

    perfil: Perfil = crear_perfil(rng, cat, cfg.p_interaccion, cfg.p_duplicidad)
    paciente = Usuario(rol=Rol.PACIENTE, nombre=f"Paciente Sintético {indice:04d}", es_sintetico=True)
    session.add(paciente)
    session.flush()
    session.add(Vinculo(medico_id=medico.id, paciente_id=paciente.id))
    consulta = Consulta(
        paciente_id=paciente.id, medico_id=medico.id, fecha=inicio, diagnostico=", ".join(perfil.patologias),
        proxima_consulta=ahora + timedelta(days=rng.randint(7, 45)),
    )
    session.add(consulta)
    session.commit()

    # --- medicación ----------------------------------------------------------------------
    horizonte = cfg.dias + 2
    meds: list[Medicacion] = []
    for item in perfil.items:
        datos = _entrada(paciente.id, item, inicio)
        if item.origen == "medico":
            m = service.indicar_medicacion(session, medico, datos, resolver, consulta_id=consulta.id,
                                           ahora=inicio, horizonte_dias=horizonte)
        else:
            m = service.agregar_medicacion_propia(session, paciente, datos, resolver, ahora=inicio,
                                                  horizonte_dias=horizonte)
        meds.append(m)

    # --- conducta sobre las tomas --------------------------------------------------------
    params = conducta.sortear_parametros(rng, [i.producto.ref for i in perfil.items], inicio, ahora)
    ref_de = {m.id: m.producto_ref for m in meds}
    tomas = session.exec(
        select(TomaProgramada)
        .where(TomaProgramada.medicacion_id.in_(list(ref_de)))
        .order_by(TomaProgramada.fecha_hora_prevista, TomaProgramada.id)
    ).all()
    for t in tomas:
        if t.fecha_hora_prevista + MARGEN_SIMULACION > ahora:
            continue  # todavía no se puede saber qué pasó: queda pendiente y sin verdad
        d = conducta.decidir(rng, params, t.fecha_hora_prevista, ref_de[t.medicacion_id], tz)
        if d.registro == "tildada":
            service.registrar_toma(session, paciente, t.id, EstadoToma.TOMADA,
                                   cuando=t.fecha_hora_prevista + timedelta(minutes=d.desvio_min), ahora=ahora)
        elif d.registro == "marcada_omitida":
            service.registrar_toma(session, paciente, t.id, EstadoToma.OMITIDA, ahora=ahora)
        gt.add(GtToma(toma_id=t.id, paciente_id=paciente.id, resultado=d.resultado, registro=d.registro,
                      desvio_min=d.desvio_min, motivo=d.motivo))

    # --- eventos de texto libre ----------------------------------------------------------
    sustancias = {i.producto.sustancia for i in perfil.items}
    pares = set(cat.pares_interaccion)
    periodo = (ahora - inicio).total_seconds()
    hechos: list[tuple[datetime, HechoEvento, str | None, str | None]] = []
    for _ in range(_sortear(rng, cfg.pesos_automedicacion)):
        prod = _elegir_automedicacion(rng, cat, sustancias, cfg.p_automedicacion_conflictiva)
        cuando = inicio + timedelta(seconds=rng.uniform(0.05, 0.98) * periodo)
        hechos.append((cuando, HechoEvento("toma_fuera_de_esquema", prod.nombre, prod.sustancia,
                                           rng.choice(SINTOMAS)), prod.ref, prod.sustancia))
    for _ in range(_sortear(rng, cfg.pesos_sintomas)):
        cuando = inicio + timedelta(seconds=rng.uniform(0.05, 0.98) * periodo)
        hechos.append((cuando, HechoEvento("sintoma", sintoma=rng.choice(SINTOMAS)), None, None))
    for cuando, hecho, ref, sust in sorted(hechos, key=lambda h: h[0]):
        texto = redactor.redactar(hecho, rng)
        ev = EventoPaciente(paciente_id=paciente.id, fecha_evento=cuando, texto_original=texto.texto)
        session.add(ev)
        session.flush()
        gt.add(GtEvento(evento_id=ev.id, paciente_id=paciente.id, tipo=hecho.tipo, producto_ref=ref,
                        sustancia=sust, nombre_mencionado=texto.nombre_mencionado, sintoma=hecho.sintoma,
                        con_typo=texto.con_typo, redactor=redactor.nombre))
        if sust is not None:  # la automedicación puede generar un problema (verdad por construcción)
            if sust in sustancias:
                gt.add(GtProblema(paciente_id=paciente.id, tipo="duplicidad", entre=[sust], origen="automedicacion",
                                  medicacion_ids=[m.id for m, i in zip(meds, perfil.items) if i.producto.sustancia == sust]))
            for s in sorted(sustancias):
                if tuple(sorted((sust, s))) in pares:
                    gt.add(GtProblema(paciente_id=paciente.id, tipo="interaccion", entre=sorted((sust, s)),
                                      origen="automedicacion",
                                      medicacion_ids=[m.id for m, i in zip(meds, perfil.items) if i.producto.sustancia == s]))
    session.commit()

    # --- verdad ---------------------------------------------------------------------------
    # La verdad debe ser completa: además de lo sembrado, TODO par del esquema con interacción
    # documentada (el esquema base se arma al azar y puede contenerlas sin que se hayan buscado).
    registrados = set()
    for p in perfil.problemas:
        gt.add(GtProblema(paciente_id=paciente.id, tipo=p.tipo, entre=p.sustancias,
                          medicacion_ids=[meds[i].id for i in p.indices]))
        registrados.add((p.tipo, tuple(sorted(p.sustancias))))
    for i, a in enumerate(perfil.items):
        for j in range(i + 1, len(perfil.items)):
            par = tuple(sorted((a.producto.sustancia, perfil.items[j].producto.sustancia)))
            if par in pares and ("interaccion", par) not in registrados:
                registrados.add(("interaccion", par))
                gt.add(GtProblema(paciente_id=paciente.id, tipo="interaccion", entre=list(par),
                                  medicacion_ids=[meds[i].id, meds[j].id], origen="esquema"))
    gt.add(GtPaciente(
        paciente_id=paciente.id, indice=indice, seed=seed, split=particion(indice), arquetipo=params.arquetipo,
        patologias=perfil.patologias, parametros={**params.to_dict(), "edad": perfil.edad},
        periodo_desde=inicio.isoformat(), periodo_hasta=ahora.isoformat(),
    ))
    gt.commit()
    service.mantenimiento(session, ahora=ahora)  # finaliza las agudas vencidas y deja la agenda futura
    return paciente


def generar_cohorte(
    ruta_tratamiento: str | Path, ruta_gt: str | Path, n: int, seed: int,
    ahora: datetime = FECHA_REFERENCIA, cfg: Config | None = None, vademecum_db: str | Path | None = None,
    redactor: Redactor | None = None,
) -> list[int]:
    """Genera `n` pacientes en bases NUEVAS (falla si ya existen, para no mezclar cohortes)."""
    for ruta in (ruta_tratamiento, ruta_gt):
        if Path(ruta).exists():
            raise FileExistsError(f"{ruta} ya existe; borrarlo o usar otra ruta.")
    cat, resolver = Catalogo(vademecum_db), crear_resolver(vademecum_db)
    engine = init_db(get_engine(ruta_tratamiento))
    gt_engine = get_gt_engine(ruta_gt)
    ids = []
    with Session(engine) as session, Session(gt_engine) as gt:
        medico = Usuario(rol=Rol.MEDICO, nombre="Médico Sintético", es_sintetico=True)
        session.add(medico)
        session.commit()
        for i in range(n):
            ids.append(generar_paciente(session, gt, medico, cat, resolver, i, seed, ahora, cfg, redactor).id)
    engine.dispose()
    gt_engine.dispose()
    return ids


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera una cohorte de pacientes sintéticos.")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--dias", type=int, default=30)
    a = ap.parse_args()
    out = Path(a.out)
    ids = generar_cohorte(out / "treatment_sint.db", out / "gt_sint.db", a.n, a.seed, cfg=Config(dias=a.dias))
    print(f"{len(ids)} pacientes en {out}/ (semilla {a.seed}, {a.dias} días)")


if __name__ == "__main__":
    main()
