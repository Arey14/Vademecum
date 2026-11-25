# Hallazgos de la revisión inicial del repositorio

> Revisión hecha el 07/11/2026 sobre el commit `5e05c05` contra la consigna del TP (`[SHR] - Consigna TP - IA Agéntica 2026.md`) y los comentarios docentes (`IAA-TP.docx`).
> Cada hallazgo tiene un ID para referenciarlo en commits, PRs e issues (ej. `fix(H-05): ...`).
> **Estados:** `Abierto` · `En curso` · `Resuelto` · `Fuera de alcance` (con justificación) · `Descartado`.
> Para proponer un cambio de estado o discutir un hallazgo, comentarlo en el grupo o en el PR correspondiente; el cambio queda registrado en [CHANGELOG.md](../CHANGELOG.md).

## Resumen

| ID | Severidad | Tema | Estado | Responsable |
|---|---|---|---|---|
| H-01 | 🔴 Crítico | No hay LLM en el sistema | Abierto | — |
| H-02 | 🔴 Crítico | No hay hipótesis, baseline ni evaluación | Abierto | — |
| H-03 | 🔴 Crítico | Licencia y fecha de los datos no documentadas | Abierto | — |
| H-04 | 🔴 Crítico | Historia de git con un único autor | Abierto | — |
| H-05 | 🟠 Alto | Búsqueda de medicamentos peligrosa (match por substring) | Resuelto | Germán |
| H-06 | 🟠 Alto | 75% de las interacciones vienen de propagación por clase sin validar | Abierto | — |
| H-07 | 🟠 Alto | Interacciones sin severidad (semáforo) | Abierto | — |
| H-08 | 🟠 Alto | Alcohol y alimentos no modelados | Abierto | — |
| H-09 | 🟠 Alto | Huecos de cobertura en los datos | En curso (IDs únicos resueltos) | — |
| H-10 | 🟡 Medio | Reproducibilidad: rutas absolutas, sin Makefile/Docker/tests | Abierto | — |
| H-11 | 🟡 Medio | Dataset de fine-tuning circular y con errores de template | Fuera de alcance (D-05) | — |
| H-12 | 🟡 Medio | README con cifras desactualizadas y afirmaciones no medidas | En curso (cifras del grafo actualizadas) | — |
| H-13 | 🟡 Medio | El CLI de interacciones no corre en consolas de Windows (cp1252) | Resuelto | Germán |

---

## 🔴 Críticos (contradicen requisitos explícitos de la consigna)

### H-01 · No hay LLM en el sistema
- **Evidencia:** no hay llamadas a ningún modelo (OpenAI, Anthropic, Gemini, Ollama, LangChain, etc.) en `src/` ni en `app.py`.
- **Por qué importa:** la consigna exige "IA generativa en el núcleo".
- **Propuesta:** agente con tools sobre el grafo (ver plan de trabajo).

### H-02 · No hay hipótesis, baseline ni evaluación
- **Evidencia:** no existe benchmark, partición dev/test, script de evaluación ni comparación contra un baseline.
- **Por qué importa:** "Evaluación, evidencia y costos" vale el 25% de la nota. Los docentes pidieron medir **cobertura** y comparar contra **LLMs genéricos**.
- **Propuesta:** benchmark propio con split fijo, baselines LLM zero-shot y reporte de costo y latencia.

### H-03 · Licencia y fecha de los datos no documentadas
- **Evidencia:** los datos se scrapearon de `ar.prvademecum.com` (`src/scraping/*`). No está registrada la licencia ni los términos de uso del sitio, ni la fecha de extracción.
- **Por qué importa:** la consigna pide "fuentes con volumen, actualización y licencia identificados".
- **Propuesta:** escribir una *data card* (`docs/DATOS.md`) con la fuente, los términos de uso, la fecha y los volúmenes. Evaluar las fuentes abiertas de ANMAT como complemento o alternativa.

### H-04 · Historia de git con un único autor
- **Evidencia:** 4 commits del 17/09/2026, todos del mismo autor.
- **Por qué importa:** la consigna evalúa "una historia que refleje la contribución de todos los integrantes".
- **Propuesta:** todos como colaboradores del repo, una rama por tarea, PRs con revisión y issues asignados.

---

## 🟠 Altos (riesgo clínico o de calidad; aparecen en la defensa)

### H-05 · Búsqueda de medicamentos peligrosa
- **Evidencia:** `find_product()` en `src/tools/check_interactions.py`: si no hay match exacto, devuelve el **primer** resultado de `LIKE '%texto%'`. Casos reales:
  - `"ibu"` → `AMOXICILINA SANT GALL FRIBURG` (porque "FRIBURG" contiene "ibu").
  - `"Amoxicilina"` → `AMOXICILINA CLAVULANICO FORTE RICHET` (asume una combinación sin preguntar).
  - `"Alcohol"` → `DG-6 ALCOHOL AEROSOL`.
- **Por qué importa:** si se resuelve mal el medicamento, todo el análisis posterior queda mal, sin ningún aviso al usuario.
- **Propuesta:** resolver con normalización (tildes, mayúsculas, ®), búsqueda difusa, alias de marcas, ranking top-k con puntaje y **desambiguación** cuando hay varios candidatos. Agregar tests con estos casos.
- **Resolución (08/11/2026):** nuevo [`src/tools/buscador.py`](../src/tools/buscador.py) (decisión D-18). Devuelve candidatos con puntaje y un estado `resuelto` / `ambiguo` / `no_encontrado`; distingue producto de sustancia; un typo nunca se resuelve solo; `evaluate_combination` frena el análisis y lista los candidatos cuando hay ambigüedad. `find_product` pasó a ser exacto (sin coincidencia parcial). Resultado sobre los casos del hallazgo: `ibu` → 77 candidatos (ninguno es FRIBURG); `Amoxicilina` → la **sustancia**; `Alcohol` → la **sustancia**. **Límite conocido:** los umbrales se ajustaron con ~25 consultas de ejemplo, no con un benchmark; la medición real es la tarea L1 del plan (gold de marcas argentinas → principio activo).

### H-06 · 75% de las interacciones vienen de propagación por clase sin validar
- **Evidencia:** de 19.087 aristas `sustancia_interaccion`, **14.238** son "Interacción de Clase", 235 son "contraindicación" y 4.614 son directas. Errores detectados:
  - El patrón de acción `antiinflamatorio` clasifica **8 corticoides o afines como AINEs** (Betametasona, Dexametasona, Hidrocortisona, Prednisolona, Triamcinolona, Mesalazina...). Dexametasona y Betametasona reciben 92 aristas falsas cada una.
  - Se ignoran las negaciones: 144 monografías dicen "no se han observado / no se conocen interacciones" y el regex igual genera aristas.
  - El campo `detalle` tiene los primeros 300 caracteres del texto entero, no la oración que justifica la interacción.
- **Por qué importa:** la bitácora reporta "+321% de cobertura", pero eso mide cantidad de aristas, no cobertura real. La precisión no se conoce.
- **Propuesta:** corregir las clases y las negaciones, guardar la oración de evidencia y **medir la precisión** sobre una muestra etiquetada. Evaluar la extracción con LLM como alternativa al regex.

### H-07 · Interacciones sin severidad (semáforo)
- **Evidencia:** la tabla `sustancia_interaccion` no tiene ningún campo de severidad.
- **Por qué importa:** los docentes lo pidieron explícitamente ("no todas las interacciones son patológicas").
- **Propuesta:** clasificar cada interacción en 🔴 / 🟡 / 🟢 (con LLM sobre la oración de evidencia), validando contra etiquetas humanas o una referencia externa (DDInter: revisar licencia).

### H-08 · Alcohol y alimentos no modelados
- **Evidencia:** no hay nodos de alcohol ni de alimentos. La monografía de Metronidazol sí lo menciona ("No se recomienda el uso simultáneo con alcohol..."), pero el grafo no lo captura.
- **Por qué importa:** es un caso de uso de la propia presentación ("¿puedo tomar alcohol si estoy con metronidazol?").
- **Propuesta:** pseudo-nodos (`Alcohol`, `Alimentos`, `Lácteos`, `Pomelo`...) extraídos del texto de las monografías.

### H-09 · Huecos de cobertura en los datos
- **Evidencia:**
  - Entre 57% y 65% de las sustancias no tienen monografía: solo 935 de 2.648 tienen `interacciones`, 1.102 `contraindicaciones` y 1.140 `dosificacion`.
  - 117 productos no tienen ningún principio activo vinculado.
  - Hay 22 nombres de producto duplicados, que colisionan en el nodo `Prod:{nombre}`.
  - Las columnas `sobredosificacion` y `medicamentos` del CSV no se cargan en la base.
  - No hay precios ni posología por presentación.
- **Propuesta:** documentar la cobertura en la data card, usar un ID único por producto, y responder "sin información" en vez de "sin interacciones" cuando falte la monografía.
- **Avance (08/11/2026):** resuelto el ID único: cada producto tiene `producto_ref` (`pv-<id>`), que es la clave de `producto_sustancia` y `producto_patologia` y el id de los nodos `Prod:` del grafo (ver D-17 en [PLAN.md](PLAN.md)). Los 22 nombres duplicados ya no se fusionan: el grafo pasó de 11.533 a 11.555 nodos. Los productos sin principio activo son **118** (antes 117, porque la fusión por nombre ocultaba uno). Siguen abiertos: las monografías faltantes, las columnas `sobredosificacion` y `medicamentos` sin cargar y la ausencia de precios.

---

## 🟡 Medios (ingeniería y reproducibilidad)

### H-10 · Reproducibilidad
- **Evidencia:**
  - Rutas `/home/augusto/...` en `src/etl/merge_datasets.py`, en el shebang de `src/etl/fill_principios_patologias.py`, en `README.md` y en `BITACORA.md`.
  - `requirements.txt` sin versiones fijadas.
  - No hay Makefile, Docker ni tests.
  - Los scrapers escriben archivos en el directorio de trabajo.
- **Por qué importa:** la consigna pide un "sistema funcional con procesos replicables" y que corra siguiendo el README.
- **Propuesta:** Makefile (`setup`, `data`, `graph`, `app`, `eval`, `test`), Dockerfile, `.env.example`, pytest y rutas basadas en `src/config.py`.

### H-11 · Dataset de fine-tuning circular y con errores de template
- **Evidencia:** las respuestas de `Final/vademecum_finetune_train.jsonl` son copias templadas de la misma base. Tiene errores como "Contraindicado en Se deberá evaluar..." y textos cortados con "...".
- **Por qué importa:** entrenar con esto enseña a memorizar una base que ya se consulta por tool. Además, evaluar contra esa misma base no prueba nada.
- **Propuesta:** dejar el fine-tuning fuera de alcance y justificarlo en el informe como alternativa evaluada y descartada.
- **Resolución (07/11/2026):** se reemplaza el fine-tuning por tools + RAG (decisión D-05 en [PLAN.md](PLAN.md)). El dataset y su generador quedan en el repo como antecedente; no se usan.

### H-12 · README con cifras desactualizadas y afirmaciones no medidas
- **Evidencia:** el README dice 11.135 relaciones producto-sustancia (en la base hay 12.088) y 12.900 producto-patología (hay 11.941). También promete respuestas "sin alucinaciones", algo que no está medido.
- **Propuesta:** regenerar las cifras con un script y reemplazar afirmaciones por resultados medidos.

---

### H-13 · El CLI de interacciones no corre en consolas de Windows
- **Evidencia:** `python check_interactions.py Sintrom Ibupirac` en una consola de Windows falla con `UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f4cb'`, porque el informe imprime emojis y la consola usa cp1252.
- **Por qué importa:** la consigna exige que el sistema corra siguiendo el README; el equipo trabaja en Windows y Linux.
- **Resolución (08/11/2026):** `main()` reconfigura `stdout` a UTF-8. Pendiente de revisar: el resto de los scripts que imprimen emojis.

## Cómo reproducir la evidencia

```bash
# H-05: búsqueda por substring
python -c "import sqlite3,sys; sys.path.insert(0,'.'); from src.tools.check_interactions import find_product; c=sqlite3.connect('Final/vademecum_graph.db').cursor(); [print(q,'->',(find_product(c,q) or {}).get('nombre')) for q in ['ibu','Amoxicilina','Alcohol']]"

# H-06: origen de las aristas de interacción
sqlite3 Final/vademecum_graph.db "select case when detalle like '[Interacci%' then 'clase' when detalle like '[Contra%' then 'contra' else 'directa' end k, count(*) from sustancia_interaccion group by k;"
```
