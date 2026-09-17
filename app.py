#!/usr/bin/env python3
import streamlit as st
from src.ui.views import (
    render_combination_view,
    render_entity_explorer_view,
    render_interaction_map_view,
    load_all_entities
)

# Page configuration
st.set_page_config(
    page_title="Vademecum Knowledge Graph Explorer",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #38BDF8;
        margin-bottom: 0px;
    }
    .sub-header {
        font-size: 1rem;
        color: #94A3B8;
        margin-bottom: 24px;
    }
    .metric-box {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
        margin-bottom: 12px;
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #38BDF8;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #94A3B8;
    }
</style>
""", unsafe_allow_html=True)

def main():
    # Sidebar
    with st.sidebar:
        st.markdown("## 💊 **Vademecum Graph**")
        st.markdown("Explorador interactivo del Grafo de Conocimiento Farmacológico y Evaluador Clínico.")
        st.markdown("---")
        
        mode = st.radio(
            "🧭 Selecciona la Vista:",
            options=[
                "💊 Evaluador de Combinaciones",
                "🔍 Explorador de Entidades",
                "🌐 Red Global de Interacciones"
            ],
            index=0
        )
        
        st.markdown("---")
        st.markdown("### 📊 Métricas del Grafo")
        
        try:
            _, _, _, stats = load_all_entities()
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"""
                <div class="metric-box">
                    <div class="metric-value">{stats['n_prod']:,}</div>
                    <div class="metric-label">Medicamentos</div>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <div class="metric-box">
                    <div class="metric-value">{stats['n_lab']:,}</div>
                    <div class="metric-label">Laboratorios</div>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div class="metric-box">
                    <div class="metric-value">{stats['n_sust']:,}</div>
                    <div class="metric-label">Sustancias</div>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(f"""
                <div class="metric-box">
                    <div class="metric-value">{stats['n_inter']:,}</div>
                    <div class="metric-label">Interacciones</div>
                </div>
                """, unsafe_allow_html=True)
        except Exception as e:
            st.caption("No se pudieron cargar las estadísticas del grafo.")
            
        st.markdown("---")
        st.markdown("### 🎨 Leyenda del Grafo")
        st.markdown("""
        - 🟦 **Azul:** Medicamento comercial
        - 🟩 **Verde:** Laboratorio fabricante
        - 🔵 **Cyan:** Principio activo / Sustancia
        - 🚨 **Rojo:** Principio activo duplicado
        - 🟪 **Púrpura:** Patología / Indicación
        - ⚡ **Naranja:** Interacción fármaco-fármaco
        """)
        
    # Main Header
    st.markdown('<div class="main-header">💊 Vademecum Knowledge Graph & Interaction Explorer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Fuente determinística de verdad sobre medicamentos, principios activos, contraindicaciones e interacciones clínicas.</div>', unsafe_allow_html=True)
    
    # Render view
    if mode == "💊 Evaluador de Combinaciones":
        render_combination_view()
    elif mode == "🔍 Explorador de Entidades":
        render_entity_explorer_view()
    elif mode == "🌐 Red Global de Interacciones":
        render_interaction_map_view()

if __name__ == "__main__":
    main()
