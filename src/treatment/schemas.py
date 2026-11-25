"""Contratos de entrada (validados con Pydantic).

`MedicacionInput` es el schema de entrada del formulario del médico (prescribir) y de la
carga de medicación propia del paciente; el origen lo determina la función del servicio.
El nombre y los principios activos NO se piden: los resuelve el servicio
a partir de `producto_ref` contra el vademécum.
"""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from src.treatment.models import ConComida, TipoPauta
from src.treatment.schedule import parse_hhmm


class MedicacionInput(BaseModel):
    paciente_id: int
    producto_ref: str = Field(min_length=1)
    dosis_cantidad: float = Field(gt=0)
    dosis_unidad: str = Field(min_length=1)  # "comprimido", "ml", "gotas"...

    tipo_pauta: TipoPauta
    horarios_fijos: list[str] = Field(default_factory=list)
    cada_n_horas: int | None = Field(default=None, ge=1, le=72)
    max_por_dia: int | None = Field(default=None, ge=1, le=24)

    con_comida: ConComida = ConComida.INDISTINTO
    indicaciones_medico: str | None = None

    inicio: datetime
    duracion_dias: int | None = Field(default=None, ge=1)  # None = crónico
    unidades_por_caja: int | None = Field(default=None, ge=1)

    @field_validator("horarios_fijos")
    @classmethod
    def _normalizar_horarios(cls, v: list[str]) -> list[str]:
        return sorted({f"{parse_hhmm(h):%H:%M}" for h in v})

    @field_validator("inicio")
    @classmethod
    def _inicio_con_zona(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("`inicio` debe incluir zona horaria.")
        return v

    @model_validator(mode="after")
    def _pauta_consistente(self):
        if self.tipo_pauta == TipoPauta.HORARIOS_FIJOS and not self.horarios_fijos:
            raise ValueError("HORARIOS_FIJOS requiere al menos un horario.")
        if self.tipo_pauta == TipoPauta.CADA_N_HORAS and self.cada_n_horas is None:
            raise ValueError("CADA_N_HORAS requiere `cada_n_horas`.")
        if self.tipo_pauta == TipoPauta.A_DEMANDA and self.max_por_dia is None:
            raise ValueError("A_DEMANDA requiere `max_por_dia`.")
        return self
