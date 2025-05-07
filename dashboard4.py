# -*- coding: utf-8 -*-
"""
Dashboard – visualização de qualidade da água
Updated 07 May 2025
  • Agregações em duas linhas mais compactas (4 + 3) e alinhamento lateral
"""

import os, pickle, numpy as np, pandas as pd
import streamlit as st
import plotly.graph_objects as go
from streamlit_plotly_events import plotly_events

# ──────────────────────────────────────────────────────────────────────────────
# Page config & CSS
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(layout="wide")
st.markdown("""
<style>
.smaller-title{font-size:28px!important;font-weight:bold!important}
.block-container{gap:0!important}
.element-container,.stImage{margin:0!important;padding:0!important}
div[data-testid="stImage"]{margin:0!important;padding:0!important}
.map-container{margin-top:-20px!important}
.map-container img{max-width:600px!important;height:auto!important}

/* === Rádio “Nível de agregação” ========================================== */
div[data-testid="stRadio"] div[role="radiogroup"]{
    display:flex;
    flex-wrap:wrap;
    gap:12px 24px;        /* linha, coluna */
}
div[data-testid="stRadio"] label{
    display:flex;
    align-items:center;   /* círculo alinhado ao texto */
    gap:4px;
    white-space:nowrap;
    font-size:14px;
    margin-bottom:4px;    /* reduz espaçamento vertical */
}
/* Garante 4 itens na 1ª linha (largura máxima ≈ 22 %) */
div[data-testid="stRadio"] label:nth-of-type(-n+4){
    flex:0 1 22%;
}
/* Restante ocupa ~30 % (3 por linha)                                    */
div[data-testid="stRadio"] label:nth-of-type(n+5){
    flex:0 1 30%;
}
</style>
""", unsafe_allow_html=True)
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

def resolve_stat_col(df: pd.DataFrame, base_param: str, stat: str) -> str:
    pref = "chla" if base_param.startswith("chla") else "turb"
    if   stat == "mean":   cands = [f"{pref}_mean"]
    elif stat == "median": cands = [f"{pref}_media", f"{pref}_median"]
    elif stat == "count":  cands = [f"{pref}_count"]
    else:                  cands = [f"{pref}_{stat}"]
    return next((c for c in cands if c in df.columns), cands[0])

def values(df: pd.DataFrame, col: str):
    return (df[col].astype(float) / 100).tolist()

# ──────────────────────────────────────────────────────────────────────────────
# Paths & data
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(__file__)
PKL_PATH    = os.path.join(BASE_DIR, "all_water_masses.pkl")
MAPS_FOLDER = os.path.join(BASE_DIR, "maps")

gdf = load_data(PKL_PATH)
gdf["date_key"] = pd.to_datetime(gdf["date_key"], errors="coerce")

# ──────────────────────────────────────────────────────────────────────────────
# Layout
# ──────────────────────────────────────────────────────────────────────────────
left, right = st.columns([1, 0.9], gap="small")

with left:
    # 1) Massa d’água
    masses   = sorted(gdf["nmoriginal"].dropna().unique())
    default  = "Açude Castanhão" if "Açude Castanhão" in masses else masses[0]
    sel_mass = st.selectbox("Selecione a massa d'água:", masses, index=masses.index(default))

    # 2) Parâmetro
    param_opts = {"Clorofila-a": "chla_mean", "Turbidez": "turb_mean"}
    param_lab  = st.radio("Selecione o parâmetro:", list(param_opts.keys()))
    param_col  = param_opts[param_lab]

    # 3) Estatística
    stat_opts = {"Média": "mean", "Mediana": "median"}
    stat_lab  = st.radio("Estatística mostrada no gráfico:", list(stat_opts.keys()), horizontal=True)
    stat_key  = stat_opts[stat_lab]

    # 4) Intervalo de datas
    dmin, dmax = gdf["date_key"].min().date(), gdf["date_key"].max().date()
    d_range = st.slider("Selecione o intervalo de datas:", dmin, dmax, (dmin, dmax), format="YYYY-MM-DD")

    # 5) Nível de agregação (mapas)
    agg_opts = [
        "Diário", "Mensal", "Trimestral", "Anual",
        "Permanência", "Estado Trófico", "Estado Trófico Mensal"
    ]
    agg_sel  = st.radio("Selecione o nível de agregação do mapa:", agg_opts, horizontal=True)

    # ─── Filtra dados ─────────────────────────────────────────────────────────
    df = gdf.loc[
        (gdf["nmoriginal"] == sel_mass)
        & (gdf["date_key"].dt.date >= d_range[0])
        & (gdf["date_key"].dt.date <= d_range[1])
    ].copy()
    df = df[df[param_col] > 0]

    # Filtro por contagem de pixels
    cnt_col = resolve_stat_col(df, param_col, "count")
    if cnt_col in df.columns:
        if st.checkbox("Filtrar pontos com baixa contagem de pixels", value=False):
            thr = max(5, df[cnt_col].quantile(0.25))
            df = df[df[cnt_col] >= thr]
            st.caption(f"Pontos com contagem &lt; **{int(thr)}** pixels removidos.")

    if df.empty:
        st.warning("Nenhum dado disponível para essa combinação.")
        st.stop()

    df.sort_values("date_key", inplace=True, ignore_index=True)

    # ─── Série principal ─────────────────────────────────────────────────────
    y_col  = resolve_stat_col(df, param_col, stat_key)
    x_vals = df["date_key"].tolist()
    y_vals = values(df, y_col)

    # ─── Média móvel – 30 dias ───────────────────────────────────────────────
    show_roll = st.checkbox("Adicionar linha de média móvel (30 dias)", value=False)
    if show_roll:
        s_roll = (
            pd.Series(y_vals, index=df["date_key"])
            .rolling("30D", center=True, min_periods=1)
            .mean()
            .tolist()
        )

    # ─── Gráfico ─────────────────────────────────────────────────────────────
    color   = "limegreen" if param_col.startswith("chla") else "brown"
    y_title = "NTU" if param_col.startswith("turb") else "µg/L"

    fig = go.Figure()

    # Pontos
    fig.add_trace(
        go.Scatter(
            x=x_vals, y=y_vals, mode="markers",
            marker=dict(size=8, color=color, line=dict(width=1, color="black")),
            name="", showlegend=False,
            hovertemplate=f"<b>Data:</b> %{{x}}<br><b>Valor:</b> %{{y:.2f}} {y_title}<extra></extra>",
        )
    )

    # Linha média móvel
    if show_roll:
        fig.add_trace(
            go.Scatter(
                x=x_vals, y=s_roll, mode="lines",
                line=dict(width=3, color="royalblue", shape="spline", smoothing=1.3),
                name="", showlegend=False,
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
        showlegend=False,
        height=400,
    )

    st.markdown('<div style="width:100%;">', unsafe_allow_html=True)
    clicks = plotly_events(fig, click_event=True, hover_event=False, select_event=False, override_height=450)
    st.markdown("</div>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Right column – mapas
# ──────────────────────────────────────────────────────────────────────────────
with right:
    def build_path(row):
        gid, date = int(row["gid"]), row["date_key"]
        base = "Chla" if param_col.startswith("chla") else "Turbidez"
        dstr = date.strftime("%Y%m%d")

        if agg_sel == "Diário":
            name = f"{dstr}_{'Chla' if base=='Chla' else 'Turb'}_Diario.png"
            return os.path.join(MAPS_FOLDER, str(gid), base, "Diário", name)

        if agg_sel == "Mensal":
            month = date.strftime("%Y_%m")
            folder = os.path.join(MAPS_FOLDER, str(gid), base, "Mensal", "Média")
            try:
                img = next(f for f in os.listdir(folder) if f.startswith(month))
                return os.path.join(folder, img)
            except StopIteration:
                return None

        if agg_sel == "Estado Trófico Mensal":
            if not param_col.startswith("chla"):
                return None
            month = date.strftime("%Y_%m")
            return os.path.join(
                MAPS_FOLDER, str(gid), "Chla", "Mensal", "Média", "IET", f"{month}_IET.png"
            )

        if agg_sel == "Trimestral":
            q = (date.month - 1)//3 + 1
            name = f"{date.year}_{q}°Trimestre_Média.png"
            return os.path.join(MAPS_FOLDER, str(gid), base, "Trimestral", "Média", name)

        if agg_sel == "Anual":
            return os.path.join(MAPS_FOLDER, str(gid), base, "Anual", "Média", f"{date.year}_Média.png")

        if agg_sel == "Estado Trófico":
            if not param_col.startswith("chla"):
                return None
            return os.path.join(
                MAPS_FOLDER, str(gid), "Chla", "2018_2024", "Permanência_90", "2018_2024_IET90.png"
            )

        # Permanência (90 %)
        return os.path.join(
            MAPS_FOLDER, str(gid), base, "Anual", "Permanência_90",
            f"{date.year}_Permanência 90%.png"
        )

    if clicks and clicks[0]["curveNumber"] == 0:
        row  = df.iloc[clicks[0]["pointIndex"]]
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
