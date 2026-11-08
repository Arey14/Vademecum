#!/usr/bin/env python3
import sys
import sqlite3
import json
import os
import argparse
from pathlib import Path

from src.graph.producto_ref import es_producto_ref
from src.tools.buscador import AMBIGUO, NO_ENCONTRADO, buscar_medicamento

try:
    from src.config import GRAPH_DB_PATH
    DEFAULT_DB_PATH = str(GRAPH_DB_PATH)
except ImportError:
    # Fallback to relative resolution
    DEFAULT_DB_PATH = str(Path(__file__).resolve().parent.parent.parent / "Final" / "vademecum_graph.db")

DB_PATH = os.environ.get("VADEMECUM_GRAPH_DB", DEFAULT_DB_PATH)

def get_connection(db_path=None):
    target_path = db_path or DB_PATH
    if not os.path.exists(target_path):
        raise FileNotFoundError(f"Database not found at {target_path}. Run build_vademecum_graph.py first.")
    return sqlite3.connect(target_path)

_COLS_PRODUCTO = "producto_ref, nombre_producto, laboratorio_nombre, descripcion, indicaciones"


def _fila_a_producto(row):
    return {'producto_ref': row[0], 'nombre': row[1], 'laboratorio': row[2],
            'descripcion': row[3], 'indicaciones': row[4]}


def find_product_by_ref(cur, ref):
    """Búsqueda exacta por identificador estable (sin ambigüedad)."""
    cur.execute(f"SELECT {_COLS_PRODUCTO} FROM productos WHERE producto_ref = ?", (ref.strip().lower(),))
    row = cur.fetchone()
    return _fila_a_producto(row) if row else None


def find_product(cur, name):
    """Búsqueda EXACTA por producto_ref (ej. 'pv-3989') o por nombre exacto.

    Ya no hace coincidencia parcial: eso devolvía productos cualquiera (H-05). Para texto
    libre usar `src.tools.buscador.buscar_medicamento`, que devuelve candidatos con puntaje.
    """
    if es_producto_ref(name):
        return find_product_by_ref(cur, name)
    cur.execute(f"SELECT {_COLS_PRODUCTO} FROM productos WHERE LOWER(nombre_producto) = LOWER(?) "
                "ORDER BY producto_ref LIMIT 1", (name,))
    row = cur.fetchone()
    return _fila_a_producto(row) if row else None


def get_product_ingredients(cur, producto_ref):
    cur.execute("SELECT sustancia_name FROM producto_sustancia WHERE producto_ref = ?", (producto_ref,))
    rows = cur.fetchall()
    return [r[0] for r in rows]

def get_sustancia_details(cur, sust_name):
    cur.execute('''SELECT nombre, accion_therapeutica, reacciones_adversas, precauciones, interacciones, contraindicaciones 
                   FROM sustancias WHERE LOWER(nombre) = LOWER(?)''', (sust_name,))
    row = cur.fetchone()
    if row:
        return {
            'nombre': row[0],
            'accion_therapeutica': row[1],
            'reacciones_adversas': row[2],
            'precauciones': row[3],
            'interacciones': row[4],
            'contraindicaciones': row[5]
        }
    return None

def check_direct_interaction(cur, sust1, sust2):
    cur.execute('''SELECT detalle FROM sustancia_interaccion 
                   WHERE (LOWER(sustancia_origen) = LOWER(?) AND LOWER(sustancia_destino) = LOWER(?))
                      OR (LOWER(sustancia_origen) = LOWER(?) AND LOWER(sustancia_destino) = LOWER(?))''',
                (sust1, sust2, sust2, sust1))
    row = cur.fetchone()
    return row[0] if row else None

def evaluate_combination(med_names, db_path=None):
    conn = get_connection(db_path)
    cur = conn.cursor()
    
    found_products = []
    missing_products = []
    ambiguous = []   # entradas que requieren que el usuario elija
    avisos = []      # decisiones tomadas sin preguntar (empates con la misma composición)

    ruta = db_path or DB_PATH
    for med in med_names:
        res = buscar_medicamento(med, k=5, db_path=ruta)
        if res.estado == NO_ENCONTRADO:
            missing_products.append(med)
            continue
        elegido = res.candidato_para_analisis
        if elegido is None:
            ambiguous.append(res)
            continue
        if res.estado == AMBIGUO:
            avisos.append(f"'{med}' coincide con {res.n_empatados} candidatos con la misma composición; "
                          f"se usó {elegido.nombre}. Para especificar, usar el código (ej. {elegido.ref}).")
        if elegido.tipo == 'producto':
            p = find_product_by_ref(cur, elegido.ref)
            p['tipo'] = 'producto'
            p['principios_activos'] = get_product_ingredients(cur, p['producto_ref'])
        else:  # sustancia ingresada directamente (ej. "ibuprofeno")
            p = {'producto_ref': f"sust:{elegido.nombre}", 'nombre': elegido.nombre, 'laboratorio': None,
                 'descripcion': None, 'indicaciones': None, 'tipo': 'sustancia',
                 'principios_activos': [elegido.nombre]}
        found_products.append(p)

    if ambiguous:
        conn.close()
        return {
            'status': 'ambiguous',
            'message': "Hay medicamentos ambiguos: elegir uno de los candidatos y repetir la consulta. "
                       "No se hizo ningún análisis parcial.",
            'ambiguous': [r.to_dict() for r in ambiguous],
            'missing': missing_products,
        }

    if not found_products:
        conn.close()
        return {
            'status': 'error',
            'message': f"No se encontraron medicamentos coincidentes para: {', '.join(med_names)}",
            'missing': missing_products
        }
        
    # Analyze ingredient overlaps
    ingredient_map = {} # ingredient -> list of product names
    for p in found_products:
        for ing in p['principios_activos']:
            ing_lower = ing.lower()
            if ing_lower not in ingredient_map:
                ingredient_map[ing_lower] = {'name': ing, 'products': []}
            ingredient_map[ing_lower]['products'].append(p['nombre'])
            
    duplications = [data for ing_lower, data in ingredient_map.items() if len(data['products']) > 1]
    
    # Analyze direct interactions between distinct active ingredients
    distinct_ingredients = list(ingredient_map.keys())
    detected_interactions = []
    
    for i in range(len(distinct_ingredients)):
        for j in range(i + 1, len(distinct_ingredients)):
            ing1 = ingredient_map[distinct_ingredients[i]]['name']
            ing2 = ingredient_map[distinct_ingredients[j]]['name']
            
            inter_detail = check_direct_interaction(cur, ing1, ing2)
            if inter_detail:
                prods1 = ingredient_map[distinct_ingredients[i]]['products']
                prods2 = ingredient_map[distinct_ingredients[j]]['products']
                detected_interactions.append({
                    'sustancia_1': ing1,
                    'productos_1': prods1,
                    'sustancia_2': ing2,
                    'productos_2': prods2,
                    'detalle': inter_detail
                })
                
    # Gather general warnings for all ingredients
    ingredient_details = []
    for ing_lower, data in ingredient_map.items():
        details = get_sustancia_details(cur, data['name'])
        if details:
            details['used_in'] = data['products']
            ingredient_details.append(details)
            
    conn.close()
    
    return {
        'status': 'success',
        'found_products': found_products,
        'missing_products': missing_products,
        'avisos': avisos,
        'duplications': duplications,
        'interactions': detected_interactions,
        'ingredient_details': ingredient_details
    }

def print_report(res):
    if res['status'] == 'error':
        print(f"❌ ERROR: {res['message']}")
        return
    if res['status'] == 'ambiguous':
        print(f"❓ {res['message']}\n")
        for amb in res['ambiguous']:
            print(f"  Para '{amb['consulta']}': {amb['mensaje']}")
            for c in amb['candidatos']:
                lab = f" ({c['laboratorio']})" if c['laboratorio'] else ""
                print(f"    - {c['nombre']}{lab}  [{c['tipo']}, código {c['ref']}, coincidencia {c['motivo']}]")
        if res['missing']:
            print(f"  ⚠️ No encontrados: {', '.join(res['missing'])}")
        return
        
    print("\n=======================================================")
    print("      INFORME DE EVALUACIÓN DE INTERACCIONES")
    print("=======================================================\n")
    
    print("📋 MEDICAMENTOS ANALIZADOS:")
    for p in res['found_products']:
        print(f"  • {p['nombre']} (Lab: {p['laboratorio'] or 'N/A'})")
        print(f"    Principios Activos: {', '.join(p['principios_activos']) if p['principios_activos'] else 'No especificados'}")
    if res['missing_products']:
        print(f"  ⚠️ No encontrados: {', '.join(res['missing_products'])}")
    for aviso in res.get('avisos', []):
        print(f"  ℹ️ {aviso}")
        
    print("\n-------------------------------------------------------")
    print("1. RIESGO DE DUPLICACIÓN DE PRINCIPIOS ACTIVOS:")
    if res['duplications']:
        for dup in res['duplications']:
            print(f"  🚨 ALERTA DE SOBREDOSIS/DUPLICIDAD: El principio '{dup['name']}' está presente en múltiples medicamentos: {', '.join(dup['products'])}")
    else:
        print("  ✅ Sin duplicaciones de principios activos detectadas.")
        
    print("\n-------------------------------------------------------")
    print("2. INTERACCIONES FARMACOLÓGICAS DIRECTAS:")
    if res['interactions']:
        for inter in res['interactions']:
            print(f"  ⚠️ INTERACCIÓN DETECTADA entre '{inter['sustancia_1']}' ({', '.join(inter['productos_1'])}) y '{inter['sustancia_2']}' ({', '.join(inter['productos_2'])}):")
            print(f"     Detalle: {inter['detalle']}\n")
    else:
        print("  ✅ No se registraron interacciones cruzadas directas conocidas entre los principios activos.")

    print("\n-------------------------------------------------------")
    print("3. CONTRAINDICACIONES Y PRECAUCIONES POR SUSTANCIA:")
    for ing in res['ingredient_details']:
        print(f"\n  💊 Principio: {ing['nombre']} (en {', '.join(ing['used_in'])})")
        if ing['accion_therapeutica']:
            print(f"     Acción Terapéutica: {ing['accion_therapeutica']}")
        if ing['contraindicaciones']:
            print(f"     Contraindicaciones: {ing['contraindicaciones'][:250]}...")
        if ing['precauciones']:
            print(f"     Precauciones: {ing['precauciones'][:250]}...")

    print("\n=======================================================\n")

def main():
    # En consolas de Windows (cp1252) los emojis del informe rompen la impresión.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="Verificador de Interacciones entre Medicamentos")
    parser.add_argument('medicamentos', nargs='+', help="Lista de nombres de medicamentos a evaluar")
    parser.add_argument('--db', default=None, help="Ruta personalizada a vademecum_graph.db")
    args = parser.parse_args()
    
    res = evaluate_combination(args.medicamentos, db_path=args.db)
    print_report(res)

if __name__ == "__main__":
    main()
