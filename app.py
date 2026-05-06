import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="TWIN-RBI Mongstad",
    page_icon="🔧",
    layout="wide"
)

# ── Header ────────────────────────────────────────────────
st.markdown("""
<h1 style='color:#0D1B2A;'>TWIN-RBI Mongstad</h1>
<h3 style='color:#1D9E75;'>Digital Twin de Integridad Mecánica — Refinería Equinor</h3>
<p style='color:#888780;'>Crudo 75% Troll / 25% Arab Medium · API 580/581 · ASME B31.3 · WRC-107</p>
""", unsafe_allow_html=True)

st.divider()

# ── KPIs ──────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Activos monitorizados", "12")
col2.metric("Accuracy Random Forest", "91.7%", "+3.3% vs baseline")
col3.metric("Activo crítico", "L-10", "RUL = 0.0 años")
col4.metric("V-101 boquilla F", "2.13×", "ratio WRC-107")
col5.metric("Validación DW Sim", "r = 0.95", "Peng-Robinson")

st.divider()

# ── Cargar datos ──────────────────────────────────────────
@st.cache_data
def load_data():
    rbi   = pd.read_csv("data/processed/rbi_labels.csv")
    scada = pd.read_csv("data/raw/scada_operational_data.csv",
                        parse_dates=['date'])
    return rbi, scada

try:
    df_rbi, df_scada = load_data()
    data_ok = True
except:
    data_ok = False

# ── Risk Matrix ───────────────────────────────────────────
st.subheader("📊 Risk Matrix — Estado actual por activo")

if data_ok:
    # Último trimestre por activo
    last = df_rbi.sort_values(['line_id','year','quarter'])\
                 .groupby('line_id').last().reset_index()

    RISK_COLORS = {
        'Low':      '#1D9E75',
        'Medium':   '#BA7517',
        'High':     '#D85A30',
        'Critical': '#A32D2D',
    }

    col_a, col_b = st.columns([2, 1])

    with col_a:
        fig = px.scatter(
            last,
            x='cof_category', y='pof_category',
            size='risk_score', color='risk_label',
            text='line_id',
            color_discrete_map=RISK_COLORS,
            size_max=50,
            labels={
                'cof_category': 'Categoría Consecuencia (CoF)',
                'pof_category': 'Categoría Probabilidad (PoF)',
                'risk_label':   'Riesgo'
            },
            title='Risk Matrix API 581 — Último trimestre 2022'
        )
        fig.update_traces(textposition='top center', textfont_size=10)
        fig.update_layout(
            height=420,
            plot_bgcolor='#F8F8F8',
            xaxis=dict(tickvals=[1,2,3,4,5], range=[0.5, 5.5]),
            yaxis=dict(tickvals=[1,2,3,4,5], range=[0.5, 5.5]),
        )
        # Zonas de riesgo
        for x0,x1,y0,y1,color in [
            (0.5,2.5,0.5,2.5,'#E1F5EE'),
            (0.5,2.5,2.5,5.5,'#FAEEDA'),
            (2.5,5.5,0.5,2.5,'#FAEEDA'),
            (2.5,4.5,2.5,4.5,'#FDEEE8'),
            (4.5,5.5,0.5,5.5,'#FCEBEB'),
            (0.5,5.5,4.5,5.5,'#FCEBEB'),
        ]:
            fig.add_shape(type='rect', x0=x0, x1=x1, y0=y0, y1=y1,
                         fillcolor=color, opacity=0.3, line_width=0)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.markdown("**RUL por activo (años)**")
        rul = last[['line_id','RUL_years','risk_label']]\
              .sort_values('RUL_years')
        for _, row in rul.iterrows():
            color = RISK_COLORS.get(row['risk_label'], '#888780')
            bar_w = min(int(row['RUL_years'] / 60 * 100), 100)
            st.markdown(f"""
            <div style='margin-bottom:4px'>
            <span style='font-size:12px;font-weight:500;color:#0D1B2A;
                         display:inline-block;width:50px'>{row['line_id']}</span>
            <div style='display:inline-block;background:{color};
                        width:{max(bar_w,2)}%;height:14px;
                        border-radius:3px;vertical-align:middle'></div>
            <span style='font-size:11px;color:#888780;margin-left:4px'>
                {row['RUL_years']:.1f} yr</span>
            </div>
            """, unsafe_allow_html=True)

st.divider()

# ── Evolución PoF ─────────────────────────────────────────
st.subheader("📈 Evolución del Riesgo — Activos Críticos")

if data_ok:
    criticos = ['L-10','L-03','L-02','L-01','V-101']
    df_crit  = df_rbi[df_rbi['line_id'].isin(criticos)].copy()
    df_crit['period'] = df_crit['year'].astype(str) + '-Q' + \
                        df_crit['quarter'].astype(str)

    fig2 = px.line(
        df_crit, x='period', y='pof_category',
        color='line_id', markers=True,
        color_discrete_sequence=[
            '#A32D2D','#D85A30','#BA7517','#534AB7','#185FA5'
        ],
        labels={'period':'Trimestre',
                'pof_category':'Categoría PoF',
                'line_id':'Activo'},
        title='Evolución categoría PoF — 2018 a 2022'
    )
    fig2.update_layout(
        height=350, plot_bgcolor='#F8F8F8',
        xaxis_tickangle=45,
        yaxis=dict(tickvals=[1,2,3,4,5],
                   ticktext=['1-Low','2-LowMed','3-Med','4-High','5-Critical'])
    )
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Estado del proyecto ───────────────────────────────────
st.subheader("🗺️ Estado del Proyecto — Plan Maestro v4.0")

modulos = [
    ("EDA + Datasets",          "✅ Completado", "SCADA 5 años · DW Sim r=0.95 · 9 figuras",          "teal"),
    ("Random Forest PoF",       "✅ Completado", "91.7% accuracy · F1-macro 88.7% · 5 categorías",    "teal"),
    ("XGBoost RUL",             "🔄 En progreso","Dataset listo · entrenamiento iniciado",             "amber"),
    ("Cadena H2S → Espesor",    "🔄 En progreso","corrosion_chain.py · datos disponibles",            "amber"),
    ("PINN NozzlePRO",          "⚙️ Ejecutando", "100 casos batch · Computadora 2 · NPS12",           "blue"),
    ("Living RBI Bayesiano",    "⏳ Pendiente",  "Depende de XGBoost · PyMC 5.x",                     "gray"),
    ("API 579 FFS V-101",       "🚨 Urgente",    "Falla activa boquilla F · ratio 2.13×",             "red"),
    ("LSTM Anomaly Detection",  "⏳ Pendiente",  "SCADA listo · anomaly_flag disponible",             "gray"),
    ("Dashboard Streamlit",     "🔄 En progreso","MVP desplegado · módulos en construcción",          "amber"),
]

cols = st.columns(3)
for i, (nombre, estado, detalle, color) in enumerate(modulos):
    color_map = {
        'teal':  ('#E1F5EE','#0F6E56'),
        'amber': ('#FAEEDA','#854F0B'),
        'blue':  ('#E6F1FB','#0C447C'),
        'red':   ('#FCEBEB','#791F1F'),
        'gray':  ('#F4F4F2','#5F5E5A'),
    }
    bg, fg = color_map.get(color, color_map['gray'])
    with cols[i % 3]:
        st.markdown(f"""
        <div style='background:{bg};border-radius:8px;
                    padding:12px;margin-bottom:10px'>
        <p style='font-size:13px;font-weight:600;
                  color:{fg};margin:0'>{nombre}</p>
        <p style='font-size:12px;color:{fg};margin:2px 0'>{estado}</p>
        <p style='font-size:11px;color:#888780;margin:0'>{detalle}</p>
        </div>
        """, unsafe_allow_html=True)

st.divider()
st.caption("TWIN-RBI Mongstad · Luis Fernando Carvallo · "
           "Senior Mechanical Integrity & Digital Twin Expert · "
           "Bootcamp Data Science + AIM Consulting MVP")