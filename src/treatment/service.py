"""Servicio de medicación y tomas: crear, versionar, suspender, mantener y tildar.

Reglas (ver docs/MODELO_DATOS.md):
- La medicación indicada por el médico NO se edita: `versionar_medicacion` cierra la
  versión anterior (estado `reemplazada`) y crea una nueva con `reemplaza_a_id`.
- Las tomas futuras pendientes de la versión cerrada se borran; el historial (tomas
  pasadas, tildadas u omitidas) se conserva.
- Cada función pública es atómica: o se aplica todo o nada.
- `ahora` se inyecta para poder testear; por defecto es el instante actual.
"""
import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable

from sqlmodel import Session, SQLModel, delete, select

from src.treatment.models import (
    EstadoMedicacion,
    EstadoToma,
    Medicacion,
    Origen,
    TipoPauta,
    TomaProgramada,
    Usuario,
    utcnow,
)
from src.treatment.permissions import (
    verificar_crear_medicacion,
    verificar_modificar_medicacion,
    verificar_registrar_toma,
)
from src.treatment.schedule import DEFAULT_TZ, HORIZONTE_DEFAULT_DIAS, generar_cronograma
from src.treatment.schemas import MedicacionInput


# --------------------------------------------------------------------------- #
# Errores y tipos
# --------------------------------------------------------------------------- #
class ServicioError(Exception):
    """Error de negocio del servicio de tratamiento."""


class NoEncontrado(ServicioError):
    pass


class EstadoInvalido(ServicioError):
    pass


class ProductoNoEncontrado(ServicioError):
    pass


@dataclass(frozen=True)
class ProductoResuelto:
    nombre: str
    principios_activos: list[str]


# El vademécum se inyecta: producto_ref -> ProductoResuelto (o ProductoNoEncontrado).
ResolverProducto = Callable[[str], ProductoResuelto]

# Campos de MedicacionInput que se pueden cambiar al versionar. `producto_ref` se admite
# aparte y solo si el principio activo es idéntico (cambio de marca).
CAMPOS_MODIFICABLES = {
    "dosis_cantidad", "dosis_unidad", "tipo_pauta", "horarios_fijos", "cada_n_horas",
    "max_por_dia", "con_comida", "indicaciones_medico", "inicio", "duracion_dias",
    "unidades_por_caja",
}


def _normalizar_principios(principios) -> frozenset[str]:
    """Compara principios activos sin distinguir mayúsculas ni tildes."""
    def limpio(p: str) -> str:
        sin_tildes = unicodedata.normalize("NFKD", p).encode("ascii", "ignore").decode()
        return sin_tildes.strip().casefold()
    return frozenset(limpio(p) for p in principios if p and p.strip())


def _snapshot_producto(
    viejo: Medicacion, nuevo_ref: str, resolver: ResolverProducto | None
) -> ProductoResuelto:
    """Producto de la nueva versión. Si cambia la marca, exige el MISMO principio activo."""
    if nuevo_ref == viejo.producto_ref:
        return ProductoResuelto(viejo.producto_nombre, viejo.principios_activos)
    if resolver is None:
        raise ServicioError("Para cambiar de marca hace falta el resolver del vademécum.")
    nuevo = resolver(nuevo_ref)
    antes = _normalizar_principios(viejo.principios_activos)
    despues = _normalizar_principios(nuevo.principios_activos)
    if not antes or not despues:
        raise ServicioError(
            "No se puede cambiar de marca: falta el principio activo de alguno de los productos "
            "y no se puede verificar que sea el mismo."
        )
    if antes != despues:
        raise ServicioError(
            f"No se puede cambiar de marca: cambia el principio activo "
            f"({sorted(antes)} -> {sorted(despues)}). Suspender la medicación e indicar otra."
        )
    return nuevo


def _atomico(fn):
    @wraps(fn)
    def envoltura(session: Session, *args, **kwargs):
        try:
            resultado = fn(session, *args, **kwargs)
            session.commit()
        except Exception:
            session.rollback()
            raise
        if isinstance(resultado, SQLModel):
            session.refresh(resultado)
        return resultado

    return envoltura


# --------------------------------------------------------------------------- #
# Helpers internos
# --------------------------------------------------------------------------- #
def _cargar_medicacion(session: Session, medicacion_id: int) -> Medicacion:
    med = session.get(Medicacion, medicacion_id)
    if med is None:
        raise NoEncontrado(f"No existe la medicación {medicacion_id}.")
    return med


def _zona(session: Session, paciente_id: int) -> str:
    paciente = session.get(Usuario, paciente_id)
    return paciente.zona_horaria if paciente else DEFAULT_TZ


def _campos_de_pauta(data: MedicacionInput) -> dict:
    """Solo los campos de pauta que corresponden al tipo (el resto se limpia)."""
    return {
        "horarios_fijos": data.horarios_fijos if data.tipo_pauta == TipoPauta.HORARIOS_FIJOS else [],
        "cada_n_horas": data.cada_n_horas if data.tipo_pauta == TipoPauta.CADA_N_HORAS else None,
        "max_por_dia": data.max_por_dia if data.tipo_pauta == TipoPauta.A_DEMANDA else None,
    }


def _borrar_tomas_futuras_pendientes(session: Session, medicacion_id: int, desde: datetime) -> None:
    session.exec(
        delete(TomaProgramada).where(
            TomaProgramada.medicacion_id == medicacion_id,
            TomaProgramada.estado == EstadoToma.PENDIENTE,
            TomaProgramada.fecha_hora_prevista >= desde,
        )
    )


def _asegurar_cronograma(
    session: Session, med: Medicacion, ahora: datetime, horizonte_dias: int
) -> int:
    """Inserta las tomas que falten desde `ahora` hasta el horizonte. Idempotente."""
    fechas = generar_cronograma(
        tipo_pauta=med.tipo_pauta,
        inicio=med.inicio,
        fin=med.fin,
        horarios_fijos=med.horarios_fijos,
        cada_n_horas=med.cada_n_horas,
        desde=ahora,
        horizonte_dias=horizonte_dias,
        tz=_zona(session, med.paciente_id),
    )
    if med.vigente_hasta is not None:
        fechas = [f for f in fechas if f < med.vigente_hasta]
    existentes = set(
        session.exec(
            select(TomaProgramada.fecha_hora_prevista).where(
                TomaProgramada.medicacion_id == med.id
            )
        ).all()
    )
    nuevas = [f for f in fechas if f not in existentes]
    session.add_all(
        TomaProgramada(medicacion_id=med.id, fecha_hora_prevista=f) for f in nuevas
    )
    return len(nuevas)


def _crear(
    session: Session,
    actor: Usuario,
    data: MedicacionInput,
    origen: Origen,
    resolver: ResolverProducto,
    consulta_id: int | None,
    ahora: datetime,
    horizonte_dias: int,
    reemplaza_a_id: int | None = None,
    producto: ProductoResuelto | None = None,
    fin_forzado: datetime | None = None,
) -> Medicacion:
    producto = producto or resolver(data.producto_ref)
    fin = fin_forzado or (
        data.inicio + timedelta(days=data.duracion_dias) if data.duracion_dias else None
    )
    med = Medicacion(
        paciente_id=data.paciente_id,
        consulta_id=consulta_id,
        creado_por_id=actor.id,
        origen=origen,
        reemplaza_a_id=reemplaza_a_id,
        producto_ref=data.producto_ref,
        producto_nombre=producto.nombre,
        principios_activos=list(producto.principios_activos),
        dosis_cantidad=data.dosis_cantidad,
        dosis_unidad=data.dosis_unidad,
        tipo_pauta=data.tipo_pauta,
        con_comida=data.con_comida,
        indicaciones_medico=data.indicaciones_medico,
        inicio=data.inicio,
        duracion_dias=data.duracion_dias,
        fin=fin,
        unidades_por_caja=data.unidades_por_caja,
        **_campos_de_pauta(data),
    )
    session.add(med)
    session.flush()  # obtiene el id
    _asegurar_cronograma(session, med, ahora, horizonte_dias)
    return med


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
@_atomico
def indicar_medicacion(
    session: Session,
    actor: Usuario,
    data: MedicacionInput,
    resolver: ResolverProducto,
    consulta_id: int | None = None,
    ahora: datetime | None = None,
    horizonte_dias: int = HORIZONTE_DEFAULT_DIAS,
) -> Medicacion:
    """El médico prescribe: crea una Medicacion `origen=medico` y su cronograma."""
    verificar_crear_medicacion(session, actor, data.paciente_id, Origen.MEDICO)
    return _crear(session, actor, data, Origen.MEDICO, resolver, consulta_id,
                  ahora or utcnow(), horizonte_dias)


@_atomico
def agregar_medicacion_propia(
    session: Session,
    actor: Usuario,
    data: MedicacionInput,
    resolver: ResolverProducto,
    ahora: datetime | None = None,
    horizonte_dias: int = HORIZONTE_DEFAULT_DIAS,
) -> Medicacion:
    """El paciente agrega medicación habitual por su cuenta (`origen=paciente`)."""
    verificar_crear_medicacion(session, actor, data.paciente_id, Origen.PACIENTE)
    return _crear(session, actor, data, Origen.PACIENTE, resolver, None,
                  ahora or utcnow(), horizonte_dias)


@_atomico
def versionar_medicacion(
    session: Session,
    actor: Usuario,
    medicacion_id: int,
    cambios: dict,
    consulta_id: int | None = None,
    ahora: datetime | None = None,
    horizonte_dias: int = HORIZONTE_DEFAULT_DIAS,
    resolver: ResolverProducto | None = None,
) -> Medicacion:
    """Cambia dosis, pauta, duración, etc. creando una versión nueva.

    - La nueva versión rige desde `cambios["inicio"]` (por defecto, `ahora`).
    - Si no se indica `duracion_dias` y la anterior tenía fecha de fin, se conserva
      esa fecha de fin (la duración se recalcula como los días que faltan).
    - Se puede cambiar de MARCA (`producto_ref`) solo si el principio activo es idéntico
      (requiere `resolver`). Si cambia el principio activo se rechaza: se suspende la
      medicación y se indica otra. Ver docs/MODELO_DATOS.md.
    """
    ahora = ahora or utcnow()
    viejo = _cargar_medicacion(session, medicacion_id)
    verificar_modificar_medicacion(session, actor, viejo)

    if viejo.estado != EstadoMedicacion.VIGENTE:
        raise EstadoInvalido(
            f"Solo se versiona una medicación vigente (estado actual: {viejo.estado.value})."
        )
    desconocidos = set(cambios) - CAMPOS_MODIFICABLES - {"producto_ref"}
    if desconocidos:
        raise ServicioError(f"Campos no modificables: {sorted(desconocidos)}.")
    snapshot = _snapshot_producto(viejo, cambios.get("producto_ref", viejo.producto_ref), resolver)

    nuevo_inicio = cambios.get("inicio", ahora)
    fin_forzado = None
    if "duracion_dias" in cambios:
        duracion = cambios["duracion_dias"]  # None = pasa a crónico
    elif viejo.fin is not None:
        # Se hereda la fecha de fin exacta; `duracion_dias` queda como dato informativo.
        if viejo.fin <= nuevo_inicio:
            raise EstadoInvalido("La medicación ya cumplió su duración; no hay nada que versionar.")
        fin_forzado = viejo.fin
        duracion = math.ceil((viejo.fin - nuevo_inicio) / timedelta(days=1))
    else:
        duracion = None

    base = dict(
        paciente_id=viejo.paciente_id,
        producto_ref=viejo.producto_ref,
        dosis_cantidad=viejo.dosis_cantidad,
        dosis_unidad=viejo.dosis_unidad,
        tipo_pauta=viejo.tipo_pauta,
        horarios_fijos=viejo.horarios_fijos,
        cada_n_horas=viejo.cada_n_horas,
        max_por_dia=viejo.max_por_dia,
        con_comida=viejo.con_comida,
        indicaciones_medico=viejo.indicaciones_medico,
        unidades_por_caja=viejo.unidades_por_caja,
    )
    if "tipo_pauta" in cambios and cambios["tipo_pauta"] != viejo.tipo_pauta:
        # Al cambiar el tipo de pauta, los campos de la pauta anterior no se arrastran.
        base.update(horarios_fijos=[], cada_n_horas=None, max_por_dia=None)
    nueva_data = MedicacionInput(  # revalida todo (lanza ValidationError si es inconsistente)
        **{**base, **cambios, "inicio": nuevo_inicio, "duracion_dias": duracion}
    )

    # Cierra la versión anterior
    viejo.estado = EstadoMedicacion.REEMPLAZADA
    viejo.vigente_hasta = nuevo_inicio
    _borrar_tomas_futuras_pendientes(session, viejo.id, nuevo_inicio)

    return _crear(
        session, actor, nueva_data, viejo.origen, resolver=None,
        consulta_id=consulta_id if consulta_id is not None else viejo.consulta_id,
        ahora=ahora, horizonte_dias=horizonte_dias,
        reemplaza_a_id=viejo.id, producto=snapshot, fin_forzado=fin_forzado,
    )


@_atomico
def suspender_medicacion(
    session: Session, actor: Usuario, medicacion_id: int, ahora: datetime | None = None
) -> Medicacion:
    """Suspende la medicación: deja de generar tomas y borra las futuras pendientes."""
    ahora = ahora or utcnow()
    med = _cargar_medicacion(session, medicacion_id)
    verificar_modificar_medicacion(session, actor, med)
    if med.estado != EstadoMedicacion.VIGENTE:
        raise EstadoInvalido(
            f"Solo se suspende una medicación vigente (estado actual: {med.estado.value})."
        )
    med.estado = EstadoMedicacion.SUSPENDIDA
    med.vigente_hasta = ahora
    _borrar_tomas_futuras_pendientes(session, med.id, ahora)
    return med


@_atomico
def registrar_toma(
    session: Session,
    actor: Usuario,
    toma_id: int,
    estado: EstadoToma = EstadoToma.TOMADA,
    cuando: datetime | None = None,
    ahora: datetime | None = None,
) -> TomaProgramada:
    """El paciente tilda una toma (tomada) o indica que no la tomó (omitida)."""
    if estado == EstadoToma.PENDIENTE:
        raise ServicioError("Usar TOMADA u OMITIDA.")
    toma = session.get(TomaProgramada, toma_id)
    if toma is None:
        raise NoEncontrado(f"No existe la toma {toma_id}.")
    med = _cargar_medicacion(session, toma.medicacion_id)
    verificar_registrar_toma(actor, med.paciente_id)
    toma.estado = estado
    toma.registrado_por_id = actor.id
    toma.fecha_hora_real = (cuando or ahora or utcnow()) if estado == EstadoToma.TOMADA else None
    return toma


@_atomico
def mantenimiento(
    session: Session,
    ahora: datetime | None = None,
    horizonte_dias: int = HORIZONTE_DEFAULT_DIAS,
) -> dict:
    """Tarea periódica: finaliza las medicaciones que cumplieron su duración y extiende el
    cronograma de las vigentes (tratamientos crónicos) hasta el horizonte."""
    ahora = ahora or utcnow()
    finalizadas = extendidas = 0
    for med in session.exec(
        select(Medicacion).where(Medicacion.estado == EstadoMedicacion.VIGENTE)
    ).all():
        if med.fin is not None and med.fin <= ahora:
            med.estado = EstadoMedicacion.FINALIZADA
            med.vigente_hasta = med.fin
            finalizadas += 1
            continue
        extendidas += _asegurar_cronograma(session, med, ahora, horizonte_dias)
    return {"finalizadas": finalizadas, "tomas_agregadas": extendidas}
