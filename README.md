# 💊 Vademecum: Grafo de Conocimiento Farmacológico & Dataset LLM

Pipeline integral de extracción (Scraping), normalización (ETL), construcción de **Grafo de Conocimiento Farmacológico** (NetworkX + SQLite) enriquecido con taxonomía de clases terapéuticas y generación de **Datasets de Fine-Tuning** (ShareGPT/JSONL) para modelos de lenguaje especializados en farmacología clínica.

---

## 🏛️ Arquitectura del Sistema

El proyecto implementa un enfoque híbrido **Determinístico + Probabilístico (LLM)** para evitar alucinaciones en el análisis de interacciones farmacológicas:

```
                  ┌──────────────────────────────────────────────┐
                  │          Pipeline de Scraping & ETL          │
                  │   (Playwright + BeautifulSoup + Pandas)      │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │             Datasets Limpios (Final/)        │
                  │  • Productos  • Sustancias  • Laboratorios   │
                  └──────────────────────┬───────────────────────┘
                                         │
                   ┌─────────────────────┴─────────────────────┐
                   ▼                                           ▼
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│    Grafo de Conocimiento (NetworkX) │     │      Dataset de Instrucción         │
│     & SQLite Indexado (Final/)      │     │            para LLMs                │
│  • Nodos: 11.533                    │     │   (vademecum_finetune_train.jsonl)  │
│  • Relaciones: 43.122               │     │  • 1.500 pares conversacionales     │
│  • Interacciones directas: 19.087   │     │  • Formato ShareGPT / ChatML        │
└──────────────────┬──────────────────┘     └──────────────────┬──────────────────┘
                   │                                           │
                   ▼                                           ▼
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│ Verificador Determinístico          │     │  Modelo Fine-Tuned                  │
│ (check_interactions.py / Web App)   │ ◄─► │  (Llama-3 / Qwen-2.5 / LoRA)        │
│  • Duplicidades de principio activo │     │   Respuestas fundamentadas          │
│  • Interacciones cruzadas directas  │     │   sin alucinaciones                 │
│  • Contraindicaciones y alertas     │     │                                     │
└─────────────────────────────────────┘     └─────────────────────────────────────┘
```

---

## 📂 Estructura del Repositorio

```text
Vademecum/
├── Final/                               # 🔒 Datasets Finales y Artefactos de Producción
│   ├── todo.txt                         # Hoja de ruta y pasos futuros
│   ├── vademecum_finetune_train.jsonl   # Dataset de Fine-Tuning (1.500 diálogos QA)
│   ├── vademecum_graph.db               # Base SQLite indexada del Grafo (19.087 interacciones)
│   ├── vademecum_graph.json             # Grafo de red exportado en JSON
│   ├── vademecum_laboratorios.csv       # Catálogo maestro de laboratorios
│   ├── vademecum_productos.csv          # Catálogo maestro de productos comerciales
│   └── vademecum_sustancias.csv         # Fichas técnicas de principios activos
│
├── data/
│   └── intermediate/                    # Datos y bases intermedias de trabajo ETL
│       ├── Lista_productos.csv
│       ├── vademecum.db
│       ├── vademecum_laboratorios.csv
│       ├── vademecum_productos_complete.csv
│       └── vademecum_sustancias.csv
│
├── logs/                                # Logs de ejecución de scrapers y pipelines
│   └── scrape.log
│
├── src/                                 # Código Fuente Modular
│   ├── config.py                        # Configuración centralizada de rutas dinámicas
│   │
│   ├── scraping/                        # 1. Módulo de Extracción Web
│   │   ├── collect_product_urls.py      # Recolección masiva de URLs de productos
│   │   ├── scrape_vademecum_labs.py     # Scraper de laboratorios farmacéuticos
│   │   ├── scrape_vademecum_productos.py# Scraper de fichas de medicamentos
│   │   └── scrape_vademecum_sustancias.py # Scraper de sustancias y monografías
│   │
│   ├── etl/                             # 2. Módulo de Limpieza y Transformación
│   │   ├── fill_principios_patologias.py# Enriquecimiento y parsing de componentes
│   │   ├── fix_lab_names.py             # Normalización de nombres de laboratorios
│   │   ├── merge_datasets.py            # Fusión y desduplicación de lotes
│   │   └── migrar_a_sqlite.py           # Migración a base de datos relacional
│   │
│   ├── graph/                           # 3. Construcción del Grafo de Conocimiento
│   │   ├── build_vademecum_graph.py     # Generador de vademecum_graph.json y .db
│   │   └── pharmacological_classes.py   # Taxonomía de 25+ familias farmacológicas y alias
│   │
│   ├── dataset/                         # 4. Generación de Dataset para LLMs
│   │   └── generate_finetune_dataset.py # Creador de pares de diálogo para entrenamiento
│   │
│   ├── tools/                           # 5. Herramientas CLI y Evaluación
│   │   └── check_interactions.py        # Motor de consulta y evaluación clínica
│   │
│   └── ui/                              # 6. Componentes del Visualizador Interactivo
│       ├── __init__.py
│       ├── graph_renderer.py            # Generador de subgrafos interactivos PyVis
│       └── views.py                     # Vistas de combinaciones, entidades y mapa global
│
├── app.py                               # 🚀 Aplicación Web Interactiva (Streamlit)
├── check_interactions.py                # Wrapper en raíz para ejecución directa CLI
├── requirements.txt                     # Dependencias del entorno
├── .gitignore                           # Exclusiones de Git
├── BITACORA.md                          # 📜 Registro histórico y bitácora técnica de hitos
└── README.md                            # Documentación del proyecto
```

---

## 🚀 Instalación y Requisitos

### 1. Clonar e Instalar Dependencias

```bash
# Crear y activar entorno virtual (opcional pero recomendado)
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# (Opcional, solo si se ejecutan scrapers web)
playwright install chromium
```

---

## 💡 Guía de Uso

### 1. Visualizador Interactivo del Grafo (Web App)

Inicia la aplicación interactiva de visualización con física de fuerzas, zoom, tooltips clínicos y 3 modos de exploración:

```bash
streamlit run app.py
```
*(O con tu entorno virtual: `/home/augusto/envs/tesis/bin/streamlit run app.py`)*

**Modos disponibles en la aplicación:**
1. 💊 **Evaluador de Combinaciones:** Ingresa 2 o más medicamentos y visualiza el subgrafo con alertas automáticas (duplicidades en rojo, interacciones en naranja, laboratorios y principios activos).
2. 🔍 **Explorador de Entidades (Ego-Graph):** Búsqueda de cualquier Medicamento, Sustancia o Laboratorio a 1 y 2 saltos con su ficha técnica completa al costado.
3. 🌐 **Red Global de Interacciones:** Visualización del mapa denso de sustancias con filtros por conectividad mínima y tabla interactiva de interacciones.

---

### 2. Consultar Interacciones entre Medicamentos (CLI)

Puedes evaluar cualquier combinación de medicamentos comerciales directamente por terminal:

```bash
python3 check_interactions.py "Sintrom" "Ibupirac"
```

**Ejemplo de salida:**
```text
=======================================================
      INFORME DE EVALUACIÓN DE INTERACCIONES
=======================================================

📋 MEDICAMENTOS ANALIZADOS:
  • SINTROM® (Lab: SIEGFRIED)
    Principios Activos: Acenocumarol
  • IBUPIRAC (Lab: PFIZER)
    Principios Activos: Ibuprofeno

-------------------------------------------------------
1. RIESGO DE DUPLICACIÓN DE PRINCIPIOS ACTIVOS:
  ✅ Sin duplicaciones de principios activos detectadas.

-------------------------------------------------------
2. INTERACCIONES FARMACOLÓGICAS DIRECTAS:
  ⚠️ INTERACCIÓN DETECTADA entre 'Acenocumarol' (SINTROM®) e 'Ibuprofeno' (IBUPIRAC):
     Detalle: [Interacción de Clase: AINEs] Las siguientes drogas potencian el efecto anticoagulante...

-------------------------------------------------------
3. CONTRAINDICACIONES Y PRECAUCIONES POR SUSTANCIA:
  💊 Principio: Acenocumarol (en SINTROM®)
     Acción Terapéutica: Anticoagulante oral cumarínico...
```

---

### 3. Regenerar el Grafo de Conocimiento y Dataset

Si se actualizan las monografías o la taxonomía de clases:

```bash
# 1. Reconstruir Grafo SQLite y JSON con las 19.087 interacciones
python3 src/graph/build_vademecum_graph.py

# 2. Regenerar Dataset de Fine-Tuning para LLMs
python3 src/dataset/generate_finetune_dataset.py
```

---

## 📊 Entidades del Grafo (`vademecum_graph.db`)

| Tabla / Entidad | Descripción | Registros |
| :--- | :--- | :---: |
| `productos` | Medicamentos comerciales con laboratorio, composición, indicaciones y presentación. | 8.349 |
| `sustancias` | Principios activos, acción terapéutica, interacciones, contraindicaciones y precauciones. | 2.647 |
| `laboratorios` | Información de contacto y catálogo de laboratorios farmacéuticos. | 296 |
| `producto_sustancia` | Relación M:N entre medicamentos comerciales y sus principios activos. | 11.135 |
| `producto_patologia` | Relación M:N entre medicamentos y patologías/indicaciones clínicas. | 12.900 |
| `sustancia_interaccion` | Relaciones explícitas y propagadas de interacción fármaco-fármaco con detalle clínico. | **19.087** |

---

## 📜 Bitácora Histórica de Desarrollo

Para consultar el registro cronológico detallado de todos los hitos de ingeniería, scraping, reestructuración modular y enriquecimiento semántico del proyecto, consulta la [**BITACORA.md**](file:///home/augusto/Desktop/Vademecum/BITACORA.md).
