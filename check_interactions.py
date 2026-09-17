#!/usr/bin/env python3
"""
Wrapper para ejecución directa de check_interactions desde la raíz del proyecto.
"""
import sys
from pathlib import Path

# Agregar raíz y src al path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from src.tools.check_interactions import main

if __name__ == "__main__":
    main()
