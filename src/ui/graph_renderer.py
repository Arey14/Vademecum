import json
from pyvis.network import Network

# Node Styling Colors & Palettes
COLOR_PRODUCT = "#3B82F6"      # Blue
COLOR_LAB = "#10B981"          # Emerald
COLOR_SUSTANCIA = "#06B6D4"    # Cyan
COLOR_DUPLICATE = "#EF4444"    # Bright Red (Danger)
COLOR_PATOLOGIA = "#8B5CF6"    # Purple
COLOR_BACKGROUND = "#0F172A"   # Dark Slate Navy
COLOR_TEXT = "#F8FAFC"         # Off-white

# Edge Styling
COLOR_EDGE_CONTAINS = "#64748B"
COLOR_EDGE_MANUFACTURED = "#34D399"
COLOR_EDGE_INDICATED = "#A78BFA"
COLOR_EDGE_INTERACTION = "#F59E0B"  # Amber / Warning
COLOR_EDGE_DANGER = "#EF4444"

def create_base_network(height="650px", width="100%"):
    net = Network(height=height, width=width, bgcolor=COLOR_BACKGROUND, font_color=COLOR_TEXT, directed=True)
    # Configure smooth physics
    net.set_options("""
    {
      "nodes": {
        "font": {
          "size": 14,
          "face": "Inter, Roboto, sans-serif",
          "color": "#F8FAFC"
        },
        "borderWidth": 2,
        "shadow": {
          "enabled": true,
          "color": "rgba(0,0,0,0.5)",
          "size": 10,
          "x": 3,
          "y": 3
        }
      },
      "edges": {
        "color": {
          "inherit": false
        },
        "smooth": {
          "type": "continuous",
          "roundness": 0.3
        },
        "arrows": {
          "to": {
            "enabled": true,
            "scaleFactor": 0.7
          }
        },
        "font": {
          "size": 11,
          "color": "#94A3B8",
          "strokeWidth": 2,
          "strokeColor": "#0F172A"
        }
      },
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -60,
          "centralGravity": 0.01,
          "springLength": 110,
          "springConstant": 0.08,
          "damping": 0.85
        },
        "solver": "forceAtlas2Based",
        "stabilization": {
          "iterations": 150
        }
      },
      "interaction": {
        "hover": true,
        "navigationButtons": true,
        "zoomView": true,
        "multiselect": true
      }
    }
    """)
    return net

def generate_network_html(net):
    html = net.generate_html()
    # Inject styling to ensure the canvas looks great inside Streamlit
    custom_style = """
    <style>
      body { margin: 0; padding: 0; background-color: #0F172A; font-family: sans-serif; overflow: hidden; }
      #mynetwork { border: 1px solid #334155; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
      div.vis-tooltip {
        background-color: #1E293B !important;
        color: #F8FAFC !important;
        border: 1px solid #475569 !important;
        border-radius: 8px !important;
        padding: 10px 14px !important;
        font-family: Inter, sans-serif !important;
        font-size: 13px !important;
        max-width: 320px !important;
        box-shadow: 0 10px 25px rgba(0,0,0,0.5) !important;
      }
    </style>
    """
    return html.replace("</head>", f"{custom_style}</head>")
