#!/usr/bin/env python3
import csv
import json
import sqlite3
import re
import os
import sys
from pathlib import Path
import networkx as nx

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from src.config import (
        FINAL_DIR,
        FINAL_PRODUCTOS_CSV,
        FINAL_LABORATORIOS_CSV,
        FINAL_SUSTANCIAS_CSV,
        GRAPH_JSON_PATH,
        GRAPH_DB_PATH
    )
    PRODUCTOS_CSV = str(FINAL_PRODUCTOS_CSV)
    LABORATORIOS_CSV = str(FINAL_LABORATORIOS_CSV)
    SUSTANCIAS_CSV = str(FINAL_SUSTANCIAS_CSV)
    OUTPUT_GRAPH_JSON = str(GRAPH_JSON_PATH)
    OUTPUT_SQLITE_DB = str(GRAPH_DB_PATH)
except ImportError:
    BASE_DIR = PROJECT_ROOT / "Final"
    PRODUCTOS_CSV = str(BASE_DIR / 'vademecum_productos.csv')
    LABORATORIOS_CSV = str(BASE_DIR / 'vademecum_laboratorios.csv')
    SUSTANCIAS_CSV = str(BASE_DIR / 'vademecum_sustancias.csv')
    OUTPUT_GRAPH_JSON = str(BASE_DIR / 'vademecum_graph.json')
    OUTPUT_SQLITE_DB = str(BASE_DIR / 'vademecum_graph.db')

from src.graph.pharmacological_classes import SUBSTANCE_ALIASES, PHARMACOLOGICAL_CLASSES

def clean_str(val):
    return val.strip() if val else ""

def split_items(val, delimiter=';'):
    if not val:
        return []
    items = [x.strip() for x in val.split(delimiter) if x.strip()]
    return list(dict.fromkeys(items))

def build_graph_and_db():
    print("Loading CSV datasets...")
    
    # 1. Load Laboratorios
    laboratorios = {}
    with open(LABORATORIOS_CSV, 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            name = clean_str(r.get('nombre'))
            if name:
                laboratorios[name] = r
                
    # 2. Load Sustancias
    sustancias = {}
    with open(SUSTANCIAS_CSV, 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            name = clean_str(r.get('nombre'))
            if name:
                sustancias[name] = r
                
    # 3. Load Productos
    productos = []
    with open(PRODUCTOS_CSV, 'r', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            productos.append(r)
            
    print(f"Loaded: {len(laboratorios)} laboratorios, {len(sustancias)} sustancias, {len(productos)} productos.")
    
    G = nx.DiGraph()
    
    # Add Laboratorio Nodes
    for lab_name, data in laboratorios.items():
        G.add_node(f"Lab:{lab_name}", type="Laboratorio", name=lab_name, **data)
        
    # Canonical substance name lookup (lowercase -> original)
    sustancia_names_lower = {name.lower(): name for name in sustancias.keys() if len(name) > 3}
    
    # Auto-generate inverted aliases for acids: e.g. "Acetilsalicílico ácido" -> "ácido acetilsalicílico", "acido acetilsalicilico"
    for name in list(sustancias.keys()):
        parts = name.split()
        if len(parts) >= 2 and parts[-1].lower() in ('ácido', 'acido'):
            base = " ".join(parts[:-1])
            sustancia_names_lower[f"ácido {base.lower()}"] = name
            sustancia_names_lower[f"acido {base.lower()}"] = name
            sustancia_names_lower[base.lower()] = name
            
    # Register aliases in lookup
    for alias, canonical in SUBSTANCE_ALIASES.items():
        if canonical.lower() in sustancia_names_lower:
            sustancia_names_lower[alias.lower()] = sustancia_names_lower[canonical.lower()]
        elif canonical in sustancias:
            sustancia_names_lower[alias.lower()] = canonical
            
    # Add Sustancia Nodes
    for sust_name, data in sustancias.items():
        G.add_node(f"Sust:{sust_name}", type="Sustancia", name=sust_name, **data)
        
    # Add Product Nodes & Relationships
    for prod in productos:
        prod_name = clean_str(prod.get('nombre_producto'))
        if not prod_name:
            continue
            
        prod_id = f"Prod:{prod_name}"
        G.add_node(prod_id, type="Producto", **prod)
        
        # Link to Laboratorio
        lab = clean_str(prod.get('nombre_laboratorio'))
        if lab and f"Lab:{lab}" in G:
            G.add_edge(prod_id, f"Lab:{lab}", relation="FABRICADO_POR")
            
        # Link to Principios Activos
        principios = split_items(prod.get('principios_activos'))
        for p in principios:
            target_sust = p
            p_lower = p.lower()
            if p_lower in sustancia_names_lower:
                target_sust = sustancia_names_lower[p_lower]
                
            sust_node = f"Sust:{target_sust}"
            if sust_node not in G:
                G.add_node(sust_node, type="Sustancia", name=target_sust)
            G.add_edge(prod_id, sust_node, relation="CONTIENE_PRINCIPIO")
            
        # Link to Patologias
        patologias = split_items(prod.get('patologias'))
        for pat in patologias:
            pat_node = f"Pat:{pat}"
            if pat_node not in G:
                G.add_node(pat_node, type="Patologia", name=pat)
            G.add_edge(prod_id, pat_node, relation="INDICADO_PARA")

    print("\n--- Starting Enhanced Interaction Extraction ---")
    
    # 1. Compile regex for Direct Substance Matching
    sorted_terms = sorted(list(sustancia_names_lower.keys()), key=len, reverse=True)
    pattern_str = r'\b(' + '|'.join(map(re.escape, sorted_terms)) + r')\b'
    sust_regex = re.compile(pattern_str, re.IGNORECASE)
    
    # 2. Compile Class / Family Matchers and resolve Member Sets
    compiled_classes = []
    for class_name, cdata in PHARMACOLOGICAL_CLASSES.items():
        mention_rx = re.compile('|'.join(cdata['mention_patterns']), re.IGNORECASE)
        action_rx = re.compile('|'.join(cdata['action_patterns']), re.IGNORECASE) if cdata.get('action_patterns') else None
        
        # Resolve members
        resolved_members = set()
        for cm in cdata['core_members']:
            if cm.lower() in sustancia_names_lower:
                resolved_members.add(sustancia_names_lower[cm.lower()])
                
        # Auto-classify based on action_therapeutica
        if action_rx:
            for s_name, s_data in sustancias.items():
                acc = s_data.get('accion_therapeutica', '')
                if acc and action_rx.search(acc):
                    resolved_members.add(s_name)
                    
        compiled_classes.append({
            'name': class_name,
            'mention_rx': mention_rx,
            'members': list(resolved_members)
        })
        print(f"Class [{class_name}]: {len(resolved_members)} members mapped.")
        
    direct_interaction_count = 0
    class_interaction_count = 0
    contraindication_interaction_count = 0
    
    # Extraction loop over all substances
    for sust_name, data in sustancias.items():
        sust_node = f"Sust:{sust_name}"
        inter_text = data.get('interacciones', '') or ''
        contra_text = data.get('contraindicaciones', '') or ''
        prec_text = data.get('precauciones', '') or ''
        
        # A. Direct matches in 'interacciones'
        if inter_text:
            matches = sust_regex.findall(inter_text)
            for m in set(matches):
                other_orig = sustancia_names_lower.get(m.lower())
                if other_orig and other_orig != sust_name:
                    other_node = f"Sust:{other_orig}"
                    if not G.has_edge(sust_node, other_node):
                        G.add_edge(sust_node, other_node, relation="INTERACTUA_CON", detail=inter_text[:300])
                        direct_interaction_count += 1
                        
        # B. Direct matches in 'contraindicaciones' and 'precauciones' (Clinical Contraindications)
        combined_warnings = f"{contra_text} {prec_text}".strip()
        if combined_warnings:
            # Check for direct co-administration warnings
            if re.search(r'\b(concomitante|coadministra|combinaci[oó]n|administraci[oó]n\s+conjunta|asociaci[oó]n\s+con)\b', combined_warnings, re.IGNORECASE):
                matches = sust_regex.findall(combined_warnings)
                for m in set(matches):
                    other_orig = sustancia_names_lower.get(m.lower())
                    if other_orig and other_orig != sust_name:
                        other_node = f"Sust:{other_orig}"
                        if not G.has_edge(sust_node, other_node):
                            detail_txt = f"[Contraindicación Clínica / Precaución] {combined_warnings[:300]}"
                            G.add_edge(sust_node, other_node, relation="INTERACTUA_CON", detail=detail_txt)
                            contraindication_interaction_count += 1
                            
        # C. Class / Family Propagation (AINEs, Anticoagulantes, etc.)
        all_clinical_text = f"{inter_text} {contra_text}".strip()
        if all_clinical_text:
            for cls in compiled_classes:
                if cls['mention_rx'].search(all_clinical_text):
                    for member in cls['members']:
                        if member != sust_name:
                            member_node = f"Sust:{member}"
                            if not G.has_edge(sust_node, member_node):
                                detail_txt = f"[Interacción de Clase: {cls['name']}] {all_clinical_text[:280]}"
                                G.add_edge(sust_node, member_node, relation="INTERACTUA_CON", detail=detail_txt)
                                class_interaction_count += 1

    total_interactions = direct_interaction_count + contraindication_interaction_count + class_interaction_count
    print(f"\nExtracted Interacciones Summary:")
    print(f"  • Directas (Nombre explícito): {direct_interaction_count}")
    print(f"  • Contraindicaciones / Precauciones: {contraindication_interaction_count}")
    print(f"  • Propagadas por Clase / Familia: {class_interaction_count}")
    print(f"  => TOTAL DE ARISTAS DE INTERACCIÓN: {total_interactions:,}")
    print(f"Graph total nodes: {G.number_of_nodes():,}, total edges: {G.number_of_edges():,}")

    # Save Graph as JSON
    print("\nSaving Graph JSON...")
    graph_data = nx.node_link_data(G)
    with open(OUTPUT_GRAPH_JSON, 'w', encoding='utf-8') as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)
    print(f"Saved Knowledge Graph JSON to {OUTPUT_GRAPH_JSON}")

    # Build SQLite Relational Representation
    print("Building SQLite Database...")
    if os.path.exists(OUTPUT_SQLITE_DB):
        os.remove(OUTPUT_SQLITE_DB)
        
    conn = sqlite3.connect(OUTPUT_SQLITE_DB)
    cur = conn.cursor()
    
    cur.execute('''
    CREATE TABLE laboratorios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE,
        url TEXT,
        direccion TEXT,
        ciudad TEXT,
        provincia TEXT,
        telefono TEXT
    )''')
    
    cur.execute('''
    CREATE TABLE productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre_producto TEXT,
        url TEXT,
        laboratorio_nombre TEXT,
        descripcion TEXT,
        composicion TEXT,
        indicaciones TEXT,
        presentacion TEXT
    )''')
    
    cur.execute('''
    CREATE TABLE sustancias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE,
        url TEXT,
        accion_therapeutica TEXT,
        propiedades TEXT,
        indicaciones TEXT,
        dosificacion TEXT,
        reacciones_adversas TEXT,
        precauciones TEXT,
        interacciones TEXT,
        contraindicaciones TEXT
    )''')
    
    cur.execute('''
    CREATE TABLE producto_sustancia (
        producto_name TEXT,
        sustancia_name TEXT,
        PRIMARY KEY (producto_name, sustancia_name)
    )''')
    
    cur.execute('''
    CREATE TABLE producto_patologia (
        producto_name TEXT,
        patologia_name TEXT,
        PRIMARY KEY (producto_name, patologia_name)
    )''')

    cur.execute('''
    CREATE TABLE sustancia_interaccion (
        sustancia_origen TEXT,
        sustancia_destino TEXT,
        detalle TEXT,
        PRIMARY KEY (sustancia_origen, sustancia_destino)
    )''')

    # Populate SQLite tables
    for lab_name, d in laboratorios.items():
        cur.execute('INSERT OR IGNORE INTO laboratorios (nombre, url, direccion, ciudad, provincia, telefono) VALUES (?, ?, ?, ?, ?, ?)',
                    (lab_name, d.get('url'), d.get('direccion'), d.get('ciudad'), d.get('provincia'), d.get('telefono')))

    for sust_name, d in sustancias.items():
        cur.execute('''INSERT OR IGNORE INTO sustancias (nombre, url, accion_therapeutica, propiedades, indicaciones, dosificacion, reacciones_adversas, precauciones, interacciones, contraindicaciones) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (sust_name, d.get('url'), d.get('accion_therapeutica'), d.get('propiedades'), d.get('indicaciones'),
                     d.get('dosificacion'), d.get('reacciones_adversas'), d.get('precauciones'), d.get('interacciones'), d.get('contraindicaciones')))

    for prod in productos:
        prod_name = clean_str(prod.get('nombre_producto'))
        if not prod_name:
            continue
        cur.execute('''INSERT INTO productos (nombre_producto, url, laboratorio_nombre, descripcion, composicion, indicaciones, presentacion)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (prod_name, prod.get('url'), prod.get('nombre_laboratorio'), prod.get('descripcion'),
                     prod.get('composicion'), prod.get('indicaciones'), prod.get('presentacion')))
        
        principios = split_items(prod.get('principios_activos'))
        for p in principios:
            target_sust = p
            p_lower = p.lower()
            if p_lower in sustancia_names_lower:
                target_sust = sustancia_names_lower[p_lower]
            cur.execute('INSERT OR IGNORE INTO producto_sustancia VALUES (?, ?)', (prod_name, target_sust))
            
        patologias = split_items(prod.get('patologias'))
        for pat in patologias:
            cur.execute('INSERT OR IGNORE INTO producto_patologia VALUES (?, ?)', (prod_name, pat))

    # Insert Interacciones
    for u, v, kdata in G.edges(data=True):
        if kdata.get('relation') == 'INTERACTUA_CON':
            s1 = u.replace('Sust:', '')
            s2 = v.replace('Sust:', '')
            detail = kdata.get('detail', '')
            cur.execute('INSERT OR IGNORE INTO sustancia_interaccion VALUES (?, ?, ?)', (s1, s2, detail))

    # Add indexes for ultra-fast query execution
    cur.execute('CREATE INDEX idx_prod_name ON productos(nombre_producto)')
    cur.execute('CREATE INDEX idx_sust_name ON sustancias(nombre)')
    cur.execute('CREATE INDEX idx_prod_sust ON producto_sustancia(producto_name)')
    cur.execute('CREATE INDEX idx_sust_inter_orig ON sustancia_interaccion(sustancia_origen)')
    cur.execute('CREATE INDEX idx_sust_inter_dest ON sustancia_interaccion(sustancia_destino)')

    conn.commit()
    conn.close()
    print(f"Saved SQLite Knowledge DB to {OUTPUT_SQLITE_DB}")

if __name__ == "__main__":
    build_graph_and_db()
