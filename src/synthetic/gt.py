"""Base de VERDAD del generador sintético (`gt_*`).

Vive en una base y un metadata SEPARADOS de los del tratamiento: el sistema evaluado
(agente, extractor, resúmenes) nunca debe leerla. Solo la usa la evaluación.
"""
from pathlib import Path
from typing import Optional

from sqlalchemy import JSON, Column, Engine, create_engine
from sqlalchemy.orm import registry
from sqlmodel import Field, SQLModel


class GtBase(SQLModel, registry=registry()):
    """Base declarativa propia: su metadata no se mezcla con el de src.treatment.models."""


class GtPaciente(GtBase, table=True):
    __tablename__ = "gt_paciente"

    paciente_id: int = Field(primary_key=True)  # id en la base de tratamiento
    indice: int                                  # posición en la cohorte
    seed: int
    split: str                                   # "dev" | "test" (partición fija, ver generador.particion)
    arquetipo: str                               # cumplidor | regular | olvidadizo
    patologias: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    parametros: dict = Field(default_factory=dict, sa_column=Column(JSON))
    periodo_desde: str
    periodo_hasta: str


class GtToma(GtBase, table=True):
    """Qué pasó REALMENTE con cada toma y qué quedó registrado en el sistema."""

    __tablename__ = "gt_toma"

    toma_id: int = Field(primary_key=True)
    paciente_id: int = Field(index=True)
    resultado: str                  # tomada_en_hora | tomada_tarde | omitida
    registro: str                   # tildada | marcada_omitida | sin_registrar
    desvio_min: Optional[int] = None  # real - prevista (solo si se tomó)
    motivo: Optional[str] = None    # olvido | abandono | ... (solo omitidas)


class GtEvento(GtBase, table=True):
    """Hecho estructurado detrás de cada texto escrito por el paciente."""

    __tablename__ = "gt_evento"

    evento_id: int = Field(primary_key=True)
    paciente_id: int = Field(index=True)
    tipo: str                       # toma_fuera_de_esquema | sintoma
    producto_ref: Optional[str] = None
    sustancia: Optional[str] = None
    nombre_mencionado: Optional[str] = None  # cómo lo escribió (puede tener typos)
    sintoma: Optional[str] = None
    con_typo: bool = False
    redactor: str = "plantillas"


class GtProblema(GtBase, table=True):
    """Problemas sembrados a propósito: la verdad para evaluar el detector de alertas."""

    __tablename__ = "gt_problema"

    id: Optional[int] = Field(default=None, primary_key=True)
    paciente_id: int = Field(index=True)
    tipo: str                       # interaccion | duplicidad
    entre: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # sustancias
    medicacion_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    origen: str = "esquema"         # esquema | automedicacion


def get_gt_engine(path: str | Path) -> Engine:
    ruta = Path(path)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{ruta}")
    GtBase.metadata.create_all(engine)
    return engine
