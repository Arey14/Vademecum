# 💊 Vademecum: Grafo de Conocimiento Farmacológico & Dataset LLM

Pipeline integral de extracción (Scraping), normalización (ETL), construcción de **Grafo de Conocimiento Farmacológico** (NetworkX + SQLite) y generación de **Datasets de Fine-Tuning** (ShareGPT/JSONL) para modelos de lenguaje especializados en farmacología clínica.

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
│  • Relaciones: 28.570               │     │  • 1.500 pares conversacionales     │
│  • Interacciones directas: 4.583    │     │  • Formato ShareGPT / ChatML        │
└──────────────────┬──────────────────┘     └──────────────────┬──────────────────┘
                   │                                           │
                   ▼                                           ▼
┌─────────────────────────────────────┐     ┌─────────────────────────────────────┐
│ Verificador Determinístico          │     │  Modelo Fine-Tuned                  │
│ (check_interactions.py)             │ ◄─► │  (Llama-3 / Qwen-2.5 / LoRA)        │
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
│   ├── vademecum_graph.db               # Base SQLite indexada del Grafo
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
│   │   └── build_vademecum_graph.py     # Generador de vademecum_graph.json y .db
│   │
│   ├── dataset/                         # 4. Generación de Dataset para LLMs
│   │   └── generate_finetune_dataset.py # Creador de pares de diálogo para entrenamiento
│   │
│   └── tools/                           # 5. Herramientas CLI y Evaluación
│       └── check_interactions.py        # Motor de consulta y evaluación clínica
│
├── check_interactions.py                # Wrapper en raíz para ejecución directa
├── requirements.txt                     # Dependencias del entorno
├── .gitignore                           # Exclusiones de Git
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

### 1. Consultar Interacciones entre Medicamentos (CLI)

Puedes evaluar cualquier combinación de medicamentos comerciales utilizando el script en la raíz:

```bash
python3 check_interactions.py "3TC" "3-TC/AZT ELEA"
```

**Ejemplo de salida:**
```text
=======================================================
      INFORME DE EVALUACIÓN DE INTERACCIONES
=======================================================

📋 MEDICAMENTOS ANALIZADOS:
  • 3TC (Lab: GSK BIOPHARMA)
    Principios Activos: Lamivudina
  • 3-TC/AZT ELEA (Lab: ELEA)
    Principios Activos: Lamivudina, Zidovudina

-------------------------------------------------------
1. RIESGO DE DUPLICACIÓN DE PRINCIPIOS ACTIVOS:
  🚨 ALERTA DE SOBREDOSIS/DUPLICIDAD: El principio 'Lamivudina' está presente en múltiples medicamentos: 3TC, 3-TC/AZT ELEA

-------------------------------------------------------
2. INTERACCIONES FARMACOLÓGICAS DIRECTAS:
  ✅ No se registraron interacciones cruzadas directas conocidas entre los principios activos.

-------------------------------------------------------
3. CONTRAINDICACIONES Y PRECAUCIONES POR SUSTANCIA:
  💊 Principio: Lamivudina (en 3TC, 3-TC/AZT ELEA)
     Acción Terapéutica: Antiviral.
     Contraindicaciones: Hipersensibilidad a la lamivudina...
```

---

### 2. Regenerar el Grafo de Conocimiento

Si actualizas los datos en `Final/`, reconstruye el grafo y la base indexada:

```bash
python3 src/graph/build_vademecum_graph.py
```

---

### 3. Regenerar el Dataset de Fine-Tuning para LLMs

Para generar un nuevo lote de entrenamiento en formato JSONL:

```bash
python3 src/dataset/generate_finetune_dataset.py
```

---

## 📊 Entidades del Grafo (`vademecum_graph.db`)

| Tabla / Entidad | Descripción |
| :--- | :--- |
| `productos` | Medicamentos comerciales con laboratorio, composición, indicaciones y presentación. |
| `sustancias` | Principios activos, acción terapéutica, interacciones, contraindicaciones y precauciones. |
| `laboratorios` | Información de contacto y catálogo de laboratorios farmacéuticos. |
| `producto_sustancia` | Relación M:N entre medicamentos comerciales y sus principios activos. |
| `producto_patologia` | Relación M:N entre medicamentos y patologías/indicaciones clínicas. |
| `sustancia_interaccion` | Relaciones explícitas de interacción fármaco-fármaco con detalle clínico. |

---

## 🔒 Integridad de Datos

Todos los datos procesados y definitivos se encuentran versionados en la carpeta `Final/` y no deben ser modificados directamente por scripts intermedios de extracción.
