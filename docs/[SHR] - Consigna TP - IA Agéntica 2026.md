# Trabajo Práctico Integrador

IA Agéntica. Maestría en Explotación de Datos y Descubrimiento del Conocimiento (UBA). Docentes: Edgar Altszyler, Matías Grinberg, Francis Felici. 

El TP integra los contenidos de la materia en el desarrollo grupal de un sistema con IA generativa aplicado a un problema que elige cada grupo, con un usuario identificable y una hipótesis medible. Vale el 50% de la nota final.

## Metodología

* Grupos de 4 a 6 personas.

* El caso lo propone cada grupo y lo valida la cátedra antes de empezar a construir.

* Instancias: propuesta escrita, seguimientos en clase, y entrega final con exposición oral. 

## Características requeridas del caso

Todo proyecto, sin excepción, debe tener:

* **Utilidad real.** Resuelve o asiste una tarea concreta de una población o una organización identificable. O genera un conocimiento relevante como respuesta a una hipótesis inicial en caso de un trabajo de investigación.  

* **IA generativa en el núcleo.** Un modelo de lenguaje es core del proyecto. No necesariamente el sistema es estrictamente agéntico.

* **Hipótesis medible**: propuesta y preferiblemente contrastada contra un baseline. “El enfoque elegido mejora X frente a Y”, con Y un baseline más simple (prompt zero-shot, script determinístico, clasificador clásico o el proceso manual actual). Siendo X una métrica cuantitativa propuesta sobre un conjunto de evaluación con partición fija entre desarrollo y test, o un KPI en caso de aplicación productiva formulando cómo se abordaría el proceso de evaluación.

* **Datos verificados.** Fuentes públicas, propias o sintéticas, con volumen, actualización y licencia identificados. Si son sintéticos, el generador es parte del sistema y se evalúa. En caso de usar datos privados, debe compartirse una muestra sanitizada para permitir replicabilidad.

* **Economía del sistema**. Evaluación de factibilidad y costos en base a modelos locales o la infraestructura que el proyecto pida. Costo por tarea (tokens y dinero), latencia, y justificación de la elección de modelo e infraestructura frente a alternativas.

* **Repositorio con trabajo distribuido.** Git usado de manera prolija, con una historia que refleje la contribución de todos los integrantes.

* **Revisión de antecedentes.** Revisión de mercado: qué productos, herramientas o servicios resuelven hoy este problema o uno cercano, en qué se diferencia lo que proponen y por qué alguien lo elegiría. Revisión de literatura científica: qué trabajos publicados abordan la tarea, con qué métodos, qué métricas usan para medirla y qué resultados reportan como referencia. Va en la propuesta en versión breve y se profundiza en el informe final. Que el problema ya esté resuelto por otros no descalifica el proyecto, pero obliga a explicitar qué aporta el suyo (i.e. estrategia de diferenciación) y a usar lo existente como punto de comparación.

Además, debe profundizar de manera sustantiva en al menos 2 de las siguientes áreas. Sustantiva significa parte del núcleo del diseño, no un agregado decorativo; pesa más la profundidad que la cantidad:

* Recuperación de información y context engineering sobre un corpus propio, con el retrieval evaluado por separado de la generación.

* Uso de herramientas y function calling, con contratos y manejo de errores, o integración vía HTTP y/o MCP.

* Orquestación: ruteo, encadenamiento de pasos, multiagente, o loops de verificación y reintento contra un criterio automático.

* Memoria, estado y gestión del contexto en interacciones largas.

* *Skills*

* Observabilidad y guardrails: trazas, registro de costos, validación de entradas y salidas, límites de acción.

* Evaluación: juez LLM con rúbrica calibrada contra evaluación humana, benchmark propio del dominio, u otros (evals).

* Human in the loop, con medición de su costo y de su efecto sobre la calidad.

* Inferencia local con modelos abiertos, comparada en calidad, costo y latencia contra un modelo de API.

* Optimización sistemática (e idealmente algorítmica) de prompts contra la métrica.

## Propuesta del proyecto

Cada grupo entrega un documento de 2 a 4 carillas, a elección: un [press release](https://workingbackwards.com/concepts/working-backwards-pr-faq-process/) o un [PRD](https://www.atlassian.com/agile/product-management/requirements). En cualquiera de los dos formatos tiene que responder explícitamente:

* Por qué el problema necesita un modelo de lenguaje y no se resuelve mejor con software convencional.

* Con qué datos o corpus funciona y de dónde salen, ya explorados.

* Cómo van a medir que funciona: métrica, alternativa contra la que comparan, hipótesis.

* Cuál es el mayor riesgo técnico y cuál es el plan B.

* Qué queda explícitamente afuera del alcance.

* Cómo piensan estimar el costo de operar el sistema.

Cada grupo lo presenta y recibe devolución. La cátedra puede aprobar, pedir ajustes de alcance o rechazar; si pide ajustes, el grupo tiene una semana para volver a presentar. 

## Entrega final y exposición

Se debe entregar: 

- Un repositorio en GitHub incluyendo el sistema funcional con procesos replicables, con instrucciones en README y código para ejecutar (Simil Makefile, bash). Debe incluir todos los artefactos utilizados durante el desarrollo, incluyendo SKILLS, reglas u otros.   
- Presentación para exponer incluyendo descripción del problema y usuarios, casos de uso, hipótesis y resultados, arquitectura con diagrama, qué se hizo en cada área de profundización, evaluación sobre test, costos, limitaciones, y qué harían distinto o próximos pasos.

La exposición oral es de 15 minutos más preguntas, con todos los integrantes. Una parte central es contar cómo fue el desarrollo: qué bloqueos aparecieron, qué no funcionó y por qué, qué decisiones cambiaron el rumbo, cómo usaron asistentes de IA y qué aprendieron. 

## Fechas 

| Instancia | Cierre | Clase |
| :---- | :---- | :---- |
| Propuesta (press release, o PRD) | Jueves 10/9 | Jueves 10/9, presentación de 10 minutos. |
| Entrega final | Jueves 19/11 | Exposición oral el 10/12 o el 11/12, a confirmar |

## Criterios de evaluación

Lo que el grupo declara en la propuesta, el informe y la exposición tiene que ser verificable en el repositorio.

* **Problema, utilidad e hipótesis (15%).** Usuario real, tarea acotada, hipótesis medible, viabilidad.

* **Diseño del sistema y uso de LLMs (25%).** El modelo está bien usado y bien rodeado: contexto, contratos, manejo de errores, decisiones justificadas. Las áreas elegidas están tratadas en serio.

* **Evaluación, evidencia y costos (25%).** Alternativa simple medida, evaluación reproducible, comparación honesta sobre test, análisis de fallas, costo y latencia reportados. Resultados verificables, no fabricados para la demo.

* **Ingeniería y trabajo en equipo (10%).** El sistema y la evaluación corren siguiendo el README. Buen manejo de git y contribuciones efectivamente distribuidas.

* **Exposición y defensa (25%).** Claridad, trade-offs, limitaciones y el relato del desarrollo. La defensa es individual además de grupal: cada integrante debe poder explicar el sistema completo y razonar sobre alternativas que no tomaron.

## Comunicación durante el desarrollo

Consultas por [Discord](https://discord.gg/HUjb5Q6Gs), con un canal por grupo.

## Consideraciones

* La originalidad suma pero no es requisito.

* Se recomienda Python o TypeScript como lenguaje de desarrollo, con desarrollo dockerizado para replicabilidad y puesta en producción. Se puede usar cualquier framework, pero el grupo tiene que poder explicar la arquitectura por debajo.

* Se pueden usar entornos como Replit u otras plataformas de desarrollo asistido, pero el entregable es el sistema funcional y replicable en el repositorio.

* El uso de asistentes de IA es requisito. En la defensa el grupo tiene que poder explicar cada parte del sistema, y exponer las maneras en las cuales usaron las herramientas de desarrollo. 