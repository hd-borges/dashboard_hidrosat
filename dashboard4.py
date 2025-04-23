# -*- coding: utf-8 -*-
"""
Dashboard – water-quality visualisation
Updated 23 Apr 2025
  • Mean / Median / Max / Min selector
  • Rolling-mean line
  • Low-count filter
  • Shapefile-column fix  (median → media)
"""

import os, pickle, numpy as np, pandas as pd
import streamlit as st
import plotly.graph_objects as go
from streamlit_plotly_events import plotly_events

# ──────────────────────────────────────────────────────────────────────────────
# Styling
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(layout="wide")
st.markdown(
    """
    <style>
    .smaller-title {font-size:28px!important;font-weight:bold!important}
    .block-container{gap:0!important}
    .element-container,.stImage{margin:0!important;padding:0!important}
    div[data-testid="stImage"]{margin:0!important;padding:0!important}
    .map-container{margin-top:-20px!important}
    .map-container img{max-width:600px!important;height:auto!important}
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="smaller-title">Visualização de qualidade de Água obtida por dados espaciais</p>',
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data
def load_data(fp: str) -> pd.DataFrame:
    with open(fp, "rb") as f:
        return pickle.load(f)

def get_stat_col(base: str, stat: str) -> str:
    """Return the column that stores *stat* for this parameter.

    Shapefiles trim field names to 10 chars, so ‘median’ became ‘media’.
    """
    prefix = "chla" if base.startswith("chla") else "turb"
    if stat == "median":            # requested name from UI
        stat = "media"              # actual column name
    return f"{prefix}_{stat}"

def series(df: pd.DataFrame, col: str):
    """Return numeric column divided by 100 (to undo scaling)."""
    return (df[col].astype(float) / 100).tolist()

# ──────────────────────────────────────────────────────────────────────────────
# Paths & data
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(__file__)
PKL_PATH     = os.path.join(BASE_DIR, "all_water_masses.pkl")
MAPS_FOLDER  = os.path.join(BASE_DIR, "maps")

gdf = load_data(PKL_PATH)
gdf["date_key"] = pd.to_datetime(gdf["date_key"], errors="coerce")

# ──────────────────────────────────────────────────────────────────────────────
# Layout
# ──────────────────────────────────────────────────────────────────────────────
col_left, col_right = st.columns([1, 0.9], gap="small")

with col_left:
    # ––– Water-mass
    masses   = sorted(gdf["nmoriginal"].dropna().unique())
    default  = "Açude Castanhão" if "Açude Castanhão" in masses else masses[0]
    sel_mass = st.selectbox("Selecione a massa d'água:", masses, index=masses.index(default))

    # ––– Parameter (mean drives map folders)
    param_opts = {"Clorofila-a": "chla_mean", "Turbidez": "turb_mean"}
    param_lab  = st.radio("Selecione o parâmetro:", list(param_opts.keys()))
    param_col  = param_opts[param_lab]

    # ––– Statistic to plot
    stat_opts = {"Média": "mean", "Mediana": "median", "Máximo": "max", "Mínimo": "min"}
    stat_lab  = st.radio("Estatística mostrada no gráfico:", list(stat_opts.keys()), horizontal=True)
    stat_col_name = get_stat_col(param_col, stat_opts[stat_lab])

    # ––– Date range
    dmin, dmax = gdf["date_key"].min().date(), gdf["date_key"].max().date()
    date_rng = st.slider("Selecione o intervalo de datas:", dmin, dmax, (dmin, dmax), format="YYYY-MM-DD")

    # ––– Aggregation level (for maps)
    agg_opts = ["Diário", "Mensal", "Trimestral", "Anual", "Permanência"]
    agg_sel  = st.radio("Selecione o nível de agregação do mapa:", agg_opts, horizontal=True)

    # ––– Filter dataframe
    mask = (
        (gdf["nmoriginal"] == sel_mass)
        & (gdf["date_key"].dt.date >= date_rng[0])
        & (gdf["date_key"].dt.date <= date_rng[1])
    )
    df = gdf.loc[mask].copy()
    df = df[df[param_col] > 0]

    # low-count filter
    cnt_col = get_stat_col(param_col, "count")
    if cnt_col in df.columns:
        use_filter = st.checkbox("Filtrar pontos com baixa contagem de pixels", value=False)
        if use_filter:
            thresh = max(5, df[cnt_col].quantile(0.25))
            df = df[df[cnt_col] >= thresh]
            st.caption(f"Pontos com contagem &lt; **{int(thresh)}** pixels removidos.")

    if df.empty:
        st.warning("Nenhum dado disponível para essa combinação.")
        st.stop()

    df.sort_values("date_key", inplace=True, ignore_index=True)

    # ––– Data series
    x_vals = df["date_key"].tolist()
    y_vals = series(df, stat_col_name)

    # ––– Rolling mean (optional)
    show_roll = st.checkbox("Adicionar linha de média móvel", value=False)
    if show_roll:
        win = st.slider("Janela da média móvel (pontos):", 2, 30, 5, key="roll_win")
        roll_vals = pd.Series(y_vals).rolling(win, center=True, min_periods=1).mean()

    # ––– Plot
    color   = "limegreen" if param_col.startswith("chla") else "brown"
    y_title = "NTU" if param_col.startswith("turb") else "µg/L"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_vals, y=y_vals, mode="markers",
            marker=dict(size=8, color=color, line=dict(width=1, color="black")),
            name=f"{param_lab} ({stat_lab.lower()})",
            hovertemplate=f"<b>Data:</b> %{{x}}<br><b>Valor:</b> %{{y:.2f}} {y_title}<extra></extra>",
        )
    )
    if show_roll:
        fig.add_trace(
            go.Scatter(
                x=x_vals, y=roll_vals, mode="lines",
                line=dict(width=2), name=f"Média móvel ({win})",
                hovertemplate=f"Média móvel: %{{y:.2f}} {y_title}<extra></extra>",
            )
        )
    fig.update_layout(
        xaxis_title="Data",
        yaxis_title=y_title,
        yaxis=dict(range=[0, max(y_vals)*1.1], showgrid=True),
        xaxis=dict(showgrid=True),
        margin=dict(l=40, r=20, t=20, b=50),
        plot_bgcolor="white",
        showlegend=show_roll,
        height=400,
    )

    st.markdown('<div style="width:100%;">', unsafe_allow_html=True)
    click = plotly_events(fig, click_event=True, hover_event=False, select_event=False, override_height=450)
    st.markdown("</div>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Right column – maps
# ──────────────────────────────────────────────────────────────────────────────
with col_right:
    def build_path(row) -> str | None:
        gid   = int(row["gid"])
        date  = row["date_key"]
        d_str = date.strftime("%Y%m%d")
        base  = "Chla" if param_col.startswith("chla") else "Turbidez"

        if agg_sel == "Diário":
            name = f"{d_str}_{'Chla' if base=='Chla' else 'Turb'}_Diario.png"
            return os.path.join(MAPS_FOLDER, str(gid), base, "Diário", name)

        if agg_sel == "Mensal":
            month_str = date.strftime("%Y_%m")
            folder = os.path.join(MAPS_FOLDER, str(gid), base, "Mensal", "Média")
            try:
                name = next(f for f in os.listdir(folder) if f.startswith(month_str))
                return os.path.join(folder, name)
            except StopIteration:
                return None

        if agg_sel == "Trimestral":
            q = (date.month - 1) // 3 + 1
            name = f"{date.year}_{q}°Trimestre_Média.png"
            return os.path.join(MAPS_FOLDER, str(gid), base, "Trimestral", "Média", name)

        if agg_sel == "Anual":
            return os.path.join(MAPS_FOLDER, str(gid), base, "Anual", "Média", f"{date.year}_Média.png")

        # Permanência
        return os.path.join(MAPS_FOLDER, str(gid), base, "Anual", "Permanência_90",
                            f"{date.year}_Permanência 90%.png")

    if click and click[0]["curveNumber"] == 0:        # respond only to marker clicks
        idx  = click[0]["pointIndex"]
        row  = df.iloc[idx]
        path = build_path(row)

        if path and os.path.exists(path):
            st.markdown('<div class="map-container">', unsafe_allow_html=True)
            st.image(path, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown(
                f"<div style='text-align:center;font-size:0.8em;color:gray;'>GID: {int(row['gid'])}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.warning(f"Mapa não encontrado: {path}")
    else:
        st.markdown(
            "<div style='text-align:center;margin-top:20px;'>Clique em um ponto do gráfico para ver o mapa aqui.</div>",
            unsafe_allow_html=True,
        )
