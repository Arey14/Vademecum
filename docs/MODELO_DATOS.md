# Modelo de datos del tratamiento

> Estado: **v1 implementada** (07–08/11/2026) en [`src/treatment/`](../src/treatment/). La fuente de verdad de los campos es [`models.py`](../src/treatment/models.py); este documento explica el *por qué* y las reglas. Decisiones: D-09 a D-13 en [PLAN.md](PLAN.md).

## 1. Principios de diseño

1. **Base separada del grafo.** El vademécum (`Final/vademecum_graph.db`) se regenera y no se modifica. El tratamiento es estado mutable y vive en `data/treatment.db` (no se versiona en git).
2. **Clave estable de producto.** Los productos se referencian por `producto_ref`, no por nombre (hay 22 nombres duplicados, H-09). Además cada medicación guarda una **copia** del nombre y de los principios activos al momento de recetar, así el historial no se rompe si se reconstruye el grafo. `producto_ref` tiene el formato `pv-<id>` y se deriva de la URL del producto ([`producto_ref.py`](../src/graph/producto_ref.py), decisión D-17); el servicio lo resuelve contra el vademécum con [`vademecum.py`](../src/treatment/vademecum.py) (solo lectura).
3. **Medicación ≠ cronograma.** La medicación es la *intención* (lo que indicó el médico o agregó el paciente); las tomas son filas concretas con fecha y hora, generadas por una función determinística ([`schedule.py`](../src/treatment/schedule.py)).
4. **El tratamiento solo lo modifica el médico, y versionando.** Cambiar una dosis o una pauta no edita la fila: se crea una nueva medicación (`reemplaza_a_id`) y la anterior pasa a `reemplazada`. El paciente nunca modifica ni borra lo indicado por el médico.
5. **El LLM nunca ve las tablas crudas.** Recibe *snapshots* compactos armados por código (ver §6).
6. **Mismo esquema para pacientes sintéticos y reales.** `Usuario.es_sintetico` los distingue. La *verdad del generador* (qué tomas se olvidó, qué interacciones se plantaron) irá en una base aparte (`gt_*`) que el sistema no puede leer.

## 2. Entidades

```
Usuario (rol: medico | paciente) ──< Vinculo >── Usuario        (n:m)

Consulta (paciente, medico, fecha, diagnostico, notas, proxima_consulta)
   └──< Medicacion   (1 medicamento por fila; versionada; origen: medico | paciente)
            └──< TomaProgramada   (1 horario concreto; el paciente la tilda)

EventoPaciente   texto libre + extracción estructurada
Alerta           resultado del semáforo, con la oración de evidencia
Resumen          previo a la consulta (médico) / posterior (paciente), con hechos_fuente
LlmRun           traza por llamada al LLM: tokens, USD, latencia
```

**Pautas soportadas** (`Medicacion.tipo_pauta`):

| Tipo | Campos | Genera tomas |
|---|---|---|
| `horarios_fijos` | `horarios_fijos: ["08:00","20:00"]` | Sí, cada día a esas horas (hora local) |
| `cada_n_horas` | `cada_n_horas: 8` | Sí: inicio, inicio + 8 h, ... (tiempo real transcurrido) |
| `a_demanda` | `max_por_dia: 3` | No (sin horario fijo); los registros llegan como eventos y se controla el máximo diario |

`duracion_dias = None` significa tratamiento crónico: el cronograma se genera solo hasta un horizonte (14 días por defecto) y se extiende a medida que pasa el tiempo.

## 3. Medicación que agrega el paciente

| Caso | Dónde se guarda |
|---|---|
| Lo tomó **una vez** ("me tomé un ibuprofeno") | `EventoPaciente` (tipo `toma_fuera_de_esquema`) |
| Lo toma **de forma habitual** ("tomo omeprazol todos los días") | `Medicacion` con `origen = paciente` |

El médico ve ambos marcados como "agregado por el paciente". El semáforo evalúa la **unión** del esquema médico y lo agregado por el paciente.

## 4. Adherencia (definición fijada)

- Toma **cumplida**: tildada dentro de ±60 min de la hora prevista (parámetro `ventana_min`).
- Toma **vencida**: sigue pendiente pasada la ventana. El estado `vencida` *no se guarda*: se deriva al calcular (evita estados desactualizados).
- **Denominador** = cumplidas + fuera de ventana + omitidas (incluye las vencidas). Las pendientes que no vencieron no cuentan; las tomas a demanda tampoco.
- **Adherencia** = cumplidas / denominador, global y desglosada por franja horaria (madrugada, mañana, tarde, noche) y por día de la semana. Implementación: [`adherence.py`](../src/treatment/adherence.py).

Esta misma definición se usa para la *verdad* del generador de pacientes sintéticos, así que la evaluación del resumen para el médico es exacta.

## 5. Permisos (se aplican en el código, no en el prompt)

Implementación: [`permissions.py`](../src/treatment/permissions.py).

| Acción | Médico vinculado | Paciente | Otros |
|---|---|---|---|
| **Indicar** medicación (`origen=medico`) | ✅ | ❌ | ❌ |
| **Modificar** (versionar) lo indicado por el médico | ✅ | ❌ | ❌ |
| Agregar / modificar **medicación propia** del paciente (`origen=paciente`, ej. "tomo omeprazol todos los días") | ❌ | ✅ solo el propio paciente | ❌ |
| Tildar una toma | ❌ | ✅ solo el propio paciente (de cualquier origen) | ❌ |
| Ver esquema, tomas, eventos y alertas del paciente | ✅ | ✅ lo propio | ❌ |

> **Nomenclatura.** La tabla se llama `Medicacion` (no "prescripción") porque no todo lo que contiene lo receta un médico. `origen = medico` es lo indicado por el médico (**prescribir** es el acto de crear una); `origen = paciente` es lo que el paciente agrega por su cuenta y toma de forma habitual. El médico solo modifica lo suyo; el paciente solo lo propio.

### Versionado y ciclo de vida ([`service.py`](../src/treatment/service.py))

| Operación | Quién | Qué hace |
|---|---|---|
| `indicar_medicacion` | médico vinculado | Crea `Medicacion(origen=medico)` + su cronograma |
| `agregar_medicacion_propia` | el propio paciente | Crea `Medicacion(origen=paciente)` + su cronograma |
| `versionar_medicacion` | quien es dueño de esa medicación (médico vinculado / paciente) | Cierra la versión anterior (`reemplazada`, `vigente_hasta`), crea la nueva con `reemplaza_a_id` y borra las **tomas futuras pendientes** de la anterior. Las tomas pasadas (tildadas u omitidas) se conservan |
| `suspender_medicacion` | ídem | Estado `suspendida`; borra las tomas futuras pendientes |
| `registrar_toma` | el propio paciente | Marca `tomada` (con hora real) u `omitida` |
| `mantenimiento` | tarea periódica | Marca `finalizada` las que llegaron a su `fin` y extiende el cronograma de las crónicas hasta el horizonte (14 días). Es idempotente |

Reglas del versionado:
- La nueva versión rige desde `cambios["inicio"]` (por defecto, el momento del cambio).
- **El fin se hereda exacto** (`fin`): cambiar la dosis a mitad de un tratamiento no agrega ni quita dosis respecto del plan original. Si el médico pasa `duracion_dias`, se cuenta desde el nuevo inicio (`None` = pasa a crónico).
- **Cambio de marca (D-16):** se puede cambiar `producto_ref` al versionar **solo si el principio activo es idéntico** (se compara sin distinguir mayúsculas ni tildes). Ejemplo: de Tafirol a un paracetamol genérico, válido (mismo principio activo; es el caso "en la farmacia no hay tal medicamento"). De Tafirol a Ibupirac se rechaza, porque cambia la droga: hay que suspender la medicación e indicar otra, así el nuevo medicamento dispara su propio semáforo contra el resto del esquema y no se mezclan en una misma cadena las alertas ni la adherencia de dos drogas. Si no se puede verificar (un producto sin principio activo cargado, o sin `resolver`), también se rechaza.
- Solo se versiona una medicación `vigente`. Si hay un error de validación, **no se modifica nada** (cada operación es atómica).
- Si cambia el tipo de pauta (ej. de horarios fijos a cada 8 h), los campos de la pauta anterior no se arrastran.
- El vademécum se inyecta como `resolver(producto_ref) -> ProductoResuelto` (nombre y principios activos), así el servicio no depende todavía del grafo.

## 6. Cómo consume los datos el LLM

Implementado en [`snapshots.py`](../src/treatment/snapshots.py). Son funciones de **solo lectura**, determinísticas y con permisos (lee el propio paciente o un médico vinculado). Devuelven diccionarios JSON-serializables con fechas en la zona horaria del paciente.

| Función (tool) | Devuelve | Para qué |
|---|---|---|
| `estado_paciente(id)` | Medicación vigente con principios activos y pauta, próximas tomas, tomas sin registrar de las últimas 24 h, adherencia de 7 días (global y por producto), alertas abiertas, próxima consulta | Contexto del chat del paciente |
| `digest_periodo(id, desde, hasta)` | Adherencia global, por franja, por día y por producto; peor franja y peor día (con mínimo de 3 tomas); tomas omitidas (marcadas o sin registrar) y fuera de ventana; eventos; alertas; cambios de medicación | Insumo del resumen previo para el médico |
| `diff_medicacion(consulta_a, consulta_b)` | Qué se agregó, modificó (campo por campo, antes/después, `cambio_de_marca`), suspendió o finalizó | Insumo del resumen posterior para el paciente |
| `cambios_medicacion(id, desde, hasta)` | Lo mismo para un intervalo cualquiera (es lo que usan las dos anteriores) | Idem |

Decisiones de diseño:
- **El LLM solo redacta**; no cuenta ni calcula. Los patrones (peor franja, peor día) también los detecta el código.
- **Hechos con id** (`med:12`, `toma:7`, `evento:3`, `alerta:5`). `digest_periodo` y `cambios_medicacion` devuelven `hechos_fuente`, que se guarda en `Resumen.hechos_fuente`: permite evaluar automáticamente si un resumen cubre los hechos relevantes y si inventa alguno.
- **Listas acotadas** (`MAX_LISTA = 20`): si se recorta, el digest informa cuántos ítems quedaron fuera, y los conteos siguen siendo exactos.
- **El `texto` de los eventos lo escribió el paciente**: el prompt debe tratarlo como dato, nunca como instrucciones.
- **Los cambios se detectan por `inicio` y `vigente_hasta`** de cada versión (no hay fecha de creación). `diff_medicacion` extiende un día el borde de la segunda consulta, porque lo indicado en una consulta suele empezar ese mismo día.
- Lo que todavía no vencido no cuenta en la adherencia (misma regla D-10); las tomas pendientes de las últimas 24 h aparecen aparte como "sin registrar", para que el chat pueda preguntar por ellas.

## 7. Contratos de entrada

[`schemas.py`](../src/treatment/schemas.py) define `MedicacionInput`: el schema de entrada del formulario del médico (validado con Pydantic: horarios `HH:MM`, coherencia de la pauta, zona horaria obligatoria, rangos). El nombre del producto y los principios activos **no** se piden: el servicio los resuelve desde `producto_ref`.

## 8. Diferencias respecto del diseño discutido

- **No hay tablas `medico` y `paciente` separadas**: alcanza con `Usuario.rol` y `Vinculo`. Se agregan datos específicos (fecha de nacimiento, matrícula) si hacen falta.
- **`vencida` es derivada**, no un valor de `EstadoToma` (ver §4).
- Los datetimes se guardan en **UTC** y se muestran en la zona del usuario (`Usuario.zona_horaria`).

## 9. Pendiente

- [x] ~~Búsqueda por nombre/marca con candidatos y puntaje~~ → [`buscador.py`](../src/tools/buscador.py) (H-05, D-18). El formulario del médico (autocompletado) y el agente llaman a `buscar_medicamento` y trabajan con el `producto_ref` elegido.

- [x] ~~Funciones de snapshot (§6)~~ → [`snapshots.py`](../src/treatment/snapshots.py).
- [x] ~~Generador de pacientes sintéticos y base `gt_*` con la verdad~~ → [`src/synthetic/`](../src/synthetic/) (v0, ver §10).
- [ ] Control del máximo diario de las tomas a demanda (más arriba) y su registro como evento.
- [ ] Exportación a .ics a partir de las tomas.

## 10. Generador de pacientes sintéticos (v0)

Código en [`src/synthetic/`](../src/synthetic/). Decisiones D-23 a D-25 en `PLAN.md`.

| Módulo | Qué hace |
|---|---|
| `catalogo.py` | Lee el vademécum (solo lectura). Usa productos de **un** principio activo y una lista curada de patologías ambulatorias (8 crónicas, 6 agudas). |
| `perfil.py` | Arma el perfil: edad, 1–3 patologías, esquema de 1 a 8 medicamentos (todos con 1 comprimido por toma) y problemas sembrados: interacción (p = 0,20) y duplicidad por compra de otra marca (p = 0,15). |
| `conducta.py` | Decide qué hace el paciente con cada toma: tomada en hora, tomada tarde (61–180 min) u omitida (olvido o abandono), y si lo registra. Tres arquetipos (cumplidor, regular, olvidadizo); el olvido sube de noche y los fines de semana. |
| `redactor.py` | Escribe el texto del paciente con plantillas rioplatenses, con typos y sin tildes (interfaz `Redactor`, listo para un redactor con LLM). |
| `gt.py` | La verdad: `gt_paciente`, `gt_toma`, `gt_evento`, `gt_problema`. Base separada. |
| `generador.py` | Orquesta todo usando el **servicio real** (`indicar_medicacion`, `registrar_toma`, …). Misma semilla ⇒ misma cohorte. |
| `validacion.py` | Informe de validez y diversidad, y la brecha entre adherencia **verdadera** y **registrada**. |

**Verdad vs. registro.** Para cada toma se guarda qué pasó (`resultado`) y qué quedó en el sistema (`registro`: tildada, marcada omitida o sin registrar). Se puede tomar y no tildar, o no tomar y no avisar; por eso la adherencia registrada es siempre ≤ la verdadera, y esa brecha es una métrica de la evaluación.

**Qué ve el sistema.** Los eventos de texto libre se guardan con `tipo = otro`, sin `producto_ref` ni `extraccion`: eso lo tiene que inferir el extractor; la respuesta correcta está solo en `gt_evento`.

**Límites conocidos (v0).**
- Dosis fija (1 comprimido) y pautas de un catálogo corto: la plausibilidad clínica la revisa el médico (M2).
- Un solo médico y una sola consulta por paciente; no se simulan cambios de esquema (versionado) durante el período.
- "Interacción" significa *par que figura en la tabla del vademécum* (se excluyen los textos que dicen que no hay); no distingue severidad (H-07).
- Las tomas de las últimas 3 h no se simulan (quedan pendientes y sin verdad).
- Tasa de interacciones alta a propósito (para tener positivos); hay que balancearla al armar el benchmark.
- Generar 50 pacientes tarda ~1,5 min (cada acción pasa por el servicio real).

