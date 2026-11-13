"""Reglas de permisos por rol. Se aplican en el código (las tools), NO en el prompt.

Reglas (ver docs/MODELO_DATOS.md §5):
- El tratamiento indicado por el médico (origen=medico) solo lo modifica un médico
  vinculado al paciente, y siempre versionando (nunca editando en el lugar).
- El paciente NO puede modificar ni borrar lo del médico. Sí puede agregar medicación propia
  (origen=paciente), modificar solo esa, y tildar las tomas de su propio cronograma.
- El médico no modifica lo que el paciente agregó por su cuenta (solo lo ve y lo evalúa).
"""
from sqlmodel import Session, select

from src.treatment.models import Origen, Medicacion, Rol, Usuario, Vinculo


class PermisoDenegado(Exception):
    """El actor no tiene permiso para la operación pedida."""


def medico_vinculado(session: Session, medico_id: int, paciente_id: int) -> bool:
    v = session.exec(
        select(Vinculo).where(
            Vinculo.medico_id == medico_id,
            Vinculo.paciente_id == paciente_id,
            Vinculo.activo == True,  # noqa: E712 (SQL)
        )
    ).first()
    return v is not None


def verificar_crear_medicacion(
    session: Session, actor: Usuario, paciente_id: int, origen: Origen
) -> None:
    if origen == Origen.MEDICO:
        if actor.rol != Rol.MEDICO:
            raise PermisoDenegado("Solo un médico puede indicar medicación del esquema médico.")
        if not medico_vinculado(session, actor.id, paciente_id):
            raise PermisoDenegado("El médico no está vinculado a este paciente.")
    else:  # origen paciente
        if actor.rol != Rol.PACIENTE or actor.id != paciente_id:
            raise PermisoDenegado("Solo el propio paciente puede agregar medicación propia.")


def verificar_modificar_medicacion(
    session: Session, actor: Usuario, medicacion: Medicacion
) -> None:
    if medicacion.origen == Origen.MEDICO:
        if actor.rol != Rol.MEDICO or not medico_vinculado(
            session, actor.id, medicacion.paciente_id
        ):
            raise PermisoDenegado(
                "El tratamiento indicado por el médico solo lo modifica un médico vinculado."
            )
    else:
        if actor.rol != Rol.PACIENTE or actor.id != medicacion.paciente_id:
            raise PermisoDenegado("Lo agregado por el paciente solo lo modifica el propio paciente.")


def verificar_registrar_toma(actor: Usuario, paciente_id: int) -> None:
    """Tildar una toma: solo el propio paciente (cualquier origen de la medicación)."""
    if actor.rol != Rol.PACIENTE or actor.id != paciente_id:
        raise PermisoDenegado("Solo el paciente puede registrar sus tomas.")


def verificar_ver_paciente(session: Session, actor: Usuario, paciente_id: int) -> None:
    """Lectura de los datos de un paciente: el propio paciente o un médico vinculado."""
    if actor.rol == Rol.PACIENTE and actor.id == paciente_id:
        return
    if actor.rol == Rol.MEDICO and medico_vinculado(session, actor.id, paciente_id):
        return
    raise PermisoDenegado("No tenés permiso para ver los datos de este paciente.")
