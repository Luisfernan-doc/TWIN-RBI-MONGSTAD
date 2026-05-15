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
    ("XGBoost RUL",             "✅ Completado", "R²=0.9995 · MAE=0.24 años",                         "teal"),
    ("API 579 FFS Level 1",     "✅ Completado", "5 mecanismos · PFI flota completa · 12 activos",     "teal"),
    ("LSTM Anomaly Detection",  "⏳ Pendiente",  "SCADA listo · anomaly_flag disponible",             "gray"),
    ("Living RBI Bayesiano",    "⏳ Pendiente",  "Depende de XGBoost · PyMC 5.x",                     "gray"),
    ("FFS Level 2 V-101",       "⏳ Pendiente",  "WRC-107/297 · boquilla F · ratio 2.13×",            "gray"),
    ("Dashboard completo",      "🔄 En progreso","MVP desplegado · módulos en construcción",          "amber"),
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

# ── Explorador de activo ──────────────────────────────────
st.subheader("🔍 Explorador de Activo — Condiciones Operacionales")

if data_ok:
    activo_sel = st.selectbox(
        "Selecciona un activo:",
        options=sorted(df_scada['line_id'].unique()),
        index=list(sorted(df_scada['line_id'].unique())).index('L-10'),
        key='explorador_selector'
    )

    df_act = df_scada[df_scada['line_id'] == activo_sel].copy()
    df_act = df_act[df_act['sensor_status'].isin([0, 1])]

    last_rbi = df_rbi[df_rbi['line_id'] == activo_sel].sort_values(
        ['year','quarter']).iloc[-1]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("PoF Categoría", f"{int(last_rbi['pof_category'])}", last_rbi['risk_label'])
    col2.metric("RUL", f"{last_rbi['RUL_years']:.1f} años")
    col3.metric("H2S medio", f"{last_rbi['h2s_mean']:.0f} ppm")
    col4.metric("CR media", f"{last_rbi['cr_mean']:.3f} mm/yr")

    st.markdown("---")

    col_a, col_b = st.columns(2)
    df_monthly = df_act.resample('ME', on='date').mean(numeric_only=True).reset_index()

    with col_a:
        fig_pt = go.Figure()
        fig_pt.add_trace(go.Scatter(
            x=df_monthly['date'], y=df_monthly['pressure_inlet_bar'],
            name='Presión inlet (bar)', line=dict(color='#185FA5', width=2)
        ))
        fig_pt.add_trace(go.Scatter(
            x=df_monthly['date'], y=df_monthly['temp_process_c'],
            name='Temperatura proceso (°C)', line=dict(color='#D85A30', width=2),
            yaxis='y2'
        ))
        fig_pt.update_layout(
            title=f'{activo_sel} — Presión y Temperatura', height=300,
            plot_bgcolor='#F8F8F8',
            yaxis=dict(title='Presión (bar)', color='#185FA5'),
            yaxis2=dict(title='Temperatura (°C)', color='#D85A30',
                       overlaying='y', side='right'),
            legend=dict(orientation='h', y=-0.2), margin=dict(t=40, b=40)
        )
        st.plotly_chart(fig_pt, use_container_width=True)

    with col_b:
        fig_hv = go.Figure()
        fig_hv.add_trace(go.Scatter(
            x=df_monthly['date'],
            y=df_monthly[['h2s_ppm_an1','h2s_ppm_an2']].mean(axis=1),
            name='H2S medio (ppm)', line=dict(color='#A32D2D', width=2)
        ))
        fig_hv.add_trace(go.Scatter(
            x=df_monthly['date'], y=df_monthly['vibration_mm_s'],
            name='Vibración (mm/s)', line=dict(color='#534AB7', width=2),
            yaxis='y2'
        ))
        fig_hv.update_layout(
            title=f'{activo_sel} — H2S y Vibración', height=300,
            plot_bgcolor='#F8F8F8',
            yaxis=dict(title='H2S (ppm)', color='#A32D2D'),
            yaxis2=dict(title='Vibración (mm/s)', color='#534AB7',
                       overlaying='y', side='right'),
            legend=dict(orientation='h', y=-0.2), margin=dict(t=40, b=40)
        )
        st.plotly_chart(fig_hv, use_container_width=True)

    fig_dew = go.Figure()
    fig_dew.add_trace(go.Scatter(
        x=df_monthly['date'], y=df_monthly['delta_T_dew'],
        name='Delta T dew (°C)', line=dict(color='#1D9E75', width=2),
        fill='tozeroy', fillcolor='rgba(29,158,117,0.1)'
    ))
    fig_dew.add_hline(y=0, line_dash='dash', line_color='#A32D2D',
                      annotation_text='Punto de rocío — riesgo CUI')
    fig_dew.add_hline(y=5, line_dash='dot', line_color='#BA7517',
                      annotation_text='Zona de riesgo (<5°C)')
    fig_dew.update_layout(
        title=f'{activo_sel} — Delta T dew (T_pared - T_rocío)',
        height=280, plot_bgcolor='#F8F8F8',
        yaxis=dict(title='°C'), margin=dict(t=40, b=20)
    )
    st.plotly_chart(fig_dew, use_container_width=True)

st.divider()

# ── FFS Assessment — API 579 Level 1 ─────────────────────
st.subheader("🔩 FFS Assessment — API 579-1/ASME FFS-1 Level 1")

@st.cache_resource
def load_ffs_engine():
    import sys
    sys.path.append('.')
    from src.ffs_engine import FFSEngine
    return FFSEngine(
        static_data_path='data/raw/pipe_static_data.csv',
        rbi_labels_path='data/processed/rbi_labels.csv'
    )

try:
    engine = load_ffs_engine()
    df_pfi = engine.pfi_all()
    ffs_ok = True
except Exception as e:
    st.error(f"Error cargando FFS engine: {e}")
    ffs_ok = False

if ffs_ok:

    st.markdown("##### Proximity to Failure Index — Flota completa")
    st.caption("PFI = % del camino recorrido hacia la falla Level 1. "
               "⚠️ SSC/HIC no se captura en PFI — ver detalle por activo.")

    COLOR_MAP = {
        'FAIL':    '#A32D2D',
        'CRITICO': '#D85A30',
        'MONITOR': '#BA7517',
        'SAFE':    '#1D9E75',
    }

    for _, row in df_pfi.iterrows():
        c0,c1,c2,c3,c4,c5 = st.columns([0.8, 0.8, 3, 1, 0.8, 2])
        pfi_val  = min(row['PFI_final'], 100)
        color    = COLOR_MAP.get(row['level'], '#888780')
        bar_html = f"""
        <div style='background:#F0F0F0;border-radius:4px;height:18px;width:100%'>
        <div style='background:{color};width:{pfi_val}%;height:18px;
                    border-radius:4px;text-align:right;padding-right:4px'>
        <span style='font-size:10px;color:white;line-height:18px'>
        {row['PFI_final']:.0f}%</span>
        </div></div>"""
        c0.markdown(f"**{row['tag']}**")
        c1.markdown(f"{row['color']} {row['PFI_final']:.0f}%")
        c2.markdown(bar_html, unsafe_allow_html=True)
        c3.markdown(f"<span style='color:{color};font-weight:600'>"
                    f"{row['level']}</span>", unsafe_allow_html=True)
        c4.markdown(f"{row['RUL_years']:.1f} yr")
        c5.markdown(f"<span style='font-size:11px'>{row['dominant']}</span>",
                    unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("##### Detalle FFS por activo")

    activo_ffs = st.selectbox(
        "Selecciona activo para evaluación FFS detallada:",
        options=df_pfi['tag'].tolist(),
        key='ffs_selector'
    )

    r   = engine.assess(activo_ffs)
    pfi = engine.calc_pfi(activo_ffs)
    color_act = COLOR_MAP.get(pfi['level'], '#888780')

    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("FFS Status",     r.ffs_status)
    m2.metric("PFI Final",      f"{pfi['PFI_final']:.1f}%")
    m3.metric("t_actual",       f"{r.t_actual_mm:.2f} mm",
              f"nominal: {r.t_nominal_mm} mm")
    m4.metric("MAWP",           f"{r.MAWP_bar:.1f} bar",
              f"P_oper: {r.P_oper_bar} bar")
    m5.metric("Vida remanente", f"{r.remaining_life_yr:.1f} años")

    col_mec, col_chart = st.columns([1, 1])

    with col_mec:
        st.markdown("**Mecanismos de daño Level 1**")
        for mec, status in {
            'GML — Metal Loss': r.gml_status,
            'LML — Pitting'   : r.lml_status,
            'SSC / HIC'       : r.ssc_status,
            'Creep'           : r.creep_status,
            'Fatiga termica'  : r.fatigue_status,
        }.items():
            if 'FAIL'    in status: icon, bg = '🔴', '#FCEBEB'
            elif 'MONITOR' in status: icon, bg = '🟡', '#FAEEDA'
            else:                   icon, bg = '🟢', '#E1F5EE'
            st.markdown(f"""
            <div style='background:{bg};border-radius:6px;
                        padding:8px 12px;margin-bottom:6px'>
            <b>{icon} {mec}</b><br>
            <span style='font-size:12px;color:#555'>{status}</span>
            </div>""", unsafe_allow_html=True)

    with col_chart:
        st.markdown("**PFI por dimensión**")
        vals   = [pfi['PFI_thickness'], pfi['PFI_mawp'], pfi['PFI_rul']]
        labels = ['Espesor', 'Presion (MAWP)', 'Vida util']
        colors = ['#A32D2D' if v>=100 else '#D85A30' if v>=75
                  else '#BA7517' if v>=50 else '#1D9E75' for v in vals]
        fig_pfi = go.Figure(go.Bar(
            x=vals, y=labels, orientation='h',
            marker_color=colors,
            text=[f"{v:.1f}%" for v in vals],
            textposition='outside',
        ))
        fig_pfi.add_vline(x=100, line_dash='dash', line_color='#A32D2D',
                          annotation_text='Limite falla')
        fig_pfi.add_vline(x=75,  line_dash='dot',  line_color='#D85A30',
                          annotation_text='Critico')
        fig_pfi.update_layout(
            height=240, plot_bgcolor='#F8F8F8',
            xaxis=dict(range=[0,160], title='%'),
            margin=dict(t=10,b=10,l=10,r=60),
            showlegend=False
        )
        st.plotly_chart(fig_pfi, use_container_width=True)

    st.markdown(f"""
    <div style='background:{color_act}22;border-left:4px solid {color_act};
                border-radius:4px;padding:12px;margin-top:8px'>
    <b style='color:{color_act}'>Accion requerida — {activo_ffs}</b><br>
    <span style='font-size:13px'>{r.action_required}</span><br>
    <span style='font-size:12px;color:#555'>
    Proxima inspeccion: {r.next_insp_months} meses</span>
    </div>""", unsafe_allow_html=True)

    if 'FAIL' in r.ssc_status:
        st.warning(f"⚠️ **SSC/HIC activo** — {r.ssc_status}. "
                   "El PFI no captura fractura fragil. "
                   "Requiere WFMT/RT y evaluacion NACE MR0175.")

st.divider()
st.caption("TWIN-RBI Mongstad · Luis Fernando Carvallo · "
           "Senior Mechanical Integrity & Digital Twin Expert · "
           "Bootcamp Data Science + AIM Consulting MVP")
