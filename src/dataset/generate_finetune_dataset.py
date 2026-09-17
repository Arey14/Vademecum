#!/usr/bin/env python3
import json
import sqlite3
import random
import os
from pathlib import Path

try:
    from src.config import FINETUNE_JSONL_PATH, GRAPH_DB_PATH
    from src.tools.check_interactions import evaluate_combination, get_connection
    DEFAULT_OUTPUT_JSONL = str(FINETUNE_JSONL_PATH)
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent / "Final"
    DEFAULT_OUTPUT_JSONL = str(BASE_DIR / "vademecum_finetune_train.jsonl")
    from ..tools.check_interactions import evaluate_combination, get_connection

OUTPUT_JSONL = os.environ.get("VADEMECUM_FINETUNE_JSONL", DEFAULT_OUTPUT_JSONL)
SYSTEM_PROMPT = "Eres un asistente farmacológico experto especializado en evaluar interacciones medicamentosas, duplicación de principios activos, contraindicaciones y precauciones clínicas en medicamentos."

def format_sharegpt(user_text, assistant_text):
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text}
        ]
    }

def generate_dataset(output_path=OUTPUT_JSONL):
    conn = get_connection()
    cur = conn.cursor()
    
    # 1. Fetch products with active ingredients
    cur.execute('''
    SELECT p.nombre_producto, p.laboratorio_nombre, p.descripcion, GROUP_CONCAT(ps.sustancia_name, '; ')
    FROM productos p
    JOIN producto_sustancia ps ON p.nombre_producto = ps.producto_name
    GROUP BY p.nombre_producto
    HAVING COUNT(ps.sustancia_name) >= 1
    ''')
    products_with_ingredients = cur.fetchall()
    
    # 2. Fetch substances with details
    cur.execute('''
    SELECT nombre, accion_therapeutica, reacciones_adversas, precauciones, interacciones, contraindicaciones
    FROM sustancias
    WHERE (interacciones IS NOT NULL AND interacciones != '')
       OR (contraindicaciones IS NOT NULL AND contraindicaciones != '')
    ''')
    substances_detailed = cur.fetchall()
    
    print(f"Found {len(products_with_ingredients)} products and {len(substances_detailed)} detailed substances for synthetic dataset generation.")
    
    dataset = []
    
    # Category 1: Drug Interaction & Combination Assessment Pairs (Pairs of medications)
    print("Generating Drug Combination QA Pairs...")
    random.seed(42)
    sample_products = random.sample(products_with_ingredients, min(1000, len(products_with_ingredients)))
    
    for i in range(0, len(sample_products) - 1, 2):
        p1 = sample_products[i][0]
        p2 = sample_products[i+1][0]
        
        eval_res = evaluate_combination([p1, p2])
        if eval_res['status'] != 'success':
            continue
            
        user_queries = [
            f"¿Es seguro tomar {p1} junto con {p2}?",
            f"¿Existe alguna contraindicación o interacción al combinar {p1} y {p2}?",
            f"Un paciente consulta si puede administrar simultáneamente {p1} de laboratorio {sample_products[i][1]} y {p2}."
        ]
        user_query = random.choice(user_queries)
        
        # Build Assistant response
        ans_lines = [f"Evaluación farmacológica para la combinación de **{p1}** y **{p2}**:\n"]
        
        ans_lines.append("### 1. Principios Activos Involucrados:")
        for fp in eval_res['found_products']:
            ans_lines.append(f"- **{fp['nombre']}** ({fp['laboratorio'] or 'Laboratorio N/A'}): {', '.join(fp['principios_activos'])}")
            
        ans_lines.append("\n### 2. Evaluación de Duplicidad:")
        if eval_res['duplications']:
            for dup in eval_res['duplications']:
                ans_lines.append(f"⚠️ **Alerta de Duplicidad**: El principio activo **{dup['name']}** está presente en ambos medicamentos ({', '.join(dup['products'])}). Administrarlos juntos puede causar riesgo de sobredosis.")
        else:
            ans_lines.append("✅ No se observan duplicaciones de principios activos entre ambos medicamentos.")
            
        ans_lines.append("\n### 3. Interacciones Directas:")
        if eval_res['interactions']:
            for inter in eval_res['interactions']:
                ans_lines.append(f"⚠️ **Interacción entre {inter['sustancia_1']} y {inter['sustancia_2']}**:\n{inter['detalle']}")
        else:
            ans_lines.append("✅ No se registraron interacciones cruzadas directas registradas entre sus componentes.")
            
        ans_lines.append("\n### 4. Precauciones y Contraindicaciones:")
        for ing in eval_res['ingredient_details']:
            if ing['contraindicaciones']:
                ans_lines.append(f"- **{ing['nombre']}**: Contraindicado en {ing['contraindicaciones'][:200]}...")
                
        assistant_resp = "\n".join(ans_lines)
        dataset.append(format_sharegpt(user_query, assistant_resp))
        
    # Category 2: Individual Drug Safety & Indications Pairs
    print("Generating Individual Product QA Pairs...")
    for prod in sample_products[:500]:
        p_name, lab, desc, ing_str = prod
        user_queries = [
            f"¿Para qué está indicado el medicamento {p_name} y cuáles son sus principios activos?",
            f"Dame la ficha de seguridad y componentes de {p_name}."
        ]
        user_query = random.choice(user_queries)
        
        resp = f"El medicamento **{p_name}**"
        if lab:
            resp += f" (desarrollado por {lab})"
        resp += f" contiene los siguientes principios activos: **{ing_str}**.\n\n"
        if desc:
            resp += f"**Descripción/Indicaciones**: {desc}\n\n"
            
        # Get details for ingredients
        ings = [x.strip() for x in ing_str.split(';')]
        for ing in ings:
            cur.execute("SELECT accion_therapeutica, contraindicaciones, precauciones FROM sustancias WHERE LOWER(nombre) = LOWER(?)", (ing,))
            s_row = cur.fetchone()
            if s_row:
                acc, contra, prec = s_row
                if acc:
                    resp += f"- **{ing}** (Acción Terapéutica): {acc}\n"
                if contra:
                    resp += f"  - *Contraindicaciones*: {contra[:180]}...\n"
                    
        dataset.append(format_sharegpt(user_query, resp))
        
    # Category 3: Substance Level Interactions & Warnings Pairs
    print("Generating Substance Interaction QA Pairs...")
    for sust in substances_detailed[:500]:
        s_name, acc, reac, prec, inter, contra = sust
        user_query = f"¿Cuáles son las interacciones, advertencias y contraindicaciones de la sustancia {s_name}?"
        
        resp_lines = [f"Información farmacológica de la sustancia **{s_name}**:\n"]
        if acc:
            resp_lines.append(f"• **Acción Terapéutica**: {acc}")
        if inter:
            resp_lines.append(f"• **Interacciones**: {inter}")
        if contra:
            resp_lines.append(f"• **Contraindicaciones**: {contra}")
        if prec:
            resp_lines.append(f"• **Precauciones**: {prec}")
        if reac:
            resp_lines.append(f"• **Reacciones Adversas**: {reac[:250]}...")
            
        dataset.append(format_sharegpt(user_query, "\n".join(resp_lines)))
        
    conn.close()
    
    # Save dataset to JSONL
    print(f"Total training pairs generated: {len(dataset)}")
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
            
    print(f"Saved Fine-Tuning dataset to {output_path}")

if __name__ == "__main__":
    generate_dataset()
