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
col_left, col_right = st.columns([1, 1], gap="large")

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
        margin=dict(l=40, r=60, t=60, b=40),
        height=350,
        width=900,
        title=f"{selected_mass} – {selected_param_label}"
    )

    clicked_points = plotly_events(
        fig,
        click_event=True,
        hover_event=False,
        select_event=False,
        override_height=600
    )

with col_right:
    st.subheader("Mapa Selecionado")
    
    # Replace multiple radios with a single horizontal radio
    agg_options = ["Diário", "Mensal", "Trimestral", "Anual", "Permanência"]
    st.write("Selecione o nível de agregação do mapa:")
    selected_agg = st.radio(
        label="",
        options=agg_options,
        horizontal=True,
        label_visibility="collapsed"
    )

    if clicked_points:
        point_info = clicked_points[0]
        point_index = point_info["pointIndex"]
        row_data = filtered_data.iloc[point_index]
        clicked_date = row_data["date_key"]

        st.write(f"**Data selecionada**: {clicked_date.strftime('%Y-%m-%d')}")

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
            quarter_str = f"{clicked_date.year}_{quarter}°Trimestre_Média"  # Remove space before "Trimestre"
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
            st.image(map_path, 
                     caption=f"Mapa para {clicked_date.strftime('%Y-%m-%d')} (GID: {gid_val})", 
                     use_container_width=True)  # Updated parameter name
        else:
            st.warning(f"Mapa não encontrado: {map_path}")
    else:
        st.write("Clique em um ponto do gráfico para ver o mapa aqui.")
