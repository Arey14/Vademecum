"""Modelo de datos del tratamiento (SQLModel sobre SQLite).

Base de datos *separada* del grafo del vademécum: acá vive el estado mutable.
Los datetimes se guardan siempre en UTC y se devuelven con tzinfo=UTC.
Ver docs/MODELO_DATOS.md.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import JSON, Column, DateTime, TypeDecorator, UniqueConstraint
from sqlmodel import Field, SQLModel


# --------------------------------------------------------------------------- #
# Tipos auxiliares
# --------------------------------------------------------------------------- #
class UTCDateTime(TypeDecorator):
    """DateTime que exige tz-aware al escribir y devuelve siempre UTC aware."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Se recibió un datetime sin zona horaria; usar tz-aware.")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=timezone.utc)


def _dt(nullable: bool = False, **kwargs):
    """Field de datetime UTC (cada llamada crea su propia Column)."""
    return Field(sa_column=Column(UTCDateTime, nullable=nullable), **kwargs)


def _json(default_factory=list, **kwargs):
    return Field(default_factory=default_factory, sa_column=Column(JSON), **kwargs)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enumeraciones
# --------------------------------------------------------------------------- #
class Rol(str, Enum):
    MEDICO = "medico"
    PACIENTE = "paciente"


class Origen(str, Enum):
    MEDICO = "medico"
    PACIENTE = "paciente"


class TipoPauta(str, Enum):
    HORARIOS_FIJOS = "horarios_fijos"  # ej. 08:00 y 20:00
    CADA_N_HORAS = "cada_n_horas"      # ej. cada 8 h desde el inicio
    A_DEMANDA = "a_demanda"            # "si hay dolor", con máximo diario


class ConComida(str, Enum):
    CON = "con"
    SIN = "sin"
    INDISTINTO = "indistinto"


class EstadoMedicacion(str, Enum):
    VIGENTE = "vigente"
    REEMPLAZADA = "reemplazada"  # existe una versión nueva (reemplaza_a_id)
    FINALIZADA = "finalizada"    # terminó su duración
    SUSPENDIDA = "suspendida"


class EstadoToma(str, Enum):
    """'Vencida' NO se guarda: se deriva (pendiente y fuera de ventana)."""

    PENDIENTE = "pendiente"
    TOMADA = "tomada"
    OMITIDA = "omitida"  # el paciente indicó explícitamente que no la tomó


class TipoEvento(str, Enum):
    TOMA_FUERA_DE_ESQUEMA = "toma_fuera_de_esquema"
    SINTOMA = "sintoma"
    DUDA = "duda"
    OTRO = "otro"


class EstadoRevision(str, Enum):
    AUTOMATICO = "automatico"
    REQUIERE_CONFIRMACION = "requiere_confirmacion"
    CONFIRMADO = "confirmado"


class TipoAlerta(str, Enum):
    DUPLICIDAD = "duplicidad"
    INTERACCION = "interaccion"
    CONTRAINDICACION = "contraindicacion"
    ALCOHOL_ALIMENTO = "alcohol_alimento"


class Severidad(str, Enum):
    ROJO = "rojo"          # riesgo grave
    AMARILLO = "amarillo"  # precaución, consultar
    VERDE = "verde"        # sin interacción relevante conocida
    GRIS = "gris"          # sin información


class TipoResumen(str, Enum):
    PREVIO_MEDICO = "previo_medico"
    POST_PACIENTE = "post_paciente"


# --------------------------------------------------------------------------- #
# Tablas
# --------------------------------------------------------------------------- #
class Usuario(SQLModel, table=True):
    __tablename__ = "usuario"

    id: Optional[int] = Field(default=None, primary_key=True)
    rol: Rol
    nombre: str
    zona_horaria: str = "America/Argentina/Buenos_Aires"
    es_sintetico: bool = False


class Vinculo(SQLModel, table=True):
    """Relación médico ↔ paciente (n:m: un paciente puede tener varios médicos)."""

    __tablename__ = "vinculo"

    medico_id: int = Field(foreign_key="usuario.id", primary_key=True)
    paciente_id: int = Field(foreign_key="usuario.id", primary_key=True)
    activo: bool = True


class Consulta(SQLModel, table=True):
    __tablename__ = "consulta"

    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="usuario.id", index=True)
    medico_id: int = Field(foreign_key="usuario.id")
    fecha: datetime = _dt()
    diagnostico: Optional[str] = None
    notas: Optional[str] = None
    proxima_consulta: Optional[datetime] = _dt(nullable=True, default=None)


class Medicacion(SQLModel, table=True):
    """Un medicamento por fila. Las del médico NO se editan: se versionan
    (se crea una nueva con `reemplaza_a_id` y se cierra la anterior)."""

    __tablename__ = "medicacion"

    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="usuario.id", index=True)
    consulta_id: Optional[int] = Field(default=None, foreign_key="consulta.id")
    creado_por_id: int = Field(foreign_key="usuario.id")
    origen: Origen
    reemplaza_a_id: Optional[int] = Field(default=None, foreign_key="medicacion.id")

    # Referencia estable al vademécum + copia al momento de recetar
    producto_ref: str
    producto_nombre: str
    principios_activos: list[str] = _json()

    dosis_cantidad: float
    dosis_unidad: str

    tipo_pauta: TipoPauta
    horarios_fijos: list[str] = _json()  # ["08:00", "20:00"]
    cada_n_horas: Optional[int] = None
    max_por_dia: Optional[int] = None    # solo a demanda

    con_comida: ConComida = ConComida.INDISTINTO
    indicaciones_medico: Optional[str] = None

    inicio: datetime = _dt()
    duracion_dias: Optional[int] = None  # None = tratamiento crónico (dato informativo)
    # Instante exacto de fin; es el dato que manda. Al versionar se hereda tal cual,
    # para no agregar ni quitar dosis respecto del plan original.
    fin: Optional[datetime] = _dt(nullable=True, default=None)
    vigente_hasta: Optional[datetime] = _dt(nullable=True, default=None)
    estado: EstadoMedicacion = EstadoMedicacion.VIGENTE
    unidades_por_caja: Optional[int] = None


class TomaProgramada(SQLModel, table=True):
    __tablename__ = "toma_programada"
    __table_args__ = (
        UniqueConstraint("medicacion_id", "fecha_hora_prevista", name="uq_toma_presc_hora"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    medicacion_id: int = Field(foreign_key="medicacion.id", index=True)
    fecha_hora_prevista: datetime = _dt()
    estado: EstadoToma = EstadoToma.PENDIENTE
    fecha_hora_real: Optional[datetime] = _dt(nullable=True, default=None)
    registrado_por_id: Optional[int] = Field(default=None, foreign_key="usuario.id")


class EventoPaciente(SQLModel, table=True):
    __tablename__ = "evento_paciente"

    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="usuario.id", index=True)
    fecha_evento: datetime = _dt()
    texto_original: str  # siempre se conserva
    tipo: TipoEvento = TipoEvento.OTRO
    extraccion: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    producto_ref: Optional[str] = None
    confianza: Optional[float] = None
    estado_revision: EstadoRevision = EstadoRevision.AUTOMATICO
    creado_en: datetime = _dt(default_factory=utcnow)


class Alerta(SQLModel, table=True):
    __tablename__ = "alerta"

    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(foreign_key="usuario.id", index=True)
    medicacion_id: Optional[int] = Field(default=None, foreign_key="medicacion.id")
    evento_id: Optional[int] = Field(default=None, foreign_key="evento_paciente.id")
    tipo: TipoAlerta
    severidad: Severidad
    entre: list[str] = _json()  # sustancias o productos involucrados
    explicacion: str
    evidencia: Optional[str] = None  # oración de la monografía
    fuente_url: Optional[str] = None
    visto_por_medico: bool = False
    fecha_visto: Optional[datetime] = _dt(nullable=True, default=None)
    creado_en: datetime = _dt(default_factory=utcnow)


class LlmRun(SQLModel, table=True):
    """Traza de cada llamada al LLM (tokens, costo, latencia)."""

    __tablename__ = "llm_run"

    id: Optional[int] = Field(default=None, primary_key=True)
    creado_en: datetime = _dt(default_factory=utcnow)
    tarea: str
    modelo: str
    tokens_in: int = 0
    tokens_out: int = 0
    costo_usd: float = 0.0
    latencia_ms: int = 0
    ok: bool = True
    error: Optional[str] = None


class Resumen(SQLModel, table=True):
    __tablename__ = "resumen"

    id: Optional[int] = Field(default=None, primary_key=True)
    consulta_id: int = Field(foreign_key="consulta.id", index=True)
    tipo: TipoResumen
    periodo_desde: datetime = _dt()
    periodo_hasta: datetime = _dt()
    contenido: str
    # ids de los hechos en los que se basó: ["toma:12", "evento:3", "alerta:7"]
    hechos_fuente: list[str] = _json()
    llm_run_id: Optional[int] = Field(default=None, foreign_key="llm_run.id")
    creado_en: datetime = _dt(default_factory=utcnow)
