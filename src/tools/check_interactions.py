#!/usr/bin/env python3
import sys
import sqlite3
import json
import os
import argparse
from pathlib import Path

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

def find_product(cur, name):
    cur.execute("SELECT nombre_producto, laboratorio_nombre, descripcion, indicaciones FROM productos WHERE LOWER(nombre_producto) = LOWER(?)", (name,))
    row = cur.fetchone()
    if row:
        return {'nombre': row[0], 'laboratorio': row[1], 'descripcion': row[2], 'indicaciones': row[3]}
        
    # Search like
    cur.execute("SELECT nombre_producto, laboratorio_nombre, descripcion, indicaciones FROM productos WHERE LOWER(nombre_producto) LIKE LOWER(?) LIMIT 1", (f"%{name}%",))
    row = cur.fetchone()
    if row:
        return {'nombre': row[0], 'laboratorio': row[1], 'descripcion': row[2], 'indicaciones': row[3]}
    return None

def get_product_ingredients(cur, prod_name):
    cur.execute("SELECT sustancia_name FROM producto_sustancia WHERE LOWER(producto_name) = LOWER(?)", (prod_name,))
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
    
    for med in med_names:
        p = find_product(cur, med)
        if p:
            ingredients = get_product_ingredients(cur, p['nombre'])
            p['principios_activos'] = ingredients
            found_products.append(p)
        else:
            missing_products.append(med)
            
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
        'duplications': duplications,
        'interactions': detected_interactions,
        'ingredient_details': ingredient_details
    }

def print_report(res):
    if res['status'] == 'error':
        print(f"❌ ERROR: {res['message']}")
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
    parser = argparse.ArgumentParser(description="Verificador de Interacciones entre Medicamentos")
    parser.add_argument('medicamentos', nargs='+', help="Lista de nombres de medicamentos a evaluar")
    parser.add_argument('--db', default=None, help="Ruta personalizada a vademecum_graph.db")
    args = parser.parse_args()
    
    res = evaluate_combination(args.medicamentos, db_path=args.db)
    print_report(res)

if __name__ == "__main__":
    main()
