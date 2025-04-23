# -*- coding: utf-8 -*-
"""
Created on Mon Mar 17 14:44:28 2025
@author: henrique

Improved to include:
 - Min / Median / Max metrics
 - Suppress low-pixel-count points
 - Optional rolling-mean line
"""
import os
import datetime
import streamlit as st
import pandas as pd
import pickle
import plotly.graph_objects as go
from streamlit_plotly_events import plotly_events

# Set a wide page layout
st.set_page_config(layout="wide")

# Custom CSS for smaller title
st.markdown("""
    <style>
    .smaller-title {
        font-size: 28px !important;
        font-weight: bold !important;
        margin-bottom: 0px !important;
    }
    </style>
""", unsafe_allow_html=True)

# Header
st.markdown(
    '<p class="smaller-title">Visualização de Qualidade de Água obtida por dados espaciais</p>',
    unsafe_allow_html=True
)

@st.cache_data
def load_data(filepath):
    """Load data from a pickle file."""
    with open(filepath, "rb") as f:
        return pickle.load(f)

# -------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------
BASE_DIR    = os.path.dirname(__file__)
DATA_PATH   = os.path.join(BASE_DIR, "all_water_masses.pkl")
MAPS_FOLDER = os.path.join(BASE_DIR, "maps")

# Load and prepare
all_gdf = load_data(DATA_PATH)
all_gdf["date_key"] = pd.to_datetime(all_gdf["date_key"], errors="coerce")

# Two-column layout
col_left, col_right = st.columns([1, 0.9], gap="small")

with col_left:
    # 1) Water mass selector
    mass_list    = sorted(all_gdf["nmoriginal"].dropna().unique())
    default_mass = "Açude Castanhão" if "Açude Castanhão" in mass_list else mass_list[0]
    selected_mass = st.selectbox(
        "Selecione a massa d'água:",
        mass_list,
        index=mass_list.index(default_mass)
    )

    # 2) Parameter selector
    param_options       = {
        "Clorofila-a (Média)": "chla_mean",
        "Turbidez (Média)"   : "turb_mean",
    }
    selected_param_label = st.radio(
        "Selecione o parâmetro:",
        list(param_options.keys())
    )
    selected_param_col   = param_options[selected_param_label]

    # 3) Date range
    min_date = all_gdf["date_key"].min().date()
    max_date = all_gdf["date_key"].max().date()
    date_range = st.slider(
        "Selecione o intervalo de datas:",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
        format="YYYY-MM-DD"
    )

    # 4) Aggregation level (for maps)
    agg_options  = ["Diário", "Mensal", "Trimestral", "Anual", "Permanência"]
    selected_agg = st.radio(
        "Selecione o nível de agregação do mapa:",
        options=agg_options,
        horizontal=True
    )

    # 5) Filter core data
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

    # 6) Suppress low-count points
    #    count_col comes from the raw stats in the pkl
    count_col = "chla_count" if selected_param_col == "chla_mean" else "turb_count"
    suppress = st.checkbox("Suppress low-count points based on pixel count")
    if suppress:
        default_thr = int(filtered_data[count_col].quantile(0.25))
        thr = st.slider(
            "Minimum pixel-count threshold:",
            min_value=int(filtered_data[count_col].min()),
            max_value=int(filtered_data[count_col].max()),
            value=default_thr
        )
        filtered_data = filtered_data[filtered_data[count_col] >= thr]
        if filtered_data.empty:
            st.warning("Nenhum dado disponível após aplicar o filtro de contagem de pixels.")
            st.stop()

    # 7) Convert to display units
    if selected_param_col == "turb_mean":
        filtered_data["value"] = filtered_data[selected_param_col].astype(float) / 100
        y_axis_title = "NTU"
    else:
        filtered_data["value"] = filtered_data[selected_param_col].astype(float) / 100
        y_axis_title = "µg/L"

    # 8) Summary metrics
    stats = filtered_data["value"].astype(float)
    min_val    = stats.min()
    median_val = stats.median()
    max_val    = stats.max()
    m1, m2, m3 = st.columns(3)
    m1.metric("Min",    f"{min_val:.2f} {y_axis_title}")
    m2.metric("Median", f"{median_val:.2f} {y_axis_title}")
    m3.metric("Max",    f"{max_val:.2f} {y_axis_title}")

    # 9) Build Plotly figure
    x_vals = filtered_data["date_key"].tolist()
    y_vals = filtered_data["value"].tolist()
    point_color = "limegreen" if selected_param_col == "chla_mean" else "brown"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="markers",
            marker=dict(size=8, color=point_color, line=dict(width=1, color="black")),
            name=selected_param_label,
            hovertemplate=(
                "<b>Data:</b> %{x}<br>"
                "<b>Valor:</b> %{y:.2f} " + y_axis_title + "<extra></extra>"
            )
        )
    )

    # 10) Optional rolling mean
    rolling = st.checkbox("Show rolling mean line")
    if rolling:
        # window in days
        window_days = st.slider("Rolling mean window (days):", 1, 365, 30)
        # compute time-based rolling mean
        rm = (
            filtered_data
            .set_index("date_key")["value"]
            .rolling(f"{window_days}D")
            .mean()
            .dropna()
        )
        fig.add_trace(
            go.Scatter(
                x=rm.index,
                y=rm.values,
                mode="lines",
                name=f"{window_days}-day rolling mean",
                line=dict(width=2)
            )
        )
        show_legend = True
    else:
        show_legend = False

    # 11) Layout tweaks
    y_max = max(y_vals) if y_vals else 1
    fig.update_layout(
        autosize=True,
        xaxis_title="Data",
        yaxis_title=y_axis_title,
        yaxis=dict(range=[0, y_max * 1.1], showgrid=True),
        xaxis=dict(showgrid=True),
        margin=dict(l=40, r=20, t=20, b=50),
        plot_bgcolor="white",
        showlegend=show_legend,
        height=400,
        width=None
    )

    # 12) Render chart & capture clicks
    st.markdown("<div style='width:100%'>", unsafe_allow_html=True)
    clicked_points = plotly_events(
        fig,
        click_event=True,
        hover_event=False,
        select_event=False,
        override_height=450
    )
    st.markdown("</div>", unsafe_allow_html=True)

with col_right:
    # Map CSS tweaks
    st.markdown("""
        <style>
        .block-container { gap: 0 !important; }
        .element-container { margin: 0 !important; padding: 0 !important; }
        .stImage { margin: 0 !important; padding: 0 !important; }
        div[data-testid="stImage"] { margin: 0 !important; padding: 0 !important; }
        .map-container { margin-top: -20px !important; }
        .map-container img { max-width: 600px !important; height: auto !important; }
        </style>
    """, unsafe_allow_html=True)

    if clicked_points:
        pt   = clicked_points[0]
        idx  = pt["pointIndex"]
        row  = filtered_data.iloc[idx]
        date = row["date_key"]
        gid  = int(row["gid"])
        ds   = date.strftime("%Y%m%d")

        # Build map path as before...
        if selected_agg == "Diário":
            img_name = f"{ds}_{'Chla' if selected_param_col=='chla_mean' else 'Turb'}_Diario.png"
            folder   = "Chla" if selected_param_col=="chla_mean" else "Turbidez"
            map_path = os.path.join(MAPS_FOLDER, str(gid), folder, "Diário", img_name)

        elif selected_agg == "Mensal":
            mon     = date.strftime("%Y_%m")
            base    = "Chla" if selected_param_col=="chla_mean" else "Turbidez"
            folder  = os.path.join(MAPS_FOLDER, str(gid), base, "Mensal", "Média")
            img_name = next((f for f in os.listdir(folder) if f.startswith(mon)), None)
            map_path = os.path.join(folder, img_name) if img_name else None

        elif selected_agg == "Trimestral":
            q = (date.month - 1) // 3 + 1
            name = f"{date.year}_{q}°Trimestre_Média.png"
            base = "Chla" if selected_param_col=="chla_mean" else "Turbidez"
            map_path = os.path.join(MAPS_FOLDER, str(gid), base, "Trimestral", "Média", name)

        elif selected_agg == "Anual":
            name = f"{date.year}_Média.png"
            base = "Chla" if selected_param_col=="chla_mean" else "Turbidez"
            map_path = os.path.join(MAPS_FOLDER, str(gid), base, "Anual", "Média", name)

        else:  # Permanência
            name = f"{date.year}_Permanência 90%.png"
            base = "Chla" if selected_param_col=="chla_mean" else "Turbidez"
            map_path = os.path.join(MAPS_FOLDER, str(gid), base, "Anual", "Permanência_90", name)

        if map_path and os.path.exists(map_path):
            st.markdown('<div class="map-container">', unsafe_allow_html=True)
            st.image(map_path, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div style="text-align:center;font-size:0.8em;color:gray;">GID: {gid}</div>',
                unsafe_allow_html=True
            )
        else:
            st.warning(f"Mapa não encontrado: {map_path}")
    else:
        st.markdown(
            "<div style='text-align:center;margin-top:20px;'>"
            "Clique em um ponto do gráfico para ver o mapa aqui."
            "</div>",
            unsafe_allow_html=True
        )
