import sqlite3
import pandas as pd
import os
from pathlib import Path

try:
    from src.config import (
        INTERMEDIATE_SUSTANCIAS_CSV,
        INTERMEDIATE_PRODUCTOS_COMPLETE_CSV,
        INTERMEDIATE_LABORATORIOS_CSV,
        INTERMEDIATE_SQLITE_DB
    )
    SUSTANCIAS_CSV = str(INTERMEDIATE_SUSTANCIAS_CSV)
    PRODUCTOS_CSV = str(INTERMEDIATE_PRODUCTOS_COMPLETE_CSV)
    LABORATORIOS_CSV = str(INTERMEDIATE_LABORATORIOS_CSV)
    DB_PATH = str(INTERMEDIATE_SQLITE_DB)
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "intermediate"
    SUSTANCIAS_CSV = str(BASE_DIR / "vademecum_sustancias.csv")
    PRODUCTOS_CSV = str(BASE_DIR / "vademecum_productos_complete.csv")
    LABORATORIOS_CSV = str(BASE_DIR / "vademecum_laboratorios.csv")
    DB_PATH = str(BASE_DIR / "vademecum.db")

def migrate():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    sustancias = pd.read_csv(SUSTANCIAS_CSV)
    productos = pd.read_csv(PRODUCTOS_CSV)
    laboratorios = pd.read_csv(LABORATORIOS_CSV)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE laboratorios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        url TEXT,
        direccion TEXT,
        ciudad TEXT,
        provincia TEXT,
        telefono TEXT,
        productos TEXT
    )
    """)

    c.execute("""
    CREATE TABLE sustancias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT,
        url TEXT,
        accion_therapeutica TEXT,
        propiedades TEXT,
        indicaciones TEXT,
        dosificacion TEXT,
        reacciones_adversas TEXT,
        precauciones TEXT,
        interacciones TEXT,
        contraindicaciones TEXT,
        sobredosificacion TEXT,
        medicamentos TEXT
    )
    """)

    c.execute("""
    CREATE TABLE productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT,
        nombre_producto TEXT,
        nombre_laboratorio TEXT,
        laboratorio_id INTEGER,
        descripcion TEXT,
        composicion TEXT,
        indicaciones TEXT,
        presentacion TEXT,
        principios_activos TEXT,
        patologias TEXT,
        error TEXT,
        FOREIGN KEY (laboratorio_id) REFERENCES laboratorios(id)
    )
    """)

    c.execute("""
    CREATE TABLE productos_sustancias (
        producto_id INTEGER,
        sustancia_id INTEGER,
        PRIMARY KEY (producto_id, sustancia_id),
        FOREIGN KEY (producto_id) REFERENCES productos(id),
        FOREIGN KEY (sustancia_id) REFERENCES sustancias(id)
    )
    """)

    conn.commit()

    # Insert laboratorios
    lab_name_to_id = {}
    for _, row in laboratorios.iterrows():
        c.execute("""
        INSERT INTO laboratorios (nombre, url, direccion, ciudad, provincia, telefono, productos)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (row["nombre"], row.get("url", ""), row.get("direccion", ""),
              row.get("ciudad", ""), row.get("provincia", ""), row.get("telefono", ""),
              row.get("productos", "")))
        lab_name_to_id[row["nombre"]] = c.lastrowid

    # Insert sustancias
    sust_name_to_id = {}
    for _, row in sustancias.iterrows():
        c.execute("""
        INSERT INTO sustancias (nombre, url, accion_therapeutica, propiedades, indicaciones,
                               dosificacion, reacciones_adversas, precauciones, interacciones,
                               contraindicaciones, sobredosificacion, medicamentos)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (row["nombre"], row.get("url", ""), row.get("accion_therapeutica", ""),
              row.get("propiedades", ""), row.get("indicaciones", ""),
              row.get("dosificacion", ""), row.get("reacciones_adversas", ""),
              row.get("precauciones", ""), row.get("interacciones", ""),
              row.get("contraindicaciones", ""), row.get("sobredosificacion", ""),
              row.get("medicamentos", "")))
        sust_name_to_id[row["nombre"]] = c.lastrowid

    # Insert productos and build pivot
    for _, row in productos.iterrows():
        lab_id = lab_name_to_id.get(row["nombre_laboratorio"])
        
        c.execute("""
        INSERT INTO productos (url, nombre_producto, nombre_laboratorio, laboratorio_id,
                              descripcion, composicion, indicaciones, presentacion,
                              principios_activos, patologias, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (row.get("url", ""), row["nombre_producto"], row["nombre_laboratorio"], lab_id,
              row.get("descripcion", ""), row.get("composicion", ""),
              row.get("indicaciones", ""), row.get("presentacion", ""),
              row["principios_activos"], row.get("patologias", ""), row.get("error", "")))
        
        prod_id = c.lastrowid
        
        sustancias_text = str(row["principios_activos"])
        if sustancias_text and sustancias_text != "nan":
            for sust_name in sustancias_text.split(";"):
                sust_name = sust_name.strip()
                if sust_name in sust_name_to_id:
                    c.execute("""
                    INSERT INTO productos_sustancias (producto_id, sustancia_id)
                    VALUES (?, ?)
                    """, (prod_id, sust_name_to_id[sust_name]))

    conn.commit()

    c.execute("SELECT COUNT(*) FROM laboratorios")
    print(f"Laboratorios: {c.fetchone()[0]}")

    c.execute("SELECT COUNT(*) FROM sustancias")
    print(f"Sustancias: {c.fetchone()[0]}")

    c.execute("SELECT COUNT(*) FROM productos")
    print(f"Productos: {c.fetchone()[0]}")

    c.execute("SELECT COUNT(*) FROM productos_sustancias")
    print(f"Relaciones producto-sustancia: {c.fetchone()[0]}")

    c.execute("PRAGMA foreign_key_check")
    errors = c.fetchall()
    if errors:
        print(f"Foreign key errors: {errors}")
    else:
        print("FK integrity: OK")

    conn.close()
    print(f"\nDatabase created: {DB_PATH}")

if __name__ == "__main__":
    migrate()