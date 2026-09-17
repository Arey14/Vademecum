import os
from pathlib import Path

# Base directories
SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
FINAL_DIR = PROJECT_ROOT / "Final"
DATA_DIR = PROJECT_ROOT / "data"
DATA_INTERMEDIATE_DIR = DATA_DIR / "intermediate"
LOGS_DIR = PROJECT_ROOT / "logs"

# Ensure runtime directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DATA_INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)

# Final Golden Datasets & Artifacts
GRAPH_DB_PATH = FINAL_DIR / "vademecum_graph.db"
GRAPH_JSON_PATH = FINAL_DIR / "vademecum_graph.json"
FINETUNE_JSONL_PATH = FINAL_DIR / "vademecum_finetune_train.jsonl"
FINAL_PRODUCTOS_CSV = FINAL_DIR / "vademecum_productos.csv"
FINAL_LABORATORIOS_CSV = FINAL_DIR / "vademecum_laboratorios.csv"
FINAL_SUSTANCIAS_CSV = FINAL_DIR / "vademecum_sustancias.csv"

# Intermediate Datasets
INTERMEDIATE_PRODUCTOS_COMPLETE_CSV = DATA_INTERMEDIATE_DIR / "vademecum_productos_complete.csv"
INTERMEDIATE_LABORATORIOS_CSV = DATA_INTERMEDIATE_DIR / "vademecum_laboratorios.csv"
INTERMEDIATE_SUSTANCIAS_CSV = DATA_INTERMEDIATE_DIR / "vademecum_sustancias.csv"
INTERMEDIATE_LISTA_PRODUCTOS_CSV = DATA_INTERMEDIATE_DIR / "Lista_productos.csv"
INTERMEDIATE_SQLITE_DB = DATA_INTERMEDIATE_DIR / "vademecum.db"
