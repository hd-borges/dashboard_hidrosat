# -*- coding: utf-8 -*-
"""
Created on Mon Mar 17 14:44:28 2025

@author: henrique
"""

import os
import datetime
import streamlit as st
import pandas as pd
import pickle
import plotly.graph_objects as go
from streamlit_plotly_events import plotly_events

st.set_page_config(layout="wide")

@st.cache_data
def load_data(filepath):
    """Load data from a pickle file."""
    with open(filepath, "rb") as f:
        return pickle.load(f)

# -------------------------------------------------------------------
# Use relative paths based on the location of this Python file.
# -------------------------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(BASE_DIR, "all_water_masses.pkl")  
MAPS_FOLDER = os.path.join(BASE_DIR, "maps")

# Load and prepare data
all_gdf = load_data(DATA_PATH)
all_gdf["date_key"] = pd.to_datetime(all_gdf["date_key"], errors="coerce")

st.title("Visualização de qualidade de Água obtida por dados espaciais")

# Create two columns
col_left, col_right = st.columns([0.8, 1], gap="small")

with col_left:
    # 1) Select Water Mass
    mass_list = sorted(all_gdf["nmoriginal"].dropna().unique())
    default_mass = "Açude Castanhão" if "Açude Castanhão" in mass_list else mass_list[0]
    selected_mass = st.selectbox("Selecione a massa d'água:", mass_list, index=mass_list.index(default_mass))

    # 2) Select Parameter (only mean values)
    param_options = {
        "Clorofila-a (Média)": "chla_mean",
        "Turbidez (Média)": "turb_mean",
    }
    selected_param_label = st.radio("Selecione o parâmetro:", list(param_options.keys()))
    selected_param_col = param_options[selected_param_label]

    # 3) Date range slider with actual dates
    min_date = all_gdf["date_key"].min().date()
    max_date = all_gdf["date_key"].max().date()

    date_range = st.slider(
        "Selecione o intervalo de datas:",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
        format="YYYY-MM-DD"
    )

    # Filter data based on selections
    mask = (
        (all_gdf["nmoriginal"] == selected_mass) &
        (all_gdf["date_key"].dt.date >= date_range[0]) &
        (all_gdf["date_key"].dt.date <= date_range[1])
    )
    filtered_data = all_gdf[mask].copy()
    filtered_data = filtered_data[filtered_data[selected_param_col] > 0]
    filtered_data.sort_values("date_key", inplace=True)
    filtered_data.reset_index(drop=True, inplace=True)

    if filtered_data.empty:
        st.warning("Nenhum dado disponível para essa combinação.")
        st.stop()

    # Convert raw data to µg/L for Clorofila-a and keep NTU for Turbidez
    if selected_param_col == "chla_mean":
        filtered_data["value"] = filtered_data[selected_param_col] / 100
        y_axis_title = "µg/L"
    else:
        filtered_data["value"] = filtered_data[selected_param_col]
        y_axis_title = "NTU"

    # Build Plotly scatter plot
    x_vals = filtered_data["date_key"].tolist()
    y_vals = filtered_data["value"].astype(float).tolist()

    # Choose marker color
    if selected_param_col == "chla_mean":
        point_color = "limegreen"
    else:
        point_color = "brown"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="markers",
            marker=dict(size=8, color=point_color, line=dict(width=1, color='black')),
            name=selected_param_label,
            hovertemplate=f"<b>Data:</b> %{{x}}<br><b>Valor:</b> %{{y:.2f}} {y_axis_title}<extra></extra>"
        )
    )

    # Ensure y-axis always starts at 0
    y_max = max(y_vals) if y_vals else 1
    fig.update_layout(
        xaxis_title="Data",
        yaxis_title=y_axis_title,
        yaxis=dict(range=[0, y_max * 1.1], showgrid=True),
        xaxis=dict(showgrid=True),
        margin=dict(l=40, r=60, t=40, b=20),  # Reduced top and bottom margins
        height=300,  # Reduced from 350
        width=850,
        title=f"{selected_mass} – {selected_param_label}"
    )

    clicked_points = plotly_events(
        fig,
        click_event=True,
        hover_event=False,
        select_event=False,
        override_height=400  # Reduced from 600
    )

with col_right:
    # Add custom CSS to reduce spacing
    st.markdown("""
        <style>
        .block-container {gap: 1rem !important;}
        .element-container {margin: 1px !important;}
        </style>
    """, unsafe_allow_html=True)
    
    st.subheader("Mapa Selecionado", divider='gray')
    
    # Define options and create radio selector
    agg_options = ["Diário", "Mensal", "Trimestral", "Anual", "Permanência"]
    selected_agg = st.radio(
        "Selecione o nível de agregação do mapa:",
        options=agg_options,
        horizontal=True
    )

    if clicked_points:
        point_info = clicked_points[0]
        point_index = point_info["pointIndex"]
        row_data = filtered_data.iloc[point_index]
        clicked_date = row_data["date_key"]

        # Combine date display with the subheader
        st.markdown(f"**Data**: {clicked_date.strftime('%Y-%m-%d')}")

        gid_val = int(row_data["gid"])
        date_str = clicked_date.strftime("%Y%m%d")

        # Build the appropriate file path based on the selected aggregation level
        if selected_agg == "Diário":
            if selected_param_col == "chla_mean":
                image_name = f"{date_str}_Chla_Diario.png"
                map_path = os.path.join(MAPS_FOLDER, str(gid_val), "Chla", "Diário", image_name)
            else:
                image_name = f"{date_str}_Turb_Diario.png"
                map_path = os.path.join(MAPS_FOLDER, str(gid_val), "Turbidez", "Diário", image_name)

        elif selected_agg == "Mensal":
            month_str = clicked_date.strftime("%Y_%m")
            if selected_param_col == "chla_mean":
                folder_path = os.path.join(MAPS_FOLDER, str(gid_val), "Chla", "Mensal", "Média")
            else:
                folder_path = os.path.join(MAPS_FOLDER, str(gid_val), "Turbidez", "Mensal", "Média")

            image_name = None
            if os.path.exists(folder_path):
                image_name = next((f for f in os.listdir(folder_path) if f.startswith(month_str)), None)
            map_path = os.path.join(folder_path, image_name) if image_name else None

        elif selected_agg == "Trimestral":
            quarter = (clicked_date.month - 1) // 3 + 1
            quarter_str = f"{clicked_date.year}_{quarter}°Trimestre_Média"
            image_name = f"{quarter_str}.png"
            if selected_param_col == "chla_mean":
                map_path = os.path.join(MAPS_FOLDER, str(gid_val), "Chla", "Trimestral", "Média", image_name)
            else:
                map_path = os.path.join(MAPS_FOLDER, str(gid_val), "Turbidez", "Trimestral", "Média", image_name)

        elif selected_agg == "Anual":
            year_str = clicked_date.strftime("%Y")
            image_name = f"{year_str}_Média.png"
            if selected_param_col == "chla_mean":
                map_path = os.path.join(MAPS_FOLDER, str(gid_val), "Chla", "Anual", "Média", image_name)
            else:
                map_path = os.path.join(MAPS_FOLDER, str(gid_val), "Turbidez", "Anual", "Média", image_name)

        else:  # Permanência
            year_str = clicked_date.strftime("%Y")
            image_name = f"{year_str}_Permanência 90%.png"
            if selected_param_col == "chla_mean":
                map_path = os.path.join(MAPS_FOLDER, str(gid_val), "Chla", "Anual", "Permanência_90", image_name)
            else:
                map_path = os.path.join(MAPS_FOLDER, str(gid_val), "Turbidez", "Anual", "Permanência_90", image_name)

        if map_path and os.path.exists(map_path):
            # Adjust map size with columns
            col1, col2, col3 = st.columns([1,1,1])
            with col2:
                st.image(
                    map_path, 
                    caption=f"GID: {gid_val}", 
                    width=400,  # Set the desired width in pixels
                )
        else:
            st.warning(f"Mapa não encontrado: {map_path}")
    else:
        # Center the message
        st.markdown("<div style='text-align: center; margin-top: 20px;'>Clique em um ponto do gráfico para ver o mapa aqui.</div>", unsafe_allow_html=True)
