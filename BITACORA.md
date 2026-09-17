# 📜 Bitácora de Desarrollo: Proyecto Vademecum
> **Grafo de Conocimiento Farmacológico & Pipeline de Fine-Tuning para LLMs**  
> **Repositorio Oficial:** [https://github.com/Arey14/Vademecum](https://github.com/Arey14/Vademecum)

---

## 🎯 Resumen Ejecutivo

El proyecto **Vademecum** implementa una arquitectura híbrida **Grafo de Conocimiento (NetworkX + SQLite) + Modelo de Lenguaje Fine-Tuned** orientada al análisis determinístico y libre de alucinaciones de medicamentos, principios activos, duplicidades de dosis, contraindicaciones clínicas e interacciones farmacológicas.

Esta bitácora documenta de manera cronológica y técnica todos los hitos de ingeniería de datos, reestructuración de código, visualización y enriquecimiento semántico realizados en el proyecto.

---

## 📅 Registro Cronológico de Hitos

### 🔹 Hito 1: Extracción Web (Scraping) y Normalización (ETL)
* **Objetivo:** Construir una base de datos farmacológica completa a partir de monografías técnicas de medicamentos en Argentina.
* **Acciones Realizadas:**
  - Desarrollo de scrapers asíncronos con **Playwright** y **BeautifulSoup** para extraer:
    1. Catálogo completo de medicamentos comerciales.
    2. Monografías de principios activos (acción terapéutica, posología, contraindicaciones, precauciones, interacciones y reacciones adversas).
    3. Catálogo de laboratorios farmacéuticos (dirección, contacto, portfolio).
  - Normalización y limpieza:
    - Fusión y deduplicación estricta por URL (`merge_datasets.py`).
    - Corrección de truncamiento en nombres de laboratorios (`fix_lab_names.py`).
    - Parsing y extracción de secciones de principios activos y patologías (`fill_principios_patologias.py`).
* **Resultados Obtenidos:**
  - **8.349 Medicamentos comerciales.**
  - **2.647 Principios activos / Sustancias.**
  - **296 Laboratorios farmacéuticos.**

---

### 🔹 Hito 2: Reorganización, Modularización y Portabilidad del Código
* **Objetivo:** Transformar un repositorio plano con scripts dispersos en una arquitectura modular, escalable y mantenible, garantizando la preservación de los datos finales.
* **Acciones Realizadas:**
  - **Preservación 100% Intacta de `Final/`:** Se resguardaron los archivos consolidados (`vademecum_productos.csv`, `vademecum_sustancias.csv`, `vademecum_laboratorios.csv`, etc.).
  - **Modularización en paquetes `src/`:**
    - `src/config.py`: Rutas dinámicas con `pathlib.Path` para evitar rutas absolutas rígidas.
    - `src/scraping/`: Scrapers de laboratorios, productos y sustancias.
    - `src/etl/`: Pipelines de limpieza, fusión y migración a SQLite.
    - `src/graph/`: Construcción y exportación del grafo de conocimiento.
    - `src/dataset/`: Generador de datasets para fine-tuning de LLMs.
    - `src/tools/`: Motor determinístico de evaluación e interacciones CLI.
  - **Separación de Datos y Logs:**
    - Datos intermedios trasladados a `data/intermediate/`.
    - Logs centralizados en `logs/`.
  - **Estandarización de Entorno:**
    - Creación de `.gitignore` (exclusión de cachés, `.playwright-mcp/`, logs).
    - Creación de `requirements.txt` con todas las dependencias del proyecto.
    - Creación de un wrapper transparente `check_interactions.py` en la raíz para consultas por CLI.

---

### 🔹 Hito 3: Publicación y Versionado en GitHub
* **Objetivo:** Versionar y publicar el código y datasets en GitHub.
* **Acciones Realizadas:**
  - Inicialización del repositorio Git local en rama `main`.
  - Configuración y subida remota a GitHub mediante GitHub CLI (`gh`).
  - Repositorio público disponible en: **`https://github.com/Arey14/Vademecum`**.

---

### 🔹 Hito 4: Visualizador Web Interactivo del Grafo (Streamlit + PyVis)
* **Objetivo:** Proveer una interfaz gráfica de usuario interactiva y moderna para explorar las relaciones del grafo y evaluar combinaciones de medicamentos en tiempo real.
* **Acciones Realizadas:**
  - Desarrollo de `app.py` y el módulo `src/ui/`:
    - `src/ui/graph_renderer.py`: Motor de renderizado con física de fuerzas (ForceAtlas2), tema oscuro, zoom, pan, clics interactivos y tooltips con reportes clínicos.
    - `src/ui/views.py`: Vistas especializadas conectadas directamente a SQLite.
  - **3 Modos de Visualización Implementados:**
    1. 💊 **Evaluador de Combinaciones:** Búsqueda autocompletada de 2 o más medicamentos. Muestra subgrafo con alertas visuales (duplicidades de principios activos en rojo con forma de estrella, interacciones directas en naranja y laboratorios asociados).
    2. 🔍 **Explorador de Entidades (Ego-Graph):** Búsqueda de cualquier Medicamento, Sustancia o Laboratorio a 1 y 2 saltos con Ficha Técnica completa (acción terapéutica, posología, contraindicaciones).
    3. 🌐 **Red Global de Interacciones:** Grafo general de sustancias filtrable por grado de conectividad mínima y tabla interactiva de interacciones.

---

### 🔹 Hito 5: Expansión Semántica y Enriquecimiento del Grafo de Interacciones
* **Objetivo:** Superar la limitación del matching textual estricto para multiplicar la cobertura factual de interacciones y contraindicaciones clínicas.
* **Problema Identificado:**
  - Muchas monografías advierten interacciones por **clase terapéutica** (*"Interactúa con AINEs, anticoagulantes o betabloqueantes"*) sin nombrar individualmente a los 30+ fármacos de esa familia.
  - Más de 80 ácidos figuraban en formato de índice (`Acetilsalicílico ácido`, `Valproico ácido`, etc.).
  - Numerosas interacciones críticas estaban redactadas en la sección `contraindicaciones` y `precauciones`.
* **Solución Implementada:**
  1. **Taxonomía Farmacológica ([`src/graph/pharmacological_classes.py`](file:///home/augusto/Desktop/Vademecum/src/graph/pharmacological_classes.py)):**
     - Mapeo de **25+ familias farmacológicas clave** (AINEs, Anticoagulantes, Antiagregantes, Betabloqueantes, IECAs, ARA II, Benzodiacepinas, Corticoides, Diuréticos, IBPs, Macrólidos, Quinolonas, Aminoglucósidos, Tricíclicos, ISRS, IMAO, Digitálicos, Hipoglucemiantes, Opioides, Estatinas, Antihistamínicos, Neurolépticos, Nitratos).
  2. **Inversión y Normalización de Ácidos:**
     - Algoritmo de resolución bidireccional automática (*"Acetilsalicílico ácido" $\leftrightarrow$ "Ácido acetilsalicílico" / "Aspirina"*).
  3. **Minería de Contraindicaciones y Precauciones:**
     - Detección de advertencias de administración concomitante prohibida (ej. *Sildenafilo + Nitroglicerina*).
  4. **Propagación por Clase Terapéutica:**
     - Si una sustancia advierte interacción con una clase, el grafo genera automáticamente las aristas específicas hacia todos los miembros de esa familia con la justificación clínica asociada.
* **Impacto y Métricas Comparativas:**
  - **Aristas de Interacción:** De **4.533** a **19.087** (**+321%** / x4.2 de cobertura).
  - **Total de Aristas en el Grafo:** De **28.570** a **43.122** (**+51%**).
  - **Dataset de Fine-Tuning:** Regenerado en `Final/vademecum_finetune_train.jsonl` con 1.500 pares de entrenamiento enriquecidos para ShareGPT / Llama-3 / Qwen.

---

## 📊 Resumen Estadístico Final del Proyecto

```
┌─────────────────────────────────────────────────────────────┐
│               MÉTRICAS DEL GRAFO DE CONOCIMIENTO            │
├─────────────────────────────────────────────────────────────┤
│  • Medicamentos Comerciales:         8.349                  │
│  • Principios Activos / Sustancias:  2.647                  │
│  • Laboratorios Farmacéuticos:         296                  │
│  • Total de Nodos en el Grafo:      11.533                  │
│  • Interacciones Fármaco-Fármaco:   19.087                  │
│  • Total de Relaciones (Aristas):   43.122                  │
│  • Pares de Entrenamiento LLM:       1.500 (JSONL/ShareGPT) │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔗 Enlaces y Recursos

* **Repositorio GitHub:** [https://github.com/Arey14/Vademecum](https://github.com/Arey14/Vademecum)
* **Guía de Uso del Visualizador:** `streamlit run app.py`
* **Evaluador por Terminal:** `python3 check_interactions.py "MEDICAMENTO_1" "MEDICAMENTO_2"`
