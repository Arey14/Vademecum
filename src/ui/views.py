import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import pandas as pd
from pathlib import Path
from pyvis.network import Network

from src.tools.check_interactions import get_connection, evaluate_combination
from src.ui.graph_renderer import (
    create_base_network, generate_network_html,
    COLOR_PRODUCT, COLOR_LAB, COLOR_SUSTANCIA, COLOR_DUPLICATE, COLOR_PATOLOGIA,
    COLOR_EDGE_CONTAINS, COLOR_EDGE_MANUFACTURED, COLOR_EDGE_INDICATED,
    COLOR_EDGE_INTERACTION, COLOR_EDGE_DANGER
)

@st.cache_data(show_spinner=False)
def load_all_entities():
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT DISTINCT nombre_producto FROM productos WHERE nombre_producto IS NOT NULL AND nombre_producto != '' ORDER BY nombre_producto")
    products = [r[0] for r in cur.fetchall()]
    
    cur.execute("SELECT DISTINCT nombre FROM sustancias WHERE nombre IS NOT NULL AND nombre != '' ORDER BY nombre")
    substances = [r[0] for r in cur.fetchall()]
    
    cur.execute("SELECT DISTINCT nombre FROM laboratorios WHERE nombre IS NOT NULL AND nombre != '' ORDER BY nombre")
    laboratories = [r[0] for r in cur.fetchall()]
    
    cur.execute("SELECT COUNT(*) FROM productos")
    n_prod = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM sustancias")
    n_sust = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM laboratorios")
    n_lab = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM sustancia_interaccion")
    n_inter = cur.fetchone()[0]
    
    conn.close()
    
    stats = {
        "n_prod": n_prod,
        "n_sust": n_sust,
        "n_lab": n_lab,
        "n_inter": n_inter
    }
    return products, substances, laboratories, stats

def render_combination_view():
    st.markdown("### 💊 Evaluador de Combinaciones e Interacciones Medicamentosas")
    st.markdown("Ingresa dos o más medicamentos para analizar visualmente la duplicidad de principios activos, interacciones directas y contraindicaciones.")
    
    products, _, _, _ = load_all_entities()
    
    # Presets
    preset = st.selectbox(
        "💡 O selecciona un ejemplo predefinido:",
        options=[
            "Personalizado (Elegir medicamentos)",
            "3TC + 3-TC/AZT ELEA (Duplicidad de Lamivudina)",
            "Ibupirac + Actron 600 (Duplicidad de Ibuprofeno)",
            "Amoxicilina + Clavulánico / Combinación antibiótica",
            "Aspirina + Sintrom / Anticoagulantes"
        ]
    )
    
    default_selection = []
    if preset == "3TC + 3-TC/AZT ELEA (Duplicidad de Lamivudina)":
        default_selection = ["3TC", "3-TC/AZT ELEA"]
    elif preset == "Ibupirac + Actron 600 (Duplicidad de Ibuprofeno)":
        matches = [p for p in products if "IBUPIRAC" in p.upper() or "ACTRON" in p.upper()]
        default_selection = matches[:2] if len(matches) >= 2 else ["IBUPIRAC"]
    elif preset == "Aspirina + Sintrom / Anticoagulantes":
        matches_asp = [p for p in products if "ASPIRINA" in p.upper()]
        matches_sin = [p for p in products if "SINTROM" in p.upper()]
        default_selection = (matches_asp[:1] + matches_sin[:1]) if matches_asp and matches_sin else []

    selected_meds = st.multiselect(
        "🔍 Busca y selecciona los medicamentos a evaluar:",
        options=products,
        default=default_selection,
        help="Escribe el nombre comercial del medicamento"
    )
    
    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        show_labs = st.checkbox("Mostrar Laboratorios Fabricantes", value=True)
    with col_opt2:
        show_pathologies = st.checkbox("Mostrar Patologías / Indicaciones", value=False)
        
    if not selected_meds:
        st.info("👆 Selecciona al menos dos medicamentos para renderizar el subgrafo.")
        return
        
    res = evaluate_combination(selected_meds)
    if res['status'] == 'error':
        st.error(res['message'])
        return
        
    # Build Interactive PyVis Network
    net = create_base_network(height="620px")
    
    duplicate_names_lower = {d['name'].lower() for d in res['duplications']}
    
    # 1. Add Product Nodes
    for p in res['found_products']:
        p_id = f"Prod:{p['nombre']}"
        net.add_node(
            p_id,
            label=p['nombre'],
            title=f"<b>Medicamento:</b> {p['nombre']}<br><b>Laboratorio:</b> {p['laboratorio'] or 'N/A'}<br><b>Indicaciones:</b> {p['indicaciones'] or 'N/A'}",
            color=COLOR_PRODUCT,
            shape="box",
            size=22,
            borderWidth=2
        )
        
        # Link to Laboratory
        if show_labs and p['laboratorio']:
            lab_id = f"Lab:{p['laboratorio']}"
            net.add_node(
                lab_id,
                label=p['laboratorio'],
                title=f"<b>Laboratorio:</b> {p['laboratorio']}",
                color=COLOR_LAB,
                shape="diamond",
                size=18
            )
            net.add_edge(p_id, lab_id, label="fabricado por", color=COLOR_EDGE_MANUFACTURED, dashes=True)
            
        # Link to Active Ingredients
        for ing in p['principios_activos']:
            ing_id = f"Sust:{ing}"
            is_dup = ing.lower() in duplicate_names_lower
            
            node_color = COLOR_DUPLICATE if is_dup else COLOR_SUSTANCIA
            node_shape = "star" if is_dup else "dot"
            node_label = f"🚨 {ing} (DUPLICIDAD)" if is_dup else ing
            node_size = 26 if is_dup else 18
            
            # Fetch details for tooltip
            cur_details = next((d for d in res['ingredient_details'] if d['nombre'].lower() == ing.lower()), None)
            tooltip_html = f"<b>Principio Activo:</b> {ing}"
            if is_dup:
                tooltip_html += "<br><span style='color:#EF4444; font-weight:bold;'>⚠️ ALERTA: Principio repetido en la combinación</span>"
            if cur_details:
                if cur_details['accion_therapeutica']:
                    tooltip_html += f"<br><b>Acción:</b> {cur_details['accion_therapeutica']}"
                if cur_details['contraindicaciones']:
                    tooltip_html += f"<br><b>Contraindicaciones:</b> {cur_details['contraindicaciones'][:160]}..."
                    
            net.add_node(
                ing_id,
                label=node_label,
                title=tooltip_html,
                color=node_color,
                shape=node_shape,
                size=node_size
            )
            net.add_edge(p_id, ing_id, label="contiene", color=COLOR_EDGE_CONTAINS, width=2)
            
        # Optional: Pathologies
        if show_pathologies:
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT patologia_name FROM producto_patologia WHERE producto_name = ?", (p['nombre'],))
            pat_rows = c.fetchall()
            conn.close()
            for pat in pat_rows:
                pat_name = pat[0]
                pat_id = f"Pat:{pat_name}"
                net.add_node(pat_id, label=pat_name, title=f"Patología: {pat_name}", color=COLOR_PATOLOGIA, shape="ellipse", size=14)
                net.add_edge(p_id, pat_id, label="indicado para", color=COLOR_EDGE_INDICATED, dashes=True)
                
    # Add Direct Interactions Edges
    for inter in res['interactions']:
        s1_id = f"Sust:{inter['sustancia_1']}"
        s2_id = f"Sust:{inter['sustancia_2']}"
        inter_title = f"<b style='color:#F59E0B;'>⚠️ INTERACCIÓN DIRECTA:</b><br>{inter['detalle']}"
        net.add_edge(s1_id, s2_id, label="⚠️ INTERACTÚA", title=inter_title, color=COLOR_EDGE_INTERACTION, width=4)
        net.add_edge(s2_id, s1_id, label="⚠️ INTERACTÚA", title=inter_title, color=COLOR_EDGE_INTERACTION, width=4)
        
    html_graph = generate_network_html(net)
    
    st.markdown("#### 🕸️ Subgrafo de la Combinación")
    components.html(html_graph, height=640, scrolling=False)
    
    # Clinical Alerts Summary
    st.markdown("---")
    st.markdown("### 📋 Informe Clínico y Farmacológico")
    
    col_dup, col_inter = st.columns(2)
    
    with col_dup:
        st.markdown("#### 1. Evaluación de Duplicidad de Principios")
        if res['duplications']:
            for dup in res['duplications']:
                st.error(f"🚨 **Alerta de Sobredosis / Duplicidad:** El principio activo **{dup['name']}** está presente en: *{', '.join(dup['products'])}*.")
        else:
            st.success("✅ No se detectaron duplicaciones de principios activos.")
            
    with col_inter:
        st.markdown("#### 2. Interacciones Directas entre Fármacos")
        if res['interactions']:
            for inter in res['interactions']:
                st.warning(f"⚠️ **Interacción detectada:** {inter['sustancia_1']} ↔ {inter['sustancia_2']}\n\n**Detalle:** {inter['detalle']}")
        else:
            st.success("✅ No se registraron interacciones cruzadas directas conocidas.")
            
    # Precautions & Technical Sheets
    with st.expander("🩺 Ver Precauciones y Contraindicaciones de cada Sustancia"):
        for ing in res['ingredient_details']:
            st.markdown(f"##### 💊 **{ing['nombre']}** (en {', '.join(ing['used_in'])})")
            if ing['accion_therapeutica']:
                st.markdown(f"- **Acción Terapéutica:** {ing['accion_therapeutica']}")
            if ing['contraindicaciones']:
                st.markdown(f"- **Contraindicaciones:** {ing['contraindicaciones']}")
            if ing['precauciones']:
                st.markdown(f"- **Precauciones:** {ing['precauciones']}")
            if ing['reacciones_adversas']:
                st.markdown(f"- **Reacciones Adversas:** {ing['reacciones_adversas']}")
            st.markdown("---")

def render_entity_explorer_view():
    st.markdown("### 🔍 Explorador de Entidades (Ego-Graph de 1 y 2 Saltos)")
    st.markdown("Inspecciona cualquier entidad del Grafo (Medicamento, Sustancia o Laboratorio) para explorar su vecindario y relaciones.")
    
    products, substances, laboratories, _ = load_all_entities()
    
    col_type, col_entity = st.columns([1, 2])
    with col_type:
        entity_type = st.selectbox("Tipo de Entidad:", ["Medicamento / Producto", "Principio Activo / Sustancia", "Laboratorio Farmacéutico"])
    with col_entity:
        if entity_type == "Medicamento / Producto":
            selected_name = st.selectbox("Selecciona o busca el Medicamento:", options=products)
        elif entity_type == "Principio Activo / Sustancia":
            selected_name = st.selectbox("Selecciona o busca la Sustancia:", options=substances)
        else:
            selected_name = st.selectbox("Selecciona o busca el Laboratorio:", options=laboratories)
            
    col_hop, col_sub_inter = st.columns(2)
    with col_hop:
        hops = st.slider("Profundidad de exploración (Saltos en el grafo):", min_value=1, max_value=2, value=1)
    with col_sub_inter:
        include_inter = st.checkbox("Incluir aristas de interacción farmacológica", value=True)
        
    if not selected_name:
        return
        
    conn = get_connection()
    cur = conn.cursor()
    net = create_base_network(height="600px")
    
    details_card = {}
    
    if entity_type == "Medicamento / Producto":
        cur.execute("SELECT nombre_producto, laboratorio_nombre, descripcion, composicion, indicaciones, presentacion FROM productos WHERE nombre_producto = ?", (selected_name,))
        prod_row = cur.fetchone()
        if prod_row:
            details_card = {
                "Tipo": "Medicamento",
                "Nombre": prod_row[0],
                "Laboratorio": prod_row[1],
                "Descripción": prod_row[2],
                "Composición": prod_row[3],
                "Indicaciones": prod_row[4],
                "Presentación": prod_row[5]
            }
            p_id = f"Prod:{prod_row[0]}"
            net.add_node(p_id, label=prod_row[0], title=f"<b>Medicamento:</b> {prod_row[0]}", color=COLOR_PRODUCT, shape="box", size=26)
            
            # Hop 1: Lab
            if prod_row[1]:
                lab_id = f"Lab:{prod_row[1]}"
                net.add_node(lab_id, label=prod_row[1], title=f"<b>Laboratorio:</b> {prod_row[1]}", color=COLOR_LAB, shape="diamond", size=20)
                net.add_edge(p_id, lab_id, label="fabricado por", color=COLOR_EDGE_MANUFACTURED, dashes=True)
                
            # Hop 1: Active Ingredients
            cur.execute("SELECT sustancia_name FROM producto_sustancia WHERE producto_name = ?", (prod_row[0],))
            sust_rows = [r[0] for r in cur.fetchall()]
            for s_name in sust_rows:
                s_id = f"Sust:{s_name}"
                net.add_node(s_id, label=s_name, title=f"<b>Principio:</b> {s_name}", color=COLOR_SUSTANCIA, shape="dot", size=20)
                net.add_edge(p_id, s_id, label="contiene", color=COLOR_EDGE_CONTAINS, width=2)
                
                # Hop 2: Interactions of these substances
                if hops >= 2 and include_inter:
                    cur.execute("SELECT sustancia_destino, detalle FROM sustancia_interaccion WHERE sustancia_origen = ?", (s_name,))
                    for inter_dest, inter_det in cur.fetchall()[:12]:
                        dest_id = f"Sust:{inter_dest}"
                        net.add_node(dest_id, label=inter_dest, title=f"<b>Sustancia:</b> {inter_dest}", color=COLOR_SUSTANCIA, shape="dot", size=14)
                        net.add_edge(s_id, dest_id, label="⚠️ interactúa", title=inter_det[:250], color=COLOR_EDGE_INTERACTION, width=2)
                        
    elif entity_type == "Principio Activo / Sustancia":
        cur.execute("SELECT nombre, accion_therapeutica, propiedades, indicaciones, dosificacion, reacciones_adversas, precauciones, interacciones, contraindicaciones FROM sustancias WHERE nombre = ?", (selected_name,))
        s_row = cur.fetchone()
        if s_row:
            details_card = {
                "Tipo": "Principio Activo",
                "Nombre": s_row[0],
                "Acción Terapéutica": s_row[1],
                "Indicaciones": s_row[3],
                "Interacciones": s_row[7],
                "Contraindicaciones": s_row[8],
                "Precauciones": s_row[6],
                "Reacciones Adversas": s_row[5]
            }
            s_id = f"Sust:{s_row[0]}"
            net.add_node(s_id, label=s_row[0], title=f"<b>Principio Activo:</b> {s_row[0]}", color=COLOR_SUSTANCIA, shape="dot", size=30)
            
            # Hop 1: Products containing it
            cur.execute("SELECT producto_name FROM producto_sustancia WHERE sustancia_name = ? LIMIT 25", (s_row[0],))
            prods = [r[0] for r in cur.fetchall()]
            for p_name in prods:
                p_id = f"Prod:{p_name}"
                net.add_node(p_id, label=p_name, title=f"<b>Medicamento:</b> {p_name}", color=COLOR_PRODUCT, shape="box", size=16)
                net.add_edge(p_id, s_id, label="contiene", color=COLOR_EDGE_CONTAINS)
                
            # Hop 1: Interactions
            if include_inter:
                cur.execute("SELECT sustancia_destino, detalle FROM sustancia_interaccion WHERE sustancia_origen = ?", (s_row[0],))
                for dest_name, inter_det in cur.fetchall():
                    dest_id = f"Sust:{dest_name}"
                    net.add_node(dest_id, label=dest_name, title=f"<b>Principio:</b> {dest_name}", color=COLOR_SUSTANCIA, shape="dot", size=18)
                    net.add_edge(s_id, dest_id, label="⚠️ interactúa", title=inter_det[:250], color=COLOR_EDGE_INTERACTION, width=3)
                    
    elif entity_type == "Laboratorio Farmacéutico":
        cur.execute("SELECT nombre, url, direccion, ciudad, provincia, telefono FROM laboratorios WHERE nombre = ?", (selected_name,))
        lab_row = cur.fetchone()
        if lab_row:
            details_card = {
                "Tipo": "Laboratorio",
                "Nombre": lab_row[0],
                "Dirección": lab_row[2],
                "Ciudad/Provincia": f"{lab_row[3] or ''}, {lab_row[4] or ''}".strip(", "),
                "Teléfono": lab_row[5]
            }
            l_id = f"Lab:{lab_row[0]}"
            net.add_node(l_id, label=lab_row[0], title=f"<b>Laboratorio:</b> {lab_row[0]}", color=COLOR_LAB, shape="diamond", size=32)
            
            # Hop 1: Manufactured products
            cur.execute("SELECT nombre_producto FROM productos WHERE laboratorio_nombre = ? LIMIT 35", (lab_row[0],))
            prods = [r[0] for r in cur.fetchall()]
            for p_name in prods:
                p_id = f"Prod:{p_name}"
                net.add_node(p_id, label=p_name, title=f"<b>Medicamento:</b> {p_name}", color=COLOR_PRODUCT, shape="box", size=16)
                net.add_edge(p_id, l_id, label="fabricado por", color=COLOR_EDGE_MANUFACTURED)
                
                # Hop 2: Active ingredients of products
                if hops >= 2:
                    cur.execute("SELECT sustancia_name FROM producto_sustancia WHERE producto_name = ?", (p_name,))
                    for s_row in cur.fetchall():
                        s_name = s_row[0]
                        s_id = f"Sust:{s_name}"
                        net.add_node(s_id, label=s_name, title=f"<b>Principio:</b> {s_name}", color=COLOR_SUSTANCIA, shape="dot", size=14)
                        net.add_edge(p_id, s_id, label="contiene", color=COLOR_EDGE_CONTAINS)
                        
    conn.close()
    
    col_graph, col_card = st.columns([2, 1])
    
    with col_graph:
        st.markdown(f"#### 🕸️ Red Vecina de: **{selected_name}**")
        html_graph = generate_network_html(net)
        components.html(html_graph, height=580, scrolling=False)
        
    with col_card:
        st.markdown("#### 📄 Ficha Técnica")
        for k, v in details_card.items():
            if v:
                st.markdown(f"**{k}:** {v}")
                st.markdown("---")

def render_interaction_map_view():
    st.markdown("### 🌐 Red Global de Interacciones Farmacológicas")
    st.markdown("Explora la red densa de principios activos que presentan interacciones cruzadas documentadas.")
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Query interaction counts per substance
    cur.execute("""
    SELECT sustancia_origen, COUNT(*) as deg 
    FROM sustancia_interaccion 
    GROUP BY sustancia_origen 
    ORDER BY deg DESC
    """)
    deg_rows = cur.fetchall()
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        min_deg = st.slider("Conectividad Mínima (Número de Interacciones):", min_value=1, max_value=50, value=12)
    with col_f2:
        max_nodes = st.slider("Límite de Sustancias Principales a mostrar:", min_value=10, max_value=120, value=40)
        
    filtered_substances = [r[0] for r in deg_rows if r[1] >= min_deg][:max_nodes]
    
    if not filtered_substances:
        st.warning("No hay sustancias con ese umbral de conexiones.")
        conn.close()
        return
        
    net = create_base_network(height="650px")
    
    # Add nodes with scaled sizes according to degrees
    sust_set = set(filtered_substances)
    deg_map = dict(deg_rows)
    
    for s_name in filtered_substances:
        d = deg_map.get(s_name, 1)
        node_size = min(40, max(14, 10 + d * 0.8))
        net.add_node(
            f"Sust:{s_name}",
            label=f"{s_name} ({d})",
            title=f"<b>Principio:</b> {s_name}<br><b>Interacciones Totales:</b> {d}",
            color=COLOR_SUSTANCIA,
            shape="dot",
            size=node_size
        )
        
    # Add edges between filtered nodes
    placeholders = ','.join(['?'] * len(filtered_substances))
    cur.execute(f"""
    SELECT sustancia_origen, sustancia_destino, detalle 
    FROM sustancia_interaccion 
    WHERE sustancia_origen IN ({placeholders}) AND sustancia_destino IN ({placeholders})
    """, filtered_substances + filtered_substances)
    
    interactions = cur.fetchall()
    conn.close()
    
    added_edges = set()
    for s1, s2, det in interactions:
        edge_key = tuple(sorted([s1, s2]))
        if edge_key not in added_edges:
            added_edges.add(edge_key)
            net.add_edge(f"Sust:{s1}", f"Sust:{s2}", title=f"<b>Interacción:</b><br>{det[:250]}...", color=COLOR_EDGE_INTERACTION, width=2)
            
    st.info(f"📊 Mostrando **{len(filtered_substances)} principios activos** y **{len(added_edges)} relaciones de interacción**.")
    
    html_graph = generate_network_html(net)
    components.html(html_graph, height=670, scrolling=False)
    
    with st.expander("📋 Ver Tabla de Interacciones de la Red Seleccionada"):
        df_inter = pd.DataFrame([
            {"Sustancia 1": s1, "Sustancia 2": s2, "Detalle Clínico": det} 
            for s1, s2, det in interactions
        ])
        st.dataframe(df_inter, use_container_width=True)
